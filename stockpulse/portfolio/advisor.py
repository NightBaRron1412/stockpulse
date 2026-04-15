"""Portfolio Advisor — always-on evaluator, never auto-trader.

Runs after every scan, generates structured suggestions with severity levels,
dispatches only on state changes. Execution stays manual.

Priority order:
1. Risk actions (EXIT, TRIM)
2. Cash deployment (BUY from cash, SWAP)
3. Watchlist opportunities (starters from excess cash)
"""
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_STATE_FILE = Path(__file__).resolve().parent.parent.parent / "outputs" / ".advisor_state.json"

# Known ETF tickers and patterns — excluded from single-position concentration checks
_KNOWN_ETFS = {
    "SPY", "QQQ", "IWM", "DIA", "VOO", "VTI", "SPUS", "SPWO", "SPSK", "HLAL",
    "SMH", "XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLB", "XLU", "XLRE",
    "GLD", "SLV", "TLT", "BND", "AGG", "HYG", "LQD", "ARKK", "SOXX", "VGT",
    "SCHD", "VIG", "DGRO", "NOBL", "VYM", "HDV", "FTEC", "IGV", "HACK", "CIBR",
    "EEM", "EFA", "VWO", "IEMG", "VEA", "VXUS",
}


def _is_etf(ticker: str) -> bool:
    """Check if ticker is a known ETF."""
    return ticker.upper() in _KNOWN_ETFS


# ── Data structures ──────────────────────────────────────────────

class Severity(str, Enum):
    URGENT = "urgent"
    ACTIONABLE = "actionable"
    INFORMATIONAL = "info"


class SuggestionType(str, Enum):
    EXIT = "exit"
    TRIM_CAUTION = "trim_caution"
    TRIM_CONCENTRATION = "trim_concentration"
    BUY_FROM_CASH = "buy_from_cash"
    SWAP = "swap"
    WATCHLIST_STARTER = "watchlist_starter"
    RISK_ALERT = "risk_alert"
    NEAR_MISS = "near_miss"


_SEVERITY_ORDER = {Severity.URGENT: 0, Severity.ACTIONABLE: 1, Severity.INFORMATIONAL: 2}
_TYPE_ORDER = {
    SuggestionType.EXIT: 0, SuggestionType.TRIM_CAUTION: 1,
    SuggestionType.TRIM_CONCENTRATION: 2, SuggestionType.RISK_ALERT: 3,
    SuggestionType.BUY_FROM_CASH: 4, SuggestionType.SWAP: 5,
    SuggestionType.WATCHLIST_STARTER: 6, SuggestionType.NEAR_MISS: 7,
}


@dataclass
class AdvisorSuggestion:
    severity: Severity
    suggestion_type: SuggestionType
    ticker: str
    action: str
    summary: str
    details: str
    score: float = 0.0
    confidence: int = 0
    hash: str = ""
    suggested_amount: float | None = None
    trim_fraction: float | None = None
    swap_out_ticker: str | None = None
    swap_out_score: float | None = None
    swap_score_gap: float | None = None
    tax_impact_note: str | None = None
    wash_sale_warning: bool = False
    persistence_count: int = 0
    is_new: bool = True
    entry_timing: dict | None = None
    pattern_match: dict | None = None
    regime: str | None = None
    current_price: float | None = None
    entry_target: float | None = None
    stop_price: float | None = None

    def __post_init__(self):
        if not self.hash:
            base = f"{self.suggestion_type.value}_{self.ticker}"
            if self.swap_out_ticker:
                base += f"_{self.swap_out_ticker}"
            self.hash = base

    def to_dict(self) -> dict:
        d = asdict(self)
        d["severity"] = self.severity.value
        d["suggestion_type"] = self.suggestion_type.value
        return d


# ── State management ─────────────────────────────────────────────

def _load_state() -> dict:
    try:
        if _STATE_FILE.exists():
            return json.loads(_STATE_FILE.read_text())
    except Exception:
        logger.exception("Failed to load advisor state")
    return {
        "last_run": None, "scan_trigger": None,
        "ticker_actions": {}, "current_suggestions": [],
        "dispatched_hashes": {}, "acknowledged_hashes": [],
        "turnover": {"swaps_today": 0, "swap_date": "", "trims_this_week": {}, "last_trade_dates": {}},
    }


def _save_state(state: dict) -> None:
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps(state, indent=2, default=str))
    except Exception:
        logger.exception("Failed to save advisor state")


def _get_config() -> dict:
    from stockpulse.config.settings import load_strategies
    return load_strategies().get("portfolio_advisor", {})


# ── Portfolio context ────────────────────────────────────────────

