"""Signal performance tracker — measures whether signals predict future price moves.

Logs every BUY/WATCHLIST signal with the price at signal time. A scheduled job
checks prices 5/10/20 trading days later and records the outcome. Over time this
builds a record of hit rates, avg return, and signal quality.

Data stored in outputs/.signal_tracker.json.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from stockpulse.data.provider import get_current_quote

logger = logging.getLogger(__name__)

_TRACKER_FILE = Path(__file__).resolve().parent.parent.parent / "outputs" / ".signal_tracker.json"


def _load_tracker() -> dict:
    if _TRACKER_FILE.exists():
        try:
            with open(_TRACKER_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"signals": [], "stats": {}}


def _save_tracker(data: dict) -> None:
    _TRACKER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_TRACKER_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


def log_signal(recommendation: dict) -> None:
    """Log a BUY or WATCHLIST signal for future performance tracking.

    Called automatically when a recommendation with action BUY or WATCHLIST is generated.
    """
    action = recommendation.get("action", "")
    if action not in ("BUY", "WATCHLIST"):
        return

    tracker = _load_tracker()
    ticker = recommendation["ticker"]

    # Don't log duplicate signals for the same ticker on the same day
    today = datetime.now().strftime("%Y-%m-%d")
    existing = [s for s in tracker["signals"]
                if s["ticker"] == ticker and s["signal_date"] == today]
    if existing:
        return

    quote = get_current_quote(ticker)
    entry_price = quote.get("price", 0)
    if entry_price <= 0:
        return

    signal_record = {
        "ticker": ticker,
        "action": action,
        "signal_date": today,
        "entry_price": entry_price,
        "composite_score": recommendation.get("composite_score", 0),
        "confidence": recommendation.get("confidence", 0),
        "thesis": recommendation.get("thesis", ""),
        "checkpoints": {
            "5d": {"date": None, "price": None, "return_pct": None, "checked": False},
            "10d": {"date": None, "price": None, "return_pct": None, "checked": False},
            "20d": {"date": None, "price": None, "return_pct": None, "checked": False},
        },
    }

    tracker["signals"].append(signal_record)
    # Keep last 500 signals max
    tracker["signals"] = tracker["signals"][-500:]
    _save_tracker(tracker)
    logger.info("Tracked signal: %s %s at $%.2f (score: %.1f)",
                action, ticker, entry_price, recommendation.get("composite_score", 0))


def check_signal_outcomes() -> dict:
    """Check prices for signals that have reached their 5/10/20 day checkpoints.

    Returns summary of newly resolved checkpoints.
    """
    tracker = _load_tracker()
    today = datetime.now()
    newly_resolved = {"5d": 0, "10d": 0, "20d": 0}

    for signal in tracker["signals"]:
        signal_date = datetime.strptime(signal["signal_date"], "%Y-%m-%d")
        entry_price = signal["entry_price"]
        if entry_price <= 0:
            continue

        for period_key, trading_days in [("5d", 7), ("10d", 14), ("20d", 28)]:
            checkpoint = signal["checkpoints"][period_key]
            if checkpoint["checked"]:
                continue

            # Check if enough calendar days have passed (trading_days is approximate)
            days_since = (today - signal_date).days
            if days_since < trading_days:
                continue

            # Get current price for this ticker
            try:
                quote = get_current_quote(signal["ticker"])
                current_price = quote.get("price", 0)
                if current_price <= 0:
                    continue

                return_pct = ((current_price - entry_price) / entry_price) * 100
                checkpoint["date"] = today.strftime("%Y-%m-%d")
                checkpoint["price"] = current_price
                checkpoint["return_pct"] = round(return_pct, 2)
                checkpoint["checked"] = True
                newly_resolved[period_key] += 1

                logger.info(
                    "Signal outcome: %s %s entry=$%.2f now=$%.2f %s-return=%.2f%%",
                    signal["action"], signal["ticker"], entry_price,
                    current_price, period_key, return_pct,
                )
            except Exception:
                continue

    # Recompute aggregate stats
    tracker["stats"] = _compute_stats(tracker["signals"])
    _save_tracker(tracker)
    return newly_resolved


def _compute_stats(signals: list) -> dict:
    """Compute aggregate performance statistics."""
    stats = {}

    for period_key in ["5d", "10d", "20d"]:
        resolved = [s for s in signals if s["checkpoints"][period_key]["checked"]]
        if not resolved:
            stats[period_key] = {"count": 0, "avg_return": 0, "hit_rate": 0, "avg_win": 0, "avg_loss": 0}
            continue

        returns = [s["checkpoints"][period_key]["return_pct"] for s in resolved]
        winners = [r for r in returns if r > 0]
        losers = [r for r in returns if r <= 0]

        stats[period_key] = {
            "count": len(resolved),
            "avg_return": round(sum(returns) / len(returns), 2),
            "hit_rate": round(len(winners) / len(resolved) * 100, 1),
            "avg_win": round(sum(winners) / len(winners), 2) if winners else 0,
            "avg_loss": round(sum(losers) / len(losers), 2) if losers else 0,
            "best": round(max(returns), 2),
            "worst": round(min(returns), 2),
        }

        # Stats by action type
        for action in ["BUY", "WATCHLIST"]:
            action_resolved = [s for s in resolved if s["action"] == action]
            if action_resolved:
                action_returns = [s["checkpoints"][period_key]["return_pct"] for s in action_resolved]
                action_winners = [r for r in action_returns if r > 0]
                stats[f"{period_key}_{action.lower()}"] = {
                    "count": len(action_resolved),
                    "avg_return": round(sum(action_returns) / len(action_returns), 2),
                    "hit_rate": round(len(action_winners) / len(action_resolved) * 100, 1),
                }

    return stats


def get_performance_report() -> str:
    """Generate a markdown performance report."""
    tracker = _load_tracker()
    stats = tracker.get("stats", {})
    total_signals = len(tracker.get("signals", []))

    lines = [
        "## Signal Performance Tracker",
        "",
        f"**Total signals tracked:** {total_signals}",
        "",
    ]

    if not stats:
        lines.append("*No performance data yet. Signals need 5+ trading days to produce results.*")
        return "\n".join(lines)

    lines.append("| Period | Signals | Avg Return | Hit Rate | Avg Win | Avg Loss |")
    lines.append("|--------|---------|-----------|----------|---------|----------|")

    for period_key in ["5d", "10d", "20d"]:
        s = stats.get(period_key, {})
        if s.get("count", 0) > 0:
            lines.append(
                f"| {period_key} | {s['count']} | {s['avg_return']:+.2f}% | "
                f"{s['hit_rate']:.0f}% | {s.get('avg_win', 0):+.2f}% | {s.get('avg_loss', 0):.2f}% |"
            )

    # Recent signals
    recent = tracker.get("signals", [])[-10:]
    if recent:
        lines.extend(["", "### Recent Signals", ""])
        lines.append("| Date | Ticker | Action | Entry | Score | 5d | 10d | 20d |")
        lines.append("|------|--------|--------|-------|-------|-----|------|------|")
        for s in reversed(recent):
            cp5 = s["checkpoints"]["5d"]
            cp10 = s["checkpoints"]["10d"]
            cp20 = s["checkpoints"]["20d"]
            r5 = f"{cp5['return_pct']:+.1f}%" if cp5["checked"] else "..."
            r10 = f"{cp10['return_pct']:+.1f}%" if cp10["checked"] else "..."
            r20 = f"{cp20['return_pct']:+.1f}%" if cp20["checked"] else "..."
            lines.append(
                f"| {s['signal_date']} | {s['ticker']} | {s['action']} | "
                f"${s['entry_price']:.2f} | {s['composite_score']:+.1f} | {r5} | {r10} | {r20} |"
            )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Backward-compatibility shims for callers using the old API
# (jobs.py eod_recap_job, run.py performance mode, daily.py reports)
# ---------------------------------------------------------------------------

def review_signals() -> dict:
    """Legacy wrapper: check outcomes and return summary in old format.

    Calls check_signal_outcomes() then maps stats into the period key format
    expected by existing callers (day_5, day_10, day_20).
    """
    check_signal_outcomes()
    tracker = _load_tracker()
    stats = tracker.get("stats", {})
    total = len(tracker.get("signals", []))

    periods: dict = {}
    key_map = {"5d": "day_5", "10d": "day_10", "20d": "day_20"}
    for new_key, old_key in key_map.items():
        s = stats.get(new_key, {})
        count = s.get("count", 0)
        if count == 0:
            periods[old_key] = {"reviewed": 0}
        else:
            avg_win = s.get("avg_win", 0)
            avg_loss = abs(s.get("avg_loss", 0))
            periods[old_key] = {
                "reviewed": count,
                "hit_rate": s.get("hit_rate", 0),
                "avg_return": s.get("avg_return", 0),
                "avg_win": avg_win,
                "avg_loss": avg_loss,
                "profit_factor": round(avg_win / avg_loss, 2) if avg_loss > 0 else 0,
                "best": s.get("best", 0),
                "worst": s.get("worst", 0),
            }

    return {"total_signals": total, "periods": periods}


def generate_performance_report() -> str:
    """Legacy wrapper: write a markdown performance report file and return its path."""
    report_dir = _TRACKER_FILE.parent / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{datetime.now().strftime('%Y-%m-%d')}-performance.md"
    path.write_text(get_performance_report())
    return str(path)
