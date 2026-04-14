"""Market scanner -- orchestrates full scan across universe."""
import logging
from datetime import datetime
from stockpulse.data.universe import get_full_universe
from stockpulse.data.provider import get_price_history
from stockpulse.research.recommendation import generate_recommendation, rank_recommendations
from stockpulse.config.settings import load_strategies, load_watchlists, save_watchlists
from stockpulse.alerts.dispatcher import dispatch_alert

logger = logging.getLogger(__name__)

def run_full_scan(tickers: list[str] | None = None) -> list[dict]:
    if tickers is None:
        tickers = get_full_universe()
    logger.info("Starting full scan of %d tickers at %s", len(tickers), datetime.now())
    recommendations = []
    for i, ticker in enumerate(tickers):
        try:
            df = get_price_history(ticker, period="1y")
            if df.empty or len(df) < 50:
                logger.debug("Skipping %s: insufficient data (%d rows)", ticker, len(df))
                continue
            rec = generate_recommendation(ticker, df)
            recommendations.append(rec)
            if (i + 1) % 50 == 0:
                logger.info("Scanned %d/%d tickers", i + 1, len(tickers))
        except Exception:
            logger.debug("Scan failed for %s", ticker)
    ranked = rank_recommendations(recommendations)
    logger.info("Scan complete: %d tickers scanned, %d recommendations generated", len(tickers), len(ranked))

    # Auto-discover: add tickers crossing WATCHLIST threshold to discovered list
    _update_discovered(ranked)

    # Track BUY/WATCHLIST signals for performance measurement
    _track_signals(ranked)

    return ranked

def run_watchlist_scan(tickers: list[str]) -> list[dict]:
    """Quick scan — no auto-discovery (only full scans discover new tickers)."""
    if tickers is None:
        tickers = []
    logger.info("Watchlist scan of %d tickers", len(tickers))
    recommendations = []
    for ticker in tickers:
        try:
            df = get_price_history(ticker, period="1y")
            if df.empty or len(df) < 50:
                continue
            rec = generate_recommendation(ticker, df)
            recommendations.append(rec)
        except Exception:
            logger.debug("Scan failed for %s", ticker)
    return rank_recommendations(recommendations)


def _update_discovered(ranked: list[dict]) -> None:
    """Auto-add tickers that cross WATCHLIST/BUY threshold to discovered list."""
    thresholds = load_strategies().get("thresholds", {})
    watchlist_threshold = thresholds.get("watchlist", 35)

    try:
        wl = load_watchlists()
        user_tickers = set(wl.get("user", []))
        discovered = set(wl.get("discovered", []))
        new_discoveries = []

        for rec in ranked:
            ticker = rec["ticker"]
            action = rec["action"]
            score = rec["composite_score"]

            # Skip if already in user list or already discovered
            if ticker in user_tickers or ticker in discovered:
                continue

            # Add if BUY or WATCHLIST
            if action in ("BUY", "WATCHLIST") or score >= watchlist_threshold:
                new_discoveries.append(ticker)
                discovered.add(ticker)

        if new_discoveries:
            # Update watchlists.yaml
            wl["discovered"] = sorted(discovered)

            # Update priority list with scores
            priority = []
            for rec in ranked:
                if rec["ticker"] in discovered or rec["ticker"] in user_tickers:
                    priority.append({
                        "ticker": rec["ticker"],
                        "score": round(rec["composite_score"], 1),
                        "action": rec["action"],
                    })
            wl["priority"] = sorted(priority, key=lambda x: abs(x["score"]), reverse=True)

            save_watchlists(wl)

            # Alert for each new discovery
            for ticker in new_discoveries:
                rec = next((r for r in ranked if r["ticker"] == ticker), None)
                if rec:
                    dispatch_alert({
                        "ticker": ticker,
                        "action": rec["action"],
                        "confidence": rec["confidence"],
                        "thesis": f"New discovery: {rec['thesis']}",
                        "type": "discovery",
                        "technical_summary": rec.get("technical_summary", ""),
                        "catalyst_summary": rec.get("catalyst_summary", ""),
                        "invalidation": rec.get("invalidation", ""),
                    })

            logger.info("Auto-discovered %d new tickers: %s", len(new_discoveries), new_discoveries)

        # Auto-remove discovered tickers that have been HOLD for 5+ consecutive days
        _cleanup_discovered(ranked, wl, user_tickers)

    except Exception:
        logger.exception("Failed to update discovered watchlist")


def _cleanup_discovered(ranked: list[dict], wl: dict, user_tickers: set) -> None:
    """Remove discovered tickers that dropped below WATCHLIST for 5 consecutive scans."""
    import json
    from pathlib import Path

    state_file = Path(__file__).resolve().parent.parent.parent / "outputs" / ".discovery_state.json"

    # Load hold-day counters
    try:
        with open(state_file) as f:
            state = json.load(f)
    except Exception:
        state = {}

    discovered = set(wl.get("discovered", []))
    rec_map = {r["ticker"]: r for r in ranked}
    removed = []

    for ticker in list(discovered):
        if ticker in user_tickers:
            continue  # never remove user tickers

        rec = rec_map.get(ticker)
        if rec and rec["action"] in ("BUY", "WATCHLIST"):
            # Still active — reset counter
            state[ticker] = 0
        else:
            # Below threshold — increment counter
            state[ticker] = state.get(ticker, 0) + 1

        if state.get(ticker, 0) >= 5:
            removed.append(ticker)
            discovered.discard(ticker)
            state.pop(ticker, None)

    if removed:
        wl["discovered"] = sorted(discovered)
        # Remove from priority too
        wl["priority"] = [p for p in wl.get("priority", []) if p.get("ticker") not in removed]
        save_watchlists(wl)
        logger.info("Auto-removed %d stale discovered tickers: %s", len(removed), removed)

    # Save state
    state_file.parent.mkdir(parents=True, exist_ok=True)
    with open(state_file, "w") as f:
        json.dump(state, f)


def _track_signals(ranked: list[dict]) -> None:
    """Log BUY/WATCHLIST signals for performance tracking."""
    try:
        from stockpulse.research.tracker import log_signal
        for rec in ranked:
            if rec.get("action") in ("BUY", "WATCHLIST"):
                log_signal(rec)
    except Exception:
        logger.debug("Signal tracking failed")
