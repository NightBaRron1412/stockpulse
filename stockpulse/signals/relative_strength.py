"""Relative Strength vs SPY and sector --  excess return percentile ranks."""

import logging
import math

import pandas as pd
import yfinance as yf

from stockpulse.data.cache import get_cached, set_cached
from stockpulse.data.provider import get_price_history

logger = logging.getLogger(__name__)

# GICS sector -> sector ETF mapping
SECTOR_ETF = {
    "Technology": "XLK",
    "Information Technology": "XLK",
    "Financial Services": "XLF",
    "Financials": "XLF",
    "Energy": "XLE",
    "Healthcare": "XLV",
    "Health Care": "XLV",
    "Industrials": "XLI",
    "Communication Services": "XLC",
    "Consumer Cyclical": "XLY",
    "Consumer Discretionary": "XLY",
    "Consumer Defensive": "XLP",
    "Consumer Staples": "XLP",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
    "Basic Materials": "XLB",
    "Materials": "XLB",
}


def _log_return(series: pd.Series, period: int) -> float:
    """Compute ln(C_t / C_t-period)."""
    if len(series) < period + 1:
        return 0.0
    current = float(series.iloc[-1])
    past = float(series.iloc[-period - 1])
    if past <= 0 or current <= 0:
        return 0.0
    return math.log(current / past)


def _get_sector(ticker: str) -> str:
    """Get GICS sector for a ticker via yfinance."""
    cache_key = f"sector_{ticker}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached
    try:
        t = yf.Ticker(ticker)
        info = t.info
        sector = info.get("sector", "")
        if sector:
            set_cached(cache_key, sector)
        return sector
    except Exception:
        return ""


def calc_relative_strength(
    ticker: str,
    df: pd.DataFrame,
    universe_excess_returns: dict | None = None,
) -> float:
    """Compute relative strength score using the formula.

    Args:
        ticker: Stock ticker
        df: Price history DataFrame for this ticker
        universe_excess_returns: Pre-computed {ticker: {ex20_mkt, ex60_mkt}} for percentile ranking.
            If None, uses raw excess return score without percentile ranking (fallback).

    Returns:
        Score in [-100, +100]
    """
    if df.empty or len(df) < 61:
        return 0.0

    close = df["Close"]

    # Stock log returns
    r20_stock = _log_return(close, 20)
    r60_stock = _log_return(close, 60)

    # SPY log returns
    spy_df = get_price_history("SPY", period="6mo")
    if spy_df.empty or len(spy_df) < 61:
        return 0.0
    r20_spy = _log_return(spy_df["Close"], 20)
    r60_spy = _log_return(spy_df["Close"], 60)

    # Excess returns vs market
    ex20_mkt = r20_stock - r20_spy
    ex60_mkt = r60_stock - r60_spy

    # Sector excess returns
    sector = _get_sector(ticker)
    sector_etf = SECTOR_ETF.get(sector, "")
    ex20_sector = 0.0
    if sector_etf:
        sector_df = get_price_history(sector_etf, period="6mo")
        if not sector_df.empty and len(sector_df) >= 21:
            r20_sector = _log_return(sector_df["Close"], 20)
            ex20_sector = r20_stock - r20_sector

    # Percentile ranking
    if universe_excess_returns and len(universe_excess_returns) > 10:
        # Compute percentile ranks across universe
        all_ex20 = [v.get("ex20_mkt", 0) for v in universe_excess_returns.values()]
        all_ex60 = [v.get("ex60_mkt", 0) for v in universe_excess_returns.values()]

        # Sector-specific percentile for ex20_sector
        sector_ex20 = [
            v.get("ex20_sector", 0) for t, v in universe_excess_returns.items()
            if v.get("sector", "") == sector
        ]

        p1 = _percentile_rank(ex20_mkt, all_ex20)
        p2 = _percentile_rank(ex60_mkt, all_ex60)
        p3 = _percentile_rank(ex20_sector, sector_ex20) if sector_ex20 else 0.5
    else:
        # Fallback: convert excess returns to approximate scores directly
        # Scale by typical excess return range (~0.10 = 10% excess return = strong)
        p1 = _excess_to_percentile(ex20_mkt, scale=0.08)
        p2 = _excess_to_percentile(ex60_mkt, scale=0.15)
        p3 = _excess_to_percentile(ex20_sector, scale=0.08)

    # RS formula
    rs_score = 100 * (
        0.40 * (2 * p1 - 1) +
        0.35 * (2 * p2 - 1) +
        0.25 * (2 * p3 - 1)
    )

    return max(-100.0, min(100.0, rs_score))


def _percentile_rank(value: float, population: list[float]) -> float:
    """Compute percentile rank of value within population. Returns 0.0-1.0."""
    if not population:
        return 0.5
    below = sum(1 for x in population if x < value)
    equal = sum(1 for x in population if x == value)
    return (below + 0.5 * equal) / len(population)


def _excess_to_percentile(excess_return: float, scale: float = 0.10) -> float:
    """Approximate percentile from excess return when universe data unavailable.
    Maps excess return to [0, 1] using a sigmoid-like function."""
    # Scale so that 'scale' excess return maps to roughly 75th percentile
    z = excess_return / scale
    # Use tanh to map to [0, 1]
    return 0.5 + 0.5 * math.tanh(z)


def compute_universe_excess_returns(tickers: list[str]) -> dict:
    """Pre-compute excess returns for the full universe for percentile ranking.

    Call this once per scan cycle, then pass the result to calc_relative_strength.
    Returns {ticker: {ex20_mkt, ex60_mkt, ex20_sector, sector}}.
    """
    cache_key = "universe_excess_returns"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    spy_df = get_price_history("SPY", period="6mo")
    if spy_df.empty or len(spy_df) < 61:
        return {}

    r20_spy = _log_return(spy_df["Close"], 20)
    r60_spy = _log_return(spy_df["Close"], 60)

    # Cache sector ETF returns
    sector_returns = {}
    for etf in set(SECTOR_ETF.values()):
        etf_df = get_price_history(etf, period="6mo")
        if not etf_df.empty and len(etf_df) >= 21:
            sector_returns[etf] = _log_return(etf_df["Close"], 20)

    results = {}
    for ticker in tickers:
        try:
            df = get_price_history(ticker, period="6mo")
            if df.empty or len(df) < 61:
                continue
            close = df["Close"]
            r20 = _log_return(close, 20)
            r60 = _log_return(close, 60)

            sector = _get_sector(ticker)
            sector_etf = SECTOR_ETF.get(sector, "")
            r20_sector = sector_returns.get(sector_etf, 0.0)

            results[ticker] = {
                "ex20_mkt": r20 - r20_spy,
                "ex60_mkt": r60 - r60_spy,
                "ex20_sector": r20 - r20_sector,
                "sector": sector,
            }
        except Exception:
            continue

    set_cached(cache_key, results)
    return results