def _get_portfolio_context(rec_map: dict) -> dict:
    from stockpulse.portfolio.tracker import get_portfolio_status
    from stockpulse.portfolio.risk import get_position_clusters, check_drawdown_status
    from stockpulse.config.settings import load_portfolio, load_strategies

    portfolio = get_portfolio_status()
    positions = portfolio.get("positions", [])
    portfolio_value = portfolio.get("total_current", 0)
    total_invested = portfolio.get("total_invested", 0)

    port_cfg = load_portfolio()
    cash = port_cfg.get("cash", None)
    if cash is None:
        initial = load_strategies().get("backtesting", {}).get("initial_cash", 100000)
        cash = max(0, initial - total_invested)

    held_tickers = {p["ticker"] for p in positions}
    clusters = {}
    if held_tickers:
        try:
            clusters = get_position_clusters(list(held_tickers))
        except Exception:
            pass

    drawdown = {"drawdown_pct": 0, "size_multiplier": 1.0, "new_buys_paused": False}
    peak = port_cfg.get("peak_equity", portfolio_value + cash)
    if peak > 0:
        try:
            drawdown = check_drawdown_status(portfolio_value + cash, peak)
        except Exception:
            pass

    total = portfolio_value + cash
    return {
        "positions": positions,
        "portfolio_value": portfolio_value,
        "total_invested": total_invested,
        "cash_available": cash,
        "cash_pct": cash / total if total > 0 else 1.0,
        "clusters": clusters,
        "drawdown": drawdown,
        "held_tickers": held_tickers,
        "total": total,
    }


# ── Persistence tracking ────────────────────────────────────────

def _update_persistence(state: dict, rec_map: dict, held_tickers: set, scan_trigger: str) -> dict:
    ta = state.get("ticker_actions", {})
    now = datetime.now().isoformat()

    # Track held tickers + BUY candidates (for swap persistence)
    track_tickers = set(held_tickers)
    for ticker, rec in rec_map.items():
        if rec.get("action") == "BUY":
            track_tickers.add(ticker)

    for ticker in track_tickers:
        rec = rec_map.get(ticker, {})
        action = rec.get("action", "UNKNOWN")
        score = rec.get("composite_score", 0)

        if ticker in ta and ta[ticker].get("action") == action:
            ta[ticker]["scan_count"] = ta[ticker].get("scan_count", 0) + 1
            if scan_trigger == "eod":
                ta[ticker]["eod_count"] = ta[ticker].get("eod_count", 0) + 1
            ta[ticker]["last_score"] = score
        else:
            ta[ticker] = {
                "action": action, "first_seen": now,
                "scan_count": 1, "eod_count": 1 if scan_trigger == "eod" else 0,
                "last_score": score,
            }

    # Clean up tickers no longer relevant
    for ticker in list(ta.keys()):
        if ticker not in track_tickers:
            del ta[ticker]

    state["ticker_actions"] = ta
    return state


# ── Turnover checks ─────────────────────────────────────────────

def _check_turnover(state: dict, config: dict) -> dict:
    turnover = state.get("turnover", {})
    today = datetime.now().strftime("%Y-%m-%d")

    # Reset daily swap count
    if turnover.get("swap_date") != today:
        turnover["swaps_today"] = 0
        turnover["swap_date"] = today

    # Reset weekly trim counts
    current_week = datetime.now().strftime("%G-W%V")
    trims = turnover.get("trims_this_week", {})
    for ticker in list(trims.keys()):
        if trims[ticker].get("week_iso") != current_week:
            del trims[ticker]
    turnover["trims_this_week"] = trims

    max_swaps = config.get("suggest_swap_to_fund_buy", {}).get("max_swaps_per_day", 1)
    return {
        "can_swap": turnover.get("swaps_today", 0) < max_swaps,
        "turnover": turnover,
    }


def _check_min_hold(state: dict, ticker: str, config: dict, is_risk: bool = False) -> bool:
    if is_risk:
        return True
    min_days = config.get("turnover", {}).get("min_hold_trading_days", 3)
    last_trade = state.get("turnover", {}).get("last_trade_dates", {}).get(ticker)
    if not last_trade:
        return True  # No record, assume held long enough
    try:
        trade_date = datetime.strptime(last_trade, "%Y-%m-%d")
        return (datetime.now() - trade_date).days >= min_days
    except Exception:
        return True


def _can_trim(state: dict, ticker: str, config: dict) -> bool:
    max_trims = config.get("turnover", {}).get("max_trims_per_week_per_position", 2)
    trims = state.get("turnover", {}).get("trims_this_week", {})
    current_week = datetime.now().strftime("%G-W%V")
    entry = trims.get(ticker, {})
    if entry.get("week_iso") != current_week:
        return True
    return entry.get("count", 0) < max_trims


# ── Suggestion generators ───────────────────────────────────────

