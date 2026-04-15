"""Shared allocation logic — used by both the allocator endpoint and the advisor.

Extracts the qualifier checks and sizing functions so both paths
use identical rules. The expert's principle: actionable suggestions
must pass the same checks as the allocator.
"""
import logging

logger = logging.getLogger(__name__)


def check_buy_eligible(rec: dict, positions: list[dict], portfolio_value: float,
                       held_tickers: set, max_positions: int) -> dict | None:
    """Check if a BUY candidate passes all rules. Returns risk_check or None."""
    from stockpulse.portfolio.risk import check_concentration_limits

    ticker = rec["ticker"]
    if len(positions) >= max_positions and ticker not in held_tickers:
        return None

    risk_check = check_concentration_limits(ticker, positions, portfolio_value)
    if not risk_check["allowed"] and ticker not in held_tickers:
        return None

    return risk_check


def check_watchlist_starter_eligible(rec: dict, positions: list[dict],
                                     portfolio_value: float, held_tickers: set,
                                     alloc_cfg: dict,
                                     clusters_used: set | None = None) -> dict:
    """Check if a WATCHLIST candidate passes all 7 starter qualifiers.

    Returns {"eligible": bool, "risk_check": dict, "reason": str, "cluster_key": frozenset}
    """
    from stockpulse.portfolio.risk import check_concentration_limits

    ticker = rec["ticker"]
    score = rec.get("composite_score", 0)
    min_score = alloc_cfg.get("watchlist_starter_min_score", 30)

    if score < min_score:
        return {"eligible": False, "reason": f"score {score:.1f} < {min_score}", "near_miss": False}

    # Requirement 1: trend bucket must confirm
    confirmation = rec.get("confirmation", {})
    trend_confirms = confirmation.get("buckets", {}).get("trend", {}).get("confirms", False)
    if not trend_confirms:
        return {"eligible": False, "reason": "trend bucket not confirming", "near_miss": True,
                "near_miss_detail": "missing trend confirmation"}

    # Requirement 2: relative strength score >= 60
    rs_score = rec.get("signals", {}).get("relative_strength", {}).get("score", 0)
    if rs_score < 60:
        return {"eligible": False, "reason": f"RS {rs_score:.0f} < 60", "near_miss": True,
                "near_miss_detail": f"relative strength {rs_score:.0f}/60"}

    # Requirement 3: no earnings blackout
    earnings_score = rec.get("signals", {}).get("earnings", {}).get("score", 0)
    if earnings_score <= -30:
        return {"eligible": False, "reason": "earnings blackout", "near_miss": False}

    # Requirement 4: concentration limits must pass
    risk_check = check_concentration_limits(ticker, positions, portfolio_value)
    if not risk_check["allowed"] and ticker not in held_tickers:
        return {"eligible": False, "reason": "concentration limits", "risk_check": risk_check, "near_miss": False}

    # Requirement 5: max 1 per cluster
    cluster_tickers = risk_check.get("cluster_tickers", [])
    cluster_key = frozenset(cluster_tickers + [ticker])
    if clusters_used is not None:
        if any(c in clusters_used for c in cluster_key):
            return {"eligible": False, "reason": "cluster overlap", "near_miss": False}

    # Requirement 6: price above 20 EMA
    signals = rec.get("signals", {})
    ma_signals = signals.get("moving_averages", {})
    price_above_20ema = ma_signals.get("price_above_20ema", None)
    if price_above_20ema is None:
        thesis_text = rec.get("thesis", "").lower()
        price_above_20ema = "below 20" not in thesis_text and "under 20 ema" not in thesis_text
    if not price_above_20ema:
        return {"eligible": False, "reason": "price below 20 EMA", "near_miss": True,
                "near_miss_detail": "price below 20 EMA"}

    # Requirement 7: not invalidated
    if rec.get("invalidated", False):
        return {"eligible": False, "reason": "invalidated", "near_miss": False}

    return {"eligible": True, "risk_check": risk_check, "cluster_key": cluster_key,
            "reason": None, "near_miss": False}


def compute_buy_size(portfolio_value: float, score: float, risk_cfg: dict,
                     size_multiplier: float = 1.0) -> float:
    """Compute full BUY position size in dollars."""
    max_pct = risk_cfg.get("max_position_pct", 8) / 100.0
    score_factor = min(abs(score) / 55, 1.0)
    return portfolio_value * max_pct * score_factor * size_multiplier


def compute_starter_size(full_dollars: float, alloc_cfg: dict,
                         remaining: float = float("inf"),
                         sleeve_remaining: float = float("inf")) -> float:
    """Compute WATCHLIST starter size (33% of full by default)."""
    ratio = alloc_cfg.get("watchlist_starter_size", 0.33)
    return round(min(full_dollars * ratio, remaining, sleeve_remaining), 2)
