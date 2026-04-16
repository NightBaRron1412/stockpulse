"""Rebound-2D scanner — intraday dip-buy detection.

Scans eligible tickers for intraday reversal setups:
1. Stock dips >= 1% or 0.35 ATR from open
2. Intraday RSI drops below 35
3. Price touches/undercuts VWAP or opening range low
4. Then reclaims with volume confirmation

Not a day-trading engine. A manual, low-frequency rebound sleeve.
"""
import logging
from datetime import datetime

import pandas as pd
import pandas_ta as ta
import yfinance as yf

from stockpulse.config.settings import load_strategies
from stockpulse.data.provider import get_price_history
from stockpulse.data.cache import get_cached, set_cached

logger = logging.getLogger(__name__)


def scan_rebound_candidates(eligible_tickers: list[str]) -> list[dict]:
    """Scan eligible tickers for intraday rebound setups.

    Returns list of candidates sorted by setup quality.
    """
    config = load_strategies().get("rebound_mode", {})
    if not config.get("enabled", False):
        return []

    entry_cfg = config.get("entry", {})
    no_before = entry_cfg.get("no_entries_before", "10:00")

    # Check time — no entries before 10:00 AM ET
    now = datetime.now()
    try:
        from pytz import timezone
        et = timezone("US/Eastern")
        now_et = datetime.now(et)
        cutoff_hour, cutoff_min = map(int, no_before.split(":"))
        if now_et.hour < cutoff_hour or (now_et.hour == cutoff_hour and now_et.minute < cutoff_min):
            logger.info("Rebound scan: before %s ET, skipping", no_before)
            return []
    except Exception:
        pass  # If timezone fails, proceed anyway

    candidates = []
    for ticker in eligible_tickers:
        try:
            setup = _check_rebound_setup(ticker, config)
            if setup:
                candidates.append(setup)
        except Exception:
            logger.debug("Rebound scan failed for %s", ticker)

    # Sort by quality score (higher = better setup), return top 2 max
    candidates.sort(key=lambda c: c.get("quality", 0), reverse=True)
    max_candidates = config.get("sizing", {}).get("max_positions", 1) + 1  # show 1 extra as backup
    return candidates[:max(2, max_candidates)]