def _evaluate_risk_actions(ctx: dict, rec_map: dict, state: dict, config: dict) -> list[AdvisorSuggestion]:
    suggestions = []
    risk_cfg = {}
    try:
        from stockpulse.config.settings import load_strategies
        risk_cfg = load_strategies().get("risk", {})
    except Exception:
        pass

    max_pos_pct = risk_cfg.get("max_position_pct", 8) / 100.0

    for pos in ctx["positions"]:
        ticker = pos["ticker"]
        rec = rec_map.get(ticker, {})
        action = rec.get("action", "UNKNOWN")
        score = rec.get("composite_score", 0)
        ta = state.get("ticker_actions", {}).get(ticker, {})

        # 1. SELL -> EXIT (urgent)
        if action == "SELL" and config.get("suggest_exit_on_sell", True):
            pnl_pct = pos.get("pnl_pct", 0)
            suggestions.append(AdvisorSuggestion(
                severity=Severity.URGENT,
                suggestion_type=SuggestionType.EXIT,
                ticker=ticker,
                action="SELL",
                score=score,
                confidence=rec.get("confidence", 0),
                summary=f"EXIT {ticker}: Signal dropped to SELL ({score:+.1f}). Full exit recommended.",
                details=(
                    f"Current P&L: {pnl_pct:+.1f}%. "
                    f"Value: ${pos.get('current_value', 0):,.0f}. "
                    f"Thesis: {rec.get('thesis', 'Signal deteriorated')}"
                ),
                suggested_amount=pos.get("current_value", 0),
            ))
            continue

        # 2. Persistent CAUTION -> TRIM
        trim_cfg = config.get("suggest_trim_on_caution", {})
        if action == "CAUTION" and trim_cfg.get("enabled", True):
            persist_needed = trim_cfg.get("require_persistence_scans", 2)
            scan_count = ta.get("scan_count", 0)
            eod_count = ta.get("eod_count", 0)

            if eod_count >= 1 or scan_count >= persist_needed * 3:
                if _check_min_hold(state, ticker, config) and _can_trim(state, ticker, config):
                    frac = trim_cfg.get("trim_fraction", 0.25)
                    # Trim more aggressively for very negative scores
                    if score < -50:
                        frac = min(frac * 2, 0.50)
                    trim_val = pos.get("current_value", 0) * frac
                    suggestions.append(AdvisorSuggestion(
                        severity=Severity.ACTIONABLE,
                        suggestion_type=SuggestionType.TRIM_CAUTION,
                        ticker=ticker,
                        action="TRIM",
                        score=score,
                        confidence=rec.get("confidence", 0),
                        summary=f"TRIM {ticker}: CAUTION persisted {scan_count} scans. Reduce by {frac:.0%}.",
                        details=(
                            f"Score: {score:+.1f} (persisted {scan_count} scans, {eod_count} EOD). "
                            f"Trim ${trim_val:,.0f} ({frac:.0%} of ${pos.get('current_value', 0):,.0f}). "
                            f"P&L: {pos.get('pnl_pct', 0):+.1f}%."
                        ),
                        suggested_amount=trim_val,
                        trim_fraction=frac,
                        persistence_count=scan_count,
                    ))

        # 3. Concentration breach -> TRIM (skip ETFs)
        if ctx["total"] > 0 and not _is_etf(ticker):
            pos_weight = pos.get("current_value", 0) / ctx["total"]
            if pos_weight > max_pos_pct * 1.1:  # 10% buffer before flagging
                target_val = ctx["total"] * max_pos_pct
                trim_val = pos.get("current_value", 0) - target_val
                if trim_val > 50 and _can_trim(state, ticker, config):
                    suggestions.append(AdvisorSuggestion(
                        severity=Severity.ACTIONABLE,
                        suggestion_type=SuggestionType.TRIM_CONCENTRATION,
                        ticker=ticker,
                        action="TRIM",
                        score=score,
                        summary=f"TRIM {ticker}: Position is {pos_weight:.1%} of portfolio (cap: {max_pos_pct:.0%}).",
                        details=f"Trim ${trim_val:,.0f} to bring back to {max_pos_pct:.0%} target.",
                        suggested_amount=trim_val,
                        trim_fraction=trim_val / pos.get("current_value", 1),
                    ))

    # 4. Drawdown alerts
    dd = ctx.get("drawdown", {})
    dd_pct = dd.get("drawdown_pct", 0)
    if dd.get("new_buys_paused", False):
        suggestions.append(AdvisorSuggestion(
            severity=Severity.URGENT,
            suggestion_type=SuggestionType.RISK_ALERT,
            ticker="PORTFOLIO",
            action="PAUSE",
            summary=f"DRAWDOWN BREAKER: Portfolio down {dd_pct:.1f}%. New buys paused.",
            details="Drawdown exceeds pause threshold. Focus on risk reduction.",
        ))
    elif dd.get("size_multiplier", 1.0) < 1.0:
        suggestions.append(AdvisorSuggestion(
            severity=Severity.ACTIONABLE,
            suggestion_type=SuggestionType.RISK_ALERT,
            ticker="PORTFOLIO",
            action="REDUCE",
            summary=f"DRAWDOWN WARNING: Portfolio down {dd_pct:.1f}%. Position sizes halved.",
            details="Drawdown crossed half-size threshold. New positions at 50% normal size.",
        ))

    return suggestions


