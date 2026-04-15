"""Portfolio risk management -- concentration limits, clustering, drawdown breaker."""

import logging
import math
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from stockpulse.config.settings import get_config, load_strategies, load_portfolio
from stockpulse.data.provider import get_price_history, get_earnings_dates
from stockpulse.data.cache import get_cached, set_cached

logger = logging.getLogger(__name__)


def _get_ticker_info(ticker: str) -> dict:
    """Get sector and industry for a ticker via yfinance."""
    cache_key = f"ticker_info_{ticker}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached
    try:
        t = yf.Ticker(ticker)
        info = t.info
        result = {
            "sector": info.get("sector", "Unknown"),
            "industry": info.get("industry", "Unknown"),
        }
        set_cached(cache_key, result)
        return result
    except Exception:
        return {"sector": "Unknown", "industry": "Unknown"}


def _compute_correlation(ticker_a: str, ticker_b: str, period: int = 60) -> float:
    """Compute daily return correlation between two tickers over N days."""
    cache_key = f"corr_{min(ticker_a, ticker_b)}_{max(ticker_a, ticker_b)}_{period}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        df_a = get_price_history(ticker_a, period="6mo")
        df_b = get_price_history(ticker_b, period="6mo")

        if df_a.empty or df_b.empty:
            return 0.0

        ret_a = df_a["Close"].pct_change().dropna().tail(period)
        ret_b = df_b["Close"].pct_change().dropna().tail(period)

        # Align on common dates
        common = ret_a.index.intersection(ret_b.index)
        if len(common) < 20:
            return 0.0

        corr = float(ret_a.loc[common].corr(ret_b.loc[common]))
        if math.isnan(corr):
            corr = 0.0

        set_cached(cache_key, corr)
        return corr
    except Exception:
        return 0.0


def get_position_clusters(tickers: list[str]) -> dict[str, list[str]]:
    """Group tickers into clusters based on sub-industry + correlation.

    Two tickers are in the same cluster if:
    - Same GICS sub-industry (industry field from yfinance), OR
    - 60-day daily return correlation >= 0.75

    Returns {cluster_id: [tickers]}.
    """
    if not tickers:
        return {}

    # Get industry info
    info = {t: _get_ticker_info(t) for t in tickers}

    # Build adjacency: same industry or high correlation
    clusters = {}
    cluster_id = 0
    assigned = {}

    for i, t1 in enumerate(tickers):
        if t1 in assigned:
            continue

        # Start new cluster
        cluster = [t1]
        assigned[t1] = cluster_id

        for t2 in tickers[i + 1 :]:
            if t2 in assigned:
                continue

            same_industry = (
                info[t1]["industry"] == info[t2]["industry"]
                and info[t1]["industry"] != "Unknown"
            )

            high_corr = False
            if not same_industry:
                corr = _compute_correlation(t1, t2)
                high_corr = corr >= 0.75

            if same_industry or high_corr:
                cluster.append(t2)
                assigned[t2] = cluster_id

        clusters[f"cluster_{cluster_id}"] = cluster
        cluster_id += 1

    return clusters