def _check_rebound_setup(ticker: str, config: dict) -> dict | None:
    """Check if a ticker has an intraday rebound setup.

    Uses 5-minute bars from yfinance for intraday data.
    """
    entry_cfg = config.get("entry", {})
    exit_cfg = config.get("exit", {})
    sizing_cfg = config.get("sizing", {})

    # Get daily data for ATR and context
    daily_df = get_price_history(ticker, period="3mo")
    if daily_df.empty or len(daily_df) < 20:
        return None
    if isinstance(daily_df.columns, pd.MultiIndex):
        daily_df.columns = daily_df.columns.get_level_values(0)

    daily_atr = ta.atr(daily_df["High"], daily_df["Low"], daily_df["Close"], length=14)
    atr_val = float(daily_atr.iloc[-1]) if daily_atr is not None else 0
    prev_close = float(daily_df["Close"].iloc[-1])

    if atr_val <= 0 or prev_close <= 0:
        return None

    # Get intraday 5-minute bars
    cache_key = f"intraday_5m_{ticker}"
    intraday = get_cached(cache_key)
    if intraday is None:
        try:
            intraday = yf.download(ticker, period="1d", interval="5m", progress=False, timeout=10)
            if isinstance(intraday.columns, pd.MultiIndex):
                intraday.columns = intraday.columns.get_level_values(0)
            if not intraday.empty:
                set_cached(cache_key, intraday)
        except Exception:
            return None

    if intraday is None or intraday.empty or len(intraday) < 10:
        return None

    # Calculate intraday metrics
    open_price = float(intraday["Open"].iloc[0])
    current_price = float(intraday["Close"].iloc[-1])
    day_high = float(intraday["High"].max())
    day_low = float(intraday["Low"].min())

    # Opening range (first 30 min = first 6 bars of 5m)
    or_bars = min(6, len(intraday))
    or_high = float(intraday["High"].iloc[:or_bars].max())
    or_low = float(intraday["Low"].iloc[:or_bars].min())

    # VWAP calculation
    typical = (intraday["High"] + intraday["Low"] + intraday["Close"]) / 3
    vwap = float((typical * intraday["Volume"]).cumsum().iloc[-1] / intraday["Volume"].cumsum().iloc[-1])

    # Dip check
    dip_from_open = ((open_price - day_low) / open_price) * 100 if open_price > 0 else 0
    dip_from_prev = ((prev_close - day_low) / prev_close) * 100 if prev_close > 0 else 0
    dip_pct = max(dip_from_open, dip_from_prev)

    dip_min_pct = entry_cfg.get("dip_min_pct", 1.0)
    dip_min_atr = entry_cfg.get("dip_min_atr_fraction", 0.35)
    atr_pct = (atr_val / prev_close) * 100 if prev_close > 0 else 2.0

    if dip_pct < dip_min_pct and dip_pct < dip_min_atr * atr_pct:
        return None  # Dip not deep enough

    # Intraday RSI (dropna to avoid NaN from first 13 bars)
    intraday_rsi = ta.rsi(intraday["Close"], length=14)
    if intraday_rsi is not None:
        rsi_clean = intraday_rsi.dropna()
        rsi_min = float(rsi_clean.min()) if not rsi_clean.empty else 50.0
        rsi_current = float(rsi_clean.iloc[-1]) if not rsi_clean.empty else 50.0
    else:
        rsi_min = 50.0
        rsi_current = 50.0
    rsi_max = entry_cfg.get("intraday_rsi_max", 35)

    rsi_dipped = rsi_min <= rsi_max

    # VWAP/OR reclaim check
    reclaimed = current_price > vwap and current_price > or_low

    # Volume on reclaim — compare last 3 bars vs median of non-spike bars
    # (using median excludes the opening spike that inflates the average)
    recent_vol = float(intraday["Volume"].iloc[-3:].mean()) if len(intraday) >= 3 else 0
    median_vol = float(intraday["Volume"].median())
    avg_vol = median_vol if median_vol > 0 else float(intraday["Volume"].mean())
    vol_mult = recent_vol / avg_vol if avg_vol > 0 else 1.0
    vol_threshold = entry_cfg.get("reclaim_volume_multiple", 1.5)
    vol_confirmed = vol_mult >= vol_threshold

    # HARD REQUIREMENTS (expert rules):
    # 1. Must have reclaimed VWAP/OR low
    # 2. Must have dipped enough
    # 3. Volume confirmation on reclaim required
    if not reclaimed:
        return None
    if not vol_confirmed:
        return None

    # Quality score (0-100) — bonus signals
    quality = 50  # Base: reclaimed + volume confirmed
    if dip_pct >= dip_min_pct * 1.5:
        quality += 15  # Deep dip bonus
    if rsi_dipped:
        quality += 20  # RSI oversold bonus
    if vol_mult >= vol_threshold * 1.5:
        quality += 15  # Strong volume bonus

    # Compute stop and target
    setup_low = day_low
    stop_pct = min(exit_cfg.get("stop_max_pct", 1.0), dip_min_atr * atr_pct) / 100
    stop_price = round(current_price * (1 - stop_pct), 2)
    stop_price = max(stop_price, round(setup_low * 0.998, 2))  # Don't set stop above the setup low

    risk_per_share = current_price - stop_price
    target_r = exit_cfg.get("target_r", 1.3)
    target_price = round(current_price + risk_per_share * target_r, 2)

    # Position sizing
    max_risk = sizing_cfg.get("max_risk_per_trade", 20)
    shares = int(max_risk / risk_per_share) if risk_per_share > 0 else 0
    default_pos = sizing_cfg.get("default_position", 1500)
    max_shares = int(default_pos / current_price) if current_price > 0 else 0
    shares = min(shares, max_shares)

    if shares <= 0:
        return None

    return {
        "ticker": ticker,
        "quality": quality,
        "current_price": round(current_price, 2),
        "open_price": round(open_price, 2),
        "day_low": round(day_low, 2),
        "vwap": round(vwap, 2),
        "or_low": round(or_low, 2),
        "or_high": round(or_high, 2),
        "dip_pct": round(dip_pct, 1),
        "rsi_low": round(rsi_min, 1),
        "rsi_current": round(rsi_current, 1),
        "vol_mult": round(vol_mult, 1),
        "reclaimed": reclaimed,
        "stop_price": stop_price,
        "target_price": target_price,
        "suggested_shares": shares,
        "suggested_amount": round(shares * current_price, 2),
        "risk_dollars": round(shares * risk_per_share, 2),
        "reward_dollars": round(shares * risk_per_share * target_r, 2),
        "setup": _describe_setup(dip_pct, rsi_dipped, reclaimed, vol_confirmed, vwap, or_low),
    }


def _describe_setup(dip_pct, rsi_dipped, reclaimed, vol_confirmed, vwap, or_low):
    parts = [f"Dipped {dip_pct:.1f}%"]
    if rsi_dipped:
        parts.append("RSI oversold")
    if reclaimed:
        parts.append(f"reclaimed VWAP ${vwap:.2f}")
    if vol_confirmed:
        parts.append("volume confirmed")
    return ". ".join(parts)


def get_eligible_tickers() -> list[str]:
    """Get tickers eligible for rebound scanning based on main engine scores."""
    from stockpulse.api.server import _get_latest_scan
    from stockpulse.signals.weekly import assess_weekly_trend

    config = load_strategies().get("rebound_mode", {})
    elig = config.get("eligibility", {})
    min_score = elig.get("main_score_gte", 25)
    block_tiers = set(elig.get("block_tiers", ["CAUTION", "SELL"]))

    recs = _get_latest_scan()
    eligible = []

    for rec in recs:
        if rec.get("action") in block_tiers:
            continue
        if rec.get("composite_score", 0) < min_score:
            continue

        ticker = rec["ticker"]

        # Weekly trend check
        if elig.get("weekly_trend_positive", True):
            try:
                df = get_price_history(ticker, period="1y")
                if not df.empty:
                    weekly = assess_weekly_trend(df)
                    if weekly.get("trend") == "down":
                        continue
            except Exception:
                pass

        # Earnings check
        if elig.get("no_earnings_today_or_next_morning", True):
            try:
                from stockpulse.data.provider import get_earnings_dates
                dates = get_earnings_dates(ticker)
                if dates and any(0 <= d.get("days_away", 999) <= 1 for d in dates):
                    continue
            except Exception:
                pass

        eligible.append(ticker)

    return eligible