def _evaluate_deployment(ctx: dict, rec_map: dict, state: dict, config: dict,
                         freed_cash: float) -> list[AdvisorSuggestion]:
    """Priority 2: Deploy cash into BUY candidates using allocator's rules."""
    from stockpulse.portfolio.allocation import check_buy_eligible, compute_buy_size
    from stockpulse.config.settings import load_strategies

    suggestions = []

    if ctx["drawdown"].get("new_buys_paused", False):
        return suggestions

    from stockpulse.portfolio.allocation import get_size_limits

    risk_cfg = load_strategies().get("risk", {})
    limits = get_size_limits(ctx["total"], risk_cfg)
    cash_min_pct = config.get("cash_reserve_min", 0.12)
    cash_min = cash_min_pct * ctx["total"]
    deployable = ctx["cash_available"] + freed_cash - cash_min
    max_positions = limits["max_positions"]

    buy_candidates = []
    for ticker, rec in rec_map.items():
        if rec.get("action") == "BUY" and ticker not in ctx["held_tickers"]:
            buy_candidates.append(rec)
    buy_candidates.sort(key=lambda r: r.get("composite_score", 0), reverse=True)

    size_mult = ctx["drawdown"].get("size_multiplier", 1.0)

    for rec in buy_candidates[:5]:
        ticker = rec["ticker"]
        score = rec.get("composite_score", 0)

        risk_check = check_buy_eligible(rec, ctx["positions"], ctx["total"],
                                         ctx["held_tickers"], max_positions)
        if risk_check is None:
            continue

        if deployable > 50:
            # Weekly trend filter: reduce size if weekly trend is down
            weekly_mult = 1.0
            try:
                from stockpulse.signals.weekly import assess_weekly_trend
                from stockpulse.data.provider import get_price_history as _gph
                wk_df = _gph(ticker, period="1y")
                if not wk_df.empty:
                    weekly = assess_weekly_trend(wk_df)
                    weekly_mult = weekly.get("size_multiplier", 1.0)
            except Exception:
                pass

            full_dollars = compute_buy_size(ctx["total"], score, risk_cfg,
                                            size_mult * risk_check.get("size_multiplier", 1.0) * weekly_mult)
            amount = min(full_dollars, deployable)
            if amount < 50:
                continue

            suggestions.append(AdvisorSuggestion(
                severity=Severity.ACTIONABLE,
                suggestion_type=SuggestionType.BUY_FROM_CASH,
                ticker=ticker,
                action="BUY",
                score=score,
                confidence=rec.get("confidence", 0),
                summary=f"BUY {ticker}: Deploy ${amount:,.0f} from cash. Score {score:+.1f}.",
                details=(
                    f"Signal: BUY ({rec.get('confidence', 0)}% confidence). "
                    f"Sector: {risk_check.get('sector', 'N/A')}. "
                    f"Leaves ${max(0, deployable - amount):,.0f} deployable cash. "
                    f"Thesis: {rec.get('thesis', '')}"
                ),
                suggested_amount=amount,
            ))
            deployable -= amount
        else:
            swap = _evaluate_swap(ctx, rec_map, state, config, ticker, rec)
            if swap:
                suggestions.append(swap)
            break

    return suggestions


def _evaluate_swap(ctx: dict, rec_map: dict, state: dict, config: dict,
                   incoming_ticker: str, incoming_rec: dict) -> AdvisorSuggestion | None:
    swap_cfg = config.get("suggest_swap_to_fund_buy", {})
    if not swap_cfg.get("enabled", True):
        return None

    # Never swap into WATCHLIST
    if config.get("never_swap_into_watchlist", True) and incoming_rec.get("action") != "BUY":
        return None

    incoming_score = incoming_rec.get("composite_score", 0)
    min_score = swap_cfg.get("incoming_min_score", 60)
    if incoming_score < min_score:
        return None

    # Check persistence
    ta = state.get("ticker_actions", {}).get(incoming_ticker, {})
    persist_needed = swap_cfg.get("require_persistence_scans", 2)
    if ta.get("scan_count", 0) < persist_needed:
        return None

    # Check turnover budget
    turnover_info = _check_turnover(state, config)
    if not turnover_info["can_swap"]:
        return None

    # Find best outgoing candidate
    outgoing_max = swap_cfg.get("outgoing_max_tier", "HOLD")
    allowed_tiers = {"HOLD", "CAUTION", "SELL"}
    if outgoing_max == "HOLD":
        allowed_tiers = {"HOLD", "CAUTION", "SELL"}
    elif outgoing_max == "CAUTION":
        allowed_tiers = {"CAUTION", "SELL"}

    min_gap = swap_cfg.get("min_score_gap", 20)
    require_diff_cluster = swap_cfg.get("require_different_cluster", True)

    # Get incoming cluster
    incoming_cluster = set()
    for cluster_id, members in ctx.get("clusters", {}).items():
        if incoming_ticker in members:
            incoming_cluster = set(members)
            break

    best_out = None
    best_out_score = float("inf")

    for pos in ctx["positions"]:
        out_ticker = pos["ticker"]
        out_rec = rec_map.get(out_ticker, {})
        out_action = out_rec.get("action", "UNKNOWN")
        out_score = out_rec.get("composite_score", 0)

        if out_action not in allowed_tiers:
            continue

        gap = incoming_score - out_score
        if gap < min_gap:
            continue

        if not _check_min_hold(state, out_ticker, config):
            continue

        # Cluster check
        if require_diff_cluster and out_ticker in incoming_cluster:
            continue

        if out_score < best_out_score:
            best_out = pos
            best_out_score = out_score

    if not best_out:
        return None

    gap = incoming_score - best_out_score
    return AdvisorSuggestion(
        severity=Severity.ACTIONABLE,
        suggestion_type=SuggestionType.SWAP,
        ticker=incoming_ticker,
        action="SWAP",
        score=incoming_score,
        confidence=incoming_rec.get("confidence", 0),
        summary=(
            f"SWAP {best_out['ticker']} -> {incoming_ticker}: "
            f"Score gap {gap:+.1f}. Improves diversification."
        ),
        details=(
            f"Sell {best_out['ticker']} (score {best_out_score:+.1f}, "
            f"P&L {best_out.get('pnl_pct', 0):+.1f}%) to fund "
            f"{incoming_ticker} (BUY {incoming_score:+.1f}). "
            f"Frees ${best_out.get('current_value', 0):,.0f}. "
            f"Persisted {state.get('ticker_actions', {}).get(incoming_ticker, {}).get('scan_count', 0)} scans."
        ),
        suggested_amount=best_out.get("current_value", 0),
        swap_out_ticker=best_out["ticker"],
        swap_out_score=best_out_score,
        swap_score_gap=gap,
    )