def check_concentration_limits(
    candidate_ticker: str,
    current_positions: list[dict],
    portfolio_value: float,
) -> dict:
    """Check if adding a new position would violate concentration limits.

    Returns {
        "allowed": bool,
        "reasons": list[str],  # why blocked (if any)
        "size_multiplier": float,  # 1.0 = full size, 0.5-0.7 = cluster penalty
        "sector": str,
        "industry": str,
        "cluster_tickers": list[str],
    }
    """
    risk_cfg = load_strategies().get("risk", {})
    max_positions = risk_cfg.get("max_positions", 8)
    max_position_pct = risk_cfg.get("max_position_pct", 8)
    max_sector_pct = risk_cfg.get("max_sector_pct", 25)

    reasons = []
    size_multiplier = 1.0

    # Check max positions
    if len(current_positions) >= max_positions:
        reasons.append(f"Max positions ({max_positions}) reached")

    # Get candidate info
    candidate_info = _get_ticker_info(candidate_ticker)
    candidate_sector = candidate_info["sector"]
    candidate_industry = candidate_info["industry"]

    # Check sector concentration
    sector_exposure = 0.0
    industry_exposure = 0.0
    cluster_tickers = []

    for pos in current_positions:
        pos_info = _get_ticker_info(pos["ticker"])
        pos_value = pos["shares"] * pos.get("current_price", pos["entry_price"])
        pos_pct = (pos_value / portfolio_value * 100) if portfolio_value > 0 else 0

        if pos_info["sector"] == candidate_sector:
            sector_exposure += pos_pct

        if (
            pos_info["industry"] == candidate_industry
            and candidate_industry != "Unknown"
        ):
            industry_exposure += pos_pct
            cluster_tickers.append(pos["ticker"])

    # Check correlation-based clustering
    for pos in current_positions:
        if pos["ticker"] not in cluster_tickers:
            corr = _compute_correlation(candidate_ticker, pos["ticker"])
            if corr >= 0.75:
                cluster_tickers.append(pos["ticker"])

    # Sector cap check
    if sector_exposure + max_position_pct > max_sector_pct:
        reasons.append(
            f"Sector '{candidate_sector}' at {sector_exposure:.1f}%, "
            f"adding {max_position_pct}% would exceed {max_sector_pct}% cap"
        )

    # Sub-industry cap check (15%)
    if industry_exposure + max_position_pct > 15:
        reasons.append(
            f"Industry '{candidate_industry}' at {industry_exposure:.1f}%, "
            f"adding would exceed 15% sub-industry cap"
        )

    # Cluster penalty
    if cluster_tickers:
        size_multiplier = 0.6  # reduce position size when adding to cluster

    # Earnings blackout check
    blackout_days = load_strategies().get("risk", {}).get("earnings_blackout_days", 3)
    try:
        earnings = get_earnings_dates(candidate_ticker)
        for e in earnings:
            if 0 <= e.get("days_away", 999) <= blackout_days:
                reasons.append(
                    f"Earnings blackout: {candidate_ticker} reports in "
                    f"{e['days_away']} days"
                )
                break
    except Exception:
        pass

    return {
        "allowed": len(reasons) == 0,
        "reasons": reasons,
        "size_multiplier": size_multiplier,
        "sector": candidate_sector,
        "industry": candidate_industry,
        "cluster_tickers": cluster_tickers,
    }


def compute_position_size(
    portfolio_value: float,
    entry_price: float,
    atr: float,
    confidence: int = 50,
) -> dict:
    """Compute volatility-adjusted position size .

    Base risk per trade = 0.75% of portfolio.
    Confidence can scale 0.75x to 1.25x.
    Uses ATR for stop distance.

    Returns {shares, dollar_amount, risk_dollars, stop_price}.
    """
    risk_cfg = load_strategies().get("risk", {})
    risk_pct = risk_cfg.get("risk_per_trade_pct", 0.75)
    max_pos_pct = risk_cfg.get("max_position_pct", 8)

    # Risk dollars
    risk_dollars = portfolio_value * (risk_pct / 100)

    # Confidence multiplier (0.75x to 1.25x)
    conf_mult = 0.75 + (confidence / 100) * 0.50  # 0% -> 0.75x, 100% -> 1.25x

    # Stop distance = 1.5 ATR
    stop_distance = 1.5 * atr if atr > 0 else entry_price * 0.03

    # Shares from risk
    shares_from_risk = int((risk_dollars * conf_mult) / stop_distance)

    # Max position cap
    max_dollars = portfolio_value * (max_pos_pct / 100)
    max_shares = int(max_dollars / entry_price) if entry_price > 0 else 0

    shares = min(shares_from_risk, max_shares)
    shares = max(shares, 0)

    return {
        "shares": shares,
        "dollar_amount": round(shares * entry_price, 2),
        "risk_dollars": round(risk_dollars * conf_mult, 2),
        "stop_price": round(entry_price - stop_distance, 2),
        "confidence_multiplier": round(conf_mult, 2),
    }


def check_drawdown_status(
    current_equity: float,
    peak_equity: float,
) -> dict:
    """Check portfolio drawdown and return trading restrictions.

    Rules:
    - At -8%: cut new position sizes in half
    - At -12%: pause all new buys
    """
    risk_cfg = load_strategies().get("risk", {})
    half_threshold = risk_cfg.get("drawdown_half", 8)
    pause_threshold = risk_cfg.get("drawdown_pause", 12)

    if peak_equity <= 0:
        return {"drawdown_pct": 0, "size_multiplier": 1.0, "new_buys_paused": False}

    drawdown_pct = ((peak_equity - current_equity) / peak_equity) * 100

    size_multiplier = 1.0
    new_buys_paused = False

    if drawdown_pct >= pause_threshold:
        new_buys_paused = True
        size_multiplier = 0.0
    elif drawdown_pct >= half_threshold:
        size_multiplier = 0.5

    return {
        "drawdown_pct": round(drawdown_pct, 2),
        "size_multiplier": size_multiplier,
        "new_buys_paused": new_buys_paused,
    }