def _evaluate_watchlist(ctx: dict, rec_map: dict, state: dict, config: dict) -> list[AdvisorSuggestion]:
    """Priority 3: WATCHLIST starters from excess cash, using allocator's qualifiers."""
    from stockpulse.portfolio.allocation import (
        check_watchlist_starter_eligible, compute_buy_size, compute_starter_size,
    )
    from stockpulse.config.settings import load_strategies

    suggestions = []

    if not config.get("allow_watchlist_starters", True):
        return suggestions

    strat = load_strategies()
    alloc_cfg = strat.get("allocation", {})
    risk_cfg = strat.get("risk", {})

    cash_min_pct = config.get("cash_reserve_min", 0.12)
    cash_min = cash_min_pct * ctx["total"]
    excess_cash = ctx["cash_available"] - cash_min
    max_wl_sleeve = alloc_cfg.get("max_watchlist_sleeve", 0.25) * ctx["total"]
    max_wl_names = alloc_cfg.get("max_watchlist_names", 3)

    if excess_cash <= 50:
        return suggestions

    wl_candidates = []
    for ticker, rec in rec_map.items():
        if rec.get("action") == "WATCHLIST" and ticker not in ctx["held_tickers"]:
            wl_candidates.append(rec)
    wl_candidates.sort(key=lambda r: r.get("composite_score", 0), reverse=True)

    clusters_used: set = set()
    wl_allocated = 0.0
    wl_count = 0

    for rec in wl_candidates[:15]:
        if wl_count >= max_wl_names or wl_allocated >= max_wl_sleeve:
            break

        ticker = rec["ticker"]
        score = rec.get("composite_score", 0)

        # Use the same 7 qualifiers as the allocator
        check = check_watchlist_starter_eligible(
            rec, ctx["positions"], ctx["total"], ctx["held_tickers"],
            alloc_cfg, clusters_used,
        )
        if not check["eligible"]:
            continue

        # Size using allocator's function
        full_dollars = compute_buy_size(ctx["total"], score, risk_cfg)
        starter_dollars = compute_starter_size(
            full_dollars, alloc_cfg,
            remaining=excess_cash,
            sleeve_remaining=max_wl_sleeve - wl_allocated,
        )

        if starter_dollars < 50:
            continue

        suggestions.append(AdvisorSuggestion(
            severity=Severity.ACTIONABLE,
            suggestion_type=SuggestionType.WATCHLIST_STARTER,
            ticker=ticker,
            action="WATCH",
            score=score,
            confidence=rec.get("confidence", 0),
            summary=f"STARTER {ticker}: Deploy ${starter_dollars:,.0f} from excess cash (WATCHLIST {score:+.1f}).",
            details=(
                f"Passes all 7 starter qualifiers. 33% of full position. "
                f"Thesis: {rec.get('thesis', '')}. "
                f"Remaining excess cash: ${max(0, excess_cash - starter_dollars):,.0f}."
            ),
            suggested_amount=starter_dollars,
        ))
        excess_cash -= starter_dollars
        wl_allocated += starter_dollars
        wl_count += 1
        clusters_used.update(check.get("cluster_key", set()))

    return suggestions


# ── Post-processing ──────────────────────────────────────────────

def _evaluate_near_misses(ctx: dict, rec_map: dict, state: dict, config: dict,
                          already_suggested: set) -> list[AdvisorSuggestion]:
    """Informational: tickers close to qualifying but missing one or two checks.
    No dollar amounts. Looser than allocator rules."""
    from stockpulse.portfolio.allocation import check_watchlist_starter_eligible
    from stockpulse.config.settings import load_strategies

    suggestions = []
    alloc_cfg = load_strategies().get("allocation", {})

    candidates = []
    for ticker, rec in rec_map.items():
        if ticker in ctx["held_tickers"] or ticker in already_suggested:
            continue
        if rec.get("action") in ("WATCHLIST", "HOLD"):
            score = rec.get("composite_score", 0)
            if score >= 20:  # Lower bar than allocator
                candidates.append(rec)
    candidates.sort(key=lambda r: r.get("composite_score", 0), reverse=True)

    for rec in candidates[:5]:
        ticker = rec["ticker"]
        score = rec.get("composite_score", 0)

        check = check_watchlist_starter_eligible(
            rec, ctx["positions"], ctx["total"], ctx["held_tickers"], alloc_cfg,
            clusters_used=set(),
        )

        if check["eligible"]:
            continue  # Already eligible — would be in watchlist starters
        if not check.get("near_miss", False):
            continue  # Not close enough

        detail = check.get("near_miss_detail", check.get("reason", ""))
        suggestions.append(AdvisorSuggestion(
            severity=Severity.INFORMATIONAL,
            suggestion_type=SuggestionType.NEAR_MISS,
            ticker=ticker,
            action="WATCH",
            score=score,
            confidence=rec.get("confidence", 0),
            summary=f"{ticker} is improving but not yet starter-eligible: {detail}.",
            details=(
                f"Score: {score:+.1f}. Action: {rec.get('action', 'HOLD')}. "
                f"Missing: {check.get('reason', 'unknown')}. "
                f"Thesis: {rec.get('thesis', '')[:200]}"
            ),
        ))

    return suggestions


def _add_tax_annotations(suggestions: list[AdvisorSuggestion], ctx: dict, config: dict, state: dict) -> list[AdvisorSuggestion]:
    if not config.get("taxable_account_show_tax_impact", True):
        return suggestions

    from stockpulse.portfolio.lots import compute_tax_impact, check_wash_sale

    for s in suggestions:
        if s.suggestion_type in (SuggestionType.EXIT, SuggestionType.TRIM_CAUTION,
                                  SuggestionType.TRIM_CONCENTRATION, SuggestionType.SWAP):
            sell_ticker = s.swap_out_ticker or s.ticker
            pos = next((p for p in ctx["positions"] if p["ticker"] == sell_ticker), None)
            if pos:
                current_price = pos.get("current_price", 0)
                # Use lot-level tax computation
                if s.suggestion_type == SuggestionType.EXIT:
                    shares_to_sell = pos.get("shares", 0)
                elif s.trim_fraction:
                    shares_to_sell = pos.get("shares", 0) * s.trim_fraction
                else:
                    shares_to_sell = pos.get("shares", 0) * 0.25

                try:
                    tax = compute_tax_impact(sell_ticker, shares_to_sell, current_price)
                    parts = []
                    if tax["short_term_gain"] != 0:
                        gl = "gain" if tax["short_term_gain"] >= 0 else "loss"
                        parts.append(f"short-term {gl}: ${abs(tax['short_term_gain']):,.0f}")
                    if tax["long_term_gain"] != 0:
                        gl = "gain" if tax["long_term_gain"] >= 0 else "loss"
                        parts.append(f"long-term {gl}: ${abs(tax['long_term_gain']):,.0f}")
                    if parts:
                        s.tax_impact_note = " | ".join(parts)
                    if tax.get("lots_detail"):
                        lot_count = len(tax["lots_detail"])
                        if lot_count > 1:
                            s.tax_impact_note = (s.tax_impact_note or "") + f" ({lot_count} lots, FIFO)"
                except Exception:
                    # Fallback to simple calculation
                    pnl_pct = pos.get("pnl_pct", 0)
                    entry_date = pos.get("entry_date", "")
                    try:
                        ed = datetime.strptime(entry_date, "%Y-%m-%d")
                        holding_days = (datetime.now() - ed).days
                        term = "long-term" if holding_days >= 365 else "short-term"
                        gl = "gain" if pnl_pct >= 0 else "loss"
                        s.tax_impact_note = f"{term} {gl} ({pnl_pct:+.1f}%, held {holding_days}d)"
                    except Exception:
                        pass

        # Wash sale warning for BUY suggestions — uses lot-level history
        if config.get("show_wash_sale_warning", True) and s.suggestion_type == SuggestionType.BUY_FROM_CASH:
            try:
                wash = check_wash_sale(s.ticker)
                if wash["wash_sale"]:
                    s.wash_sale_warning = True
                    s.tax_impact_note = (s.tax_impact_note or "") + f" | WASH SALE WARNING: sold at loss on {wash['sold_at']}"
            except Exception:
                pass

    return suggestions


def _detect_state_changes(suggestions: list[AdvisorSuggestion], state: dict) -> list[AdvisorSuggestion]:
    dispatched = state.get("dispatched_hashes", {})
    acknowledged = set(state.get("acknowledged_hashes", []))

    result = []
    for s in suggestions:
        if s.hash in acknowledged:
            continue
        s.is_new = s.hash not in dispatched
        result.append(s)

    return result


# ── Public API ───────────────────────────────────────────────────

def evaluate(recommendations: list[dict], scan_trigger: str = "manual") -> list[AdvisorSuggestion]:
    """Main entry point. Returns sorted suggestions. Updates state file."""
    config = _get_config()
    if not config.get("evaluate_after_every_scan", True) and scan_trigger != "manual":
        return []

    state = _load_state()
    rec_map = {r["ticker"]: r for r in recommendations}
    ctx = _get_portfolio_context(rec_map)

    # Update persistence tracking
    state = _update_persistence(state, rec_map, ctx["held_tickers"], scan_trigger)

    # Detect market regime
    regime = None
    try:
        from stockpulse.signals.market_regime import detect_regime
        regime = detect_regime()
        if regime and regime.get("adjustment"):
            adj = regime["adjustment"]
            # Adjust cash reserve based on market conditions
            config = dict(config)  # don't mutate original
            base_reserve = config.get("cash_reserve_min", 0.12)
            config["cash_reserve_min"] = base_reserve * adj.get("cash_reserve_mult", 1.0)
    except Exception:
        logger.debug("Market regime detection failed, using defaults")

    # Record patterns for historical matching
    try:
        from stockpulse.research.patterns import record_pattern
        for rec in recommendations:
            if rec.get("action") in ("BUY", "WATCHLIST") and rec.get("signals"):
                record_pattern(rec)
    except Exception:
        pass

    # 1. Risk actions
    risk_suggestions = _evaluate_risk_actions(ctx, rec_map, state, config)

    # Estimate freed cash from trims
    freed_cash = sum(
        (s.suggested_amount or 0) for s in risk_suggestions
        if s.suggestion_type in (SuggestionType.TRIM_CAUTION, SuggestionType.TRIM_CONCENTRATION)
    )

    # 2. Deployment (uses cash_available + freed_cash)
    deploy_suggestions = _evaluate_deployment(ctx, rec_map, state, config, freed_cash)

    # 3. Watchlist — chain cash: subtract what deployment already consumed
    deployed_cash = sum(s.suggested_amount or 0 for s in deploy_suggestions)
    ctx_for_wl = dict(ctx)
    ctx_for_wl["cash_available"] = max(0, ctx["cash_available"] + freed_cash - deployed_cash)
    watchlist_suggestions = _evaluate_watchlist(ctx_for_wl, rec_map, state, config)

    # 4. Near-misses (informational only, no dollar amounts)
    already_suggested = {s.ticker for s in risk_suggestions + deploy_suggestions + watchlist_suggestions}
    near_miss_suggestions = _evaluate_near_misses(ctx, rec_map, state, config, already_suggested)

    # Combine, sort by severity then type
    all_suggestions = risk_suggestions + deploy_suggestions + watchlist_suggestions + near_miss_suggestions
    all_suggestions.sort(key=lambda s: (_SEVERITY_ORDER.get(s.severity, 9), _TYPE_ORDER.get(s.suggestion_type, 9)))

    # Add pricing, entry timing, and pattern matching to all suggestions
    for s in all_suggestions:
        # Current price + stop price for all suggestions
        try:
            from stockpulse.data.provider import get_current_quote
            quote = get_current_quote(s.ticker)
            s.current_price = quote.get("price", 0) if quote else None
        except Exception:
            pass

        # Entry target and stop from invalidation data
        rec = rec_map.get(s.ticker, {})
        inv = rec.get("invalidation", "")
        if isinstance(inv, str) and "Stop:" in inv:
            try:
                stop_str = inv.split("Stop:")[1].split("|")[0].strip().replace("$", "").split(" ")[0]
                s.stop_price = round(float(stop_str), 2)
            except Exception:
                pass

        # Entry target from timing or EMA
        if s.entry_timing and s.entry_timing.get("target_price"):
            s.entry_target = s.entry_timing["target_price"]
        elif s.current_price:
            s.entry_target = s.current_price  # At market

        if s.severity in (Severity.URGENT, Severity.ACTIONABLE) and s.suggested_amount:
            # Entry timing
            try:
                from stockpulse.portfolio.entry_timing import assess_entry_timing
                from stockpulse.data.provider import get_price_history
                df = get_price_history(s.ticker, period="6mo")
                if not df.empty:
                    s.entry_timing = assess_entry_timing(s.ticker, df, s.action)
                    if s.entry_timing.get("target_price"):
                        s.entry_target = s.entry_timing["target_price"]
            except Exception:
                pass

            # Pattern matching
            try:
                from stockpulse.research.patterns import find_similar_patterns
                if rec.get("signals"):
                    s.pattern_match = find_similar_patterns(s.ticker, rec["signals"])
            except Exception:
                pass

        # Tag with regime
        if regime:
            s.regime = regime.get("regime")

    # Tax annotations
    all_suggestions = _add_tax_annotations(all_suggestions, ctx, config, state)

    # State-change detection
    all_suggestions = _detect_state_changes(all_suggestions, state)

    # Save state
    state["current_suggestions"] = [s.to_dict() for s in all_suggestions]
    state["last_run"] = datetime.now().isoformat()
    state["scan_trigger"] = scan_trigger
    for s in all_suggestions:
        if s.hash not in state.get("dispatched_hashes", {}):
            state.setdefault("dispatched_hashes", {})[s.hash] = datetime.now().isoformat()
    _save_state(state)

    logger.info(
        "Advisor: %d suggestions (%d urgent, %d actionable, %d info)",
        len(all_suggestions),
        sum(1 for s in all_suggestions if s.severity == Severity.URGENT),
        sum(1 for s in all_suggestions if s.severity == Severity.ACTIONABLE),
        sum(1 for s in all_suggestions if s.severity == Severity.INFORMATIONAL),
    )

    return all_suggestions


def generate_eod_plan(recommendations: list[dict]) -> dict:
    """Generate a consolidated end-of-day portfolio plan.

    Unlike evaluate(), this resolves conflicts and produces a single
    ranked plan with net cash impact and a narrative summary.
    """
    config = _get_config()

    suggestions = evaluate(recommendations, scan_trigger="eod")

    # Reload state AFTER evaluate() since it saves updated suggestions
    state = _load_state()

    # Categorize
    exits = [s for s in suggestions if s.suggestion_type == SuggestionType.EXIT]
    trims = [s for s in suggestions if s.suggestion_type in (SuggestionType.TRIM_CAUTION, SuggestionType.TRIM_CONCENTRATION)]
    buys = [s for s in suggestions if s.suggestion_type == SuggestionType.BUY_FROM_CASH]
    swaps = [s for s in suggestions if s.suggestion_type == SuggestionType.SWAP]
    starters = [s for s in suggestions if s.suggestion_type == SuggestionType.WATCHLIST_STARTER]
    near_misses = [s for s in suggestions if s.suggestion_type == SuggestionType.NEAR_MISS]
    risk_alerts = [s for s in suggestions if s.suggestion_type == SuggestionType.RISK_ALERT]

    # Compute net cash impact
    cash_freed = sum(s.suggested_amount or 0 for s in exits + trims)
    cash_deployed = sum(s.suggested_amount or 0 for s in buys + starters)
    net_cash = cash_freed - cash_deployed

    # Build sections
    sections = []
    if risk_alerts:
        sections.append({
            "title": "Risk Alerts",
            "items": [s.to_dict() for s in risk_alerts],
        })
    if exits:
        sections.append({
            "title": "Suggested Exits",
            "items": [s.to_dict() for s in exits],
        })
    if trims:
        sections.append({
            "title": "Suggested Trims",
            "items": [s.to_dict() for s in trims],
        })
    if buys:
        sections.append({
            "title": "New Buys from Cash",
            "items": [s.to_dict() for s in buys],
        })
    if swaps:
        sections.append({
            "title": "Swap Opportunities",
            "items": [s.to_dict() for s in swaps],
        })
    if starters:
        sections.append({
            "title": "Watchlist Starters",
            "items": [s.to_dict() for s in starters],
        })
    if near_misses:
        sections.append({
            "title": "Near-Miss Candidates",
            "items": [s.to_dict() for s in near_misses],
        })

    # Build narrative summary
    parts = []
    if exits:
        parts.append(f"Exit {', '.join(s.ticker for s in exits)} (frees ${sum(s.suggested_amount or 0 for s in exits):,.0f})")
    if trims:
        parts.append(f"Trim {', '.join(s.ticker for s in trims)} (frees ${sum(s.suggested_amount or 0 for s in trims):,.0f})")
    if buys:
        parts.append(f"Buy {', '.join(s.ticker for s in buys)} (deploys ${sum(s.suggested_amount or 0 for s in buys):,.0f})")
    if swaps:
        for sw in swaps:
            parts.append(f"Swap {sw.swap_out_ticker} -> {sw.ticker}")
    if starters:
        parts.append(f"Start {', '.join(s.ticker for s in starters)} (deploys ${sum(s.suggested_amount or 0 for s in starters):,.0f})")
    if near_misses:
        parts.append(f"Watch {', '.join(s.ticker for s in near_misses)} (near-miss)")
    if not parts:
        parts.append("No changes recommended. Portfolio looks good.")

    plan = {
        "timestamp": datetime.now().isoformat(),
        "summary": ". ".join(parts) + ".",
        "net_cash_impact": round(net_cash, 2),
        "cash_freed": round(cash_freed, 2),
        "cash_deployed": round(cash_deployed, 2),
        "total_suggestions": len(suggestions),
        "urgent_count": sum(1 for s in suggestions if s.severity == Severity.URGENT),
        "actionable_count": sum(1 for s in suggestions if s.severity == Severity.ACTIONABLE),
        "info_count": sum(1 for s in suggestions if s.severity == Severity.INFORMATIONAL),
        "sections": sections,
        "all_suggestions": [s.to_dict() for s in suggestions],
    }

    # Persist EOD plan
    state["eod_plan"] = plan
    _save_state(state)

    return plan


def get_latest_suggestions() -> dict:
    """Read current suggestions from state file."""
    state = _load_state()
    # Get current regime
    regime = None
    try:
        from stockpulse.signals.market_regime import detect_regime
        regime = detect_regime()
    except Exception:
        pass
    return {
        "suggestions": state.get("current_suggestions", []),
        "last_run": state.get("last_run"),
        "scan_trigger": state.get("scan_trigger"),
        "regime": regime,
    }


def acknowledge_suggestion(suggestion_hash: str) -> bool:
    """Mark a suggestion as dismissed."""
    state = _load_state()
    ack = state.get("acknowledged_hashes", [])
    if suggestion_hash not in ack:
        ack.append(suggestion_hash)
        state["acknowledged_hashes"] = ack
        # Remove from current suggestions
        state["current_suggestions"] = [
            s for s in state.get("current_suggestions", [])
            if s.get("hash") != suggestion_hash
        ]
        _save_state(state)
        return True
    return False
