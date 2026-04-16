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

    # Sort by quality score
    candidates.sort(key=lambda c: c.get("quality", 0), reverse=True)
    return candidates[:5]


def scan_active_dips(eligible_tickers: list[str]) -> list[dict]:
    """Find stocks currently IN a dip — not yet bounced.

    These are real-time alerts: "QBTS is down 5% and near VWAP — watch for entry."
    The user decides when to buy based on their own confirmation.
    """
    config = load_strategies().get("rebound_mode", {})
    if not config.get("enabled", False):
        return []

    entry_cfg = config.get("entry", {})
    exit_cfg = config.get("exit", {})
    sizing_cfg = config.get("sizing", {})

    dips = []
    for ticker in eligible_tickers:
        try:
            result = _check_active_dip(ticker, config)
            if result:
                dips.append(result)
        except Exception:
            pass

    dips.sort(key=lambda d: d.get("dip_pct", 0), reverse=True)
    return dips[:10]


def _check_active_dip(ticker: str, config: dict) -> dict | None:
    """Check if a ticker is currently in a dip — price below VWAP or OR low."""
    import yfinance as yf
    entry_cfg = config.get("entry", {})
    exit_cfg = config.get("exit", {})
    sizing_cfg = config.get("sizing", {})

    # Get daily ATR
    daily_df = get_price_history(ticker, period="3mo")
    if daily_df.empty or len(daily_df) < 20:
        return None
    if isinstance(daily_df.columns, pd.MultiIndex):
        daily_df.columns = daily_df.columns.get_level_values(0)

    atr_series = ta.atr(daily_df["High"], daily_df["Low"], daily_df["Close"], length=14)
    atr_val = float(atr_series.iloc[-1]) if atr_series is not None else 0
    prev_close = float(daily_df["Close"].iloc[-1])

    if atr_val <= 0 or prev_close <= 0:
        return None

    # Get intraday
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

    if intraday is None or intraday.empty or len(intraday) < 6:
        return None

    open_price = float(intraday["Open"].iloc[0])
    current_price = float(intraday["Close"].iloc[-1])
    day_low = float(intraday["Low"].min())

    # Opening range
    or_high = float(intraday["High"].iloc[:6].max())
    or_low = float(intraday["Low"].iloc[:6].min())

    # VWAP
    typical = (intraday["High"] + intraday["Low"] + intraday["Close"]) / 3
    vol_sum = intraday["Volume"].cumsum()
    vwap = float((typical * intraday["Volume"]).cumsum().iloc[-1] / vol_sum.iloc[-1]) if float(vol_sum.iloc[-1]) > 0 else current_price

    # Dip check
    dip_from_open = ((open_price - current_price) / open_price) * 100 if open_price > 0 else 0
    dip_from_prev = ((prev_close - current_price) / prev_close) * 100 if prev_close > 0 else 0
    dip_pct = max(dip_from_open, dip_from_prev)

    dip_min = entry_cfg.get("dip_min_pct", 1.0)
    if dip_pct < dip_min:
        return None

    # Min price filter
    if current_price < 5.0:
        return None

    # Must be BELOW vwap or near OR low — still in the dip
    below_vwap = current_price <= vwap * 1.002
    near_or_low = current_price <= or_low * 1.01

    if not below_vwap and not near_or_low:
        return None  # Already bounced — not an active dip

    # RSI
    rsi = ta.rsi(intraday["Close"], length=14)
    rsi_current = 50.0
    if rsi is not None:
        clean = rsi.dropna()
        if not clean.empty:
            rsi_current = float(clean.iloc[-1])

    # Compute levels — for active dips, entry is current price (you're buying NOW)
    # Target is the bounce back to VWAP or above
    stop_pct = exit_cfg.get("stop_max_pct", 1.0) / 100
    stop_price = round(current_price * (1 - stop_pct), 2)
    risk_per_share = current_price - stop_price
    if risk_per_share <= 0:
        return None
    # Target: bounce to VWAP + some profit, or use R multiple
    target_r = exit_cfg.get("target_r", 1.3)
    bounce_target = round(vwap + risk_per_share * 0.5, 2)  # VWAP + half a stop width
    r_target = round(current_price + risk_per_share * target_r, 2)
    target_price = max(bounce_target, r_target)  # Whichever is higher
    entry_zone = round(current_price, 2)  # Entry is NOW — you're buying the dip

    # Sizing
    max_risk = sizing_cfg.get("max_risk_per_trade", 20)
    shares = int(max_risk / risk_per_share) if risk_per_share > 0 else 0
    default_pos = sizing_cfg.get("default_position", 1500)
    max_shares = int(default_pos / current_price) if current_price > 0 else 0
    shares = min(shares, max_shares)

    if shares <= 0:
        return None

    # Status
    if current_price <= day_low * 1.005:
        status = "AT LOW"
    elif below_vwap:
        status = "BELOW VWAP"
    else:
        status = "NEAR OR LOW"

    return {
        "ticker": ticker,
        "status": status,
        "dip_pct": round(dip_pct, 1),
        "current_price": round(current_price, 2),
        "open_price": round(open_price, 2),
        "day_low": round(day_low, 2),
        "vwap": round(vwap, 2),
        "or_low": round(or_low, 2),
        "or_high": round(or_high, 2),
        "rsi": round(rsi_current, 1),
        "entry_zone": entry_zone,
        "stop_price": stop_price,
        "target_price": target_price,
        "suggested_shares": shares,
        "risk_dollars": round(shares * risk_per_share, 2),
        "alert": f"{ticker} DOWN {dip_pct:.1f}% — {status} at ${current_price:.2f}. VWAP ${vwap:.2f}. Watch for reclaim.",
    }


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

    # Intraday RSI — use shorter period (5) for 5-min bars to get meaningful readings
    intraday_rsi = ta.rsi(intraday["Close"], length=5)
    if intraday_rsi is not None:
        rsi_clean = intraday_rsi.dropna()
        rsi_min = float(rsi_clean.min()) if not rsi_clean.empty else 50.0
        rsi_current = float(rsi_clean.iloc[-1]) if not rsi_clean.empty else 50.0
        # Clamp — RSI should be 0-100
        rsi_min = max(0.1, rsi_min)
    else:
        rsi_min = 50.0
        rsi_current = 50.0
    rsi_max = entry_cfg.get("intraday_rsi_max", 35)

    rsi_dipped = rsi_min <= rsi_max

    # VWAP/OR reclaim check
    reclaimed = current_price > vwap and current_price > or_low

    # Time-of-day adjusted volume (BarRVOL_TOD)
    # Compare current bar volume to median volume for this time slot over last 20 sessions
    bar_rvol_tod, cum_rvol_tod = _compute_tod_volume(ticker, intraday)
    recent_vol = float(intraday["Volume"].iloc[-3:].mean()) if len(intraday) >= 3 else 0
    vol_mult = bar_rvol_tod  # Use TOD-adjusted metric for display

    # Cumulative RVOL — is the stock "in play" today?
    cum_in_play = cum_rvol_tod >= 1.0

    # HARD REQUIREMENTS:
    # 1. Must have reclaimed VWAP/OR low
    # 2. Must have dipped enough
    # 3. Volume: reject if truly dead (TOD-adjusted)
    if not reclaimed:
        return None
    if bar_rvol_tod < 0.5 and cum_rvol_tod < 1.0:
        return None  # Dead volume — no participation at all

    # Event override: big gap + high cumulative RVOL = in play regardless of reclaim bar
    event_override = dip_pct >= 3.0 and cum_rvol_tod >= 2.0

    # Quality score (0-100)
    # Min price filter — skip penny stocks
    if current_price < 5.0:
        return None

    quality = 40  # Base: dip + reclaim
    if dip_pct >= dip_min_pct * 2:
        quality += 10  # Deep dip bonus
    if rsi_dipped:
        quality += 15  # RSI oversold bonus
    # Volume quality tiers (TOD-adjusted)
    if bar_rvol_tod >= 1.2:
        quality += 15  # Strong reclaim volume
    elif bar_rvol_tod >= 0.9:
        quality += 10  # Normal volume
    if event_override:
        quality += 10  # Big gap + in play
    if cum_in_play:
        quality += 5   # Stock is in play today
    quality = min(quality, 100)  # Cap at 100

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
        "setup": _describe_setup(dip_pct, rsi_dipped, reclaimed, bar_rvol_tod >= 1.0, vwap, or_low),
    }


def _compute_tod_volume(ticker: str, intraday: pd.DataFrame) -> tuple[float, float]:
    """Compute time-of-day adjusted volume metrics.

    BarRVOL_TOD: current bar volume / median volume for this time slot over last 20 sessions
    CumRVOL_TOD: cumulative volume today / median cumulative volume by this time over 20 sessions

    Returns (bar_rvol_tod, cum_rvol_tod). Defaults to (1.0, 1.0) if historical data unavailable.
    """
    try:
        import yfinance as yf

        # Get last 20 sessions of 5-min data
        cache_key = f"tod_vol_{ticker}"
        hist_data = get_cached(cache_key)
        if hist_data is None:
            hist_data = yf.download(ticker, period="1mo", interval="5m", progress=False, timeout=15)
            if isinstance(hist_data.columns, pd.MultiIndex):
                hist_data.columns = hist_data.columns.get_level_values(0)
            if not hist_data.empty:
                set_cached(cache_key, hist_data)

        if hist_data is None or hist_data.empty or len(hist_data) < 50:
            return 1.0, 1.0

        # Current time slot (hour:minute)
        current_time = intraday.index[-1]
        current_hour = current_time.hour if hasattr(current_time, 'hour') else 12
        current_minute = (current_time.minute if hasattr(current_time, 'minute') else 0) // 5 * 5

        # Get historical volumes for this time slot
        tod_volumes = []
        for idx, row in hist_data.iterrows():
            h = idx.hour if hasattr(idx, 'hour') else 0
            m = idx.minute if hasattr(idx, 'minute') else 0
            if h == current_hour and (m // 5 * 5) == current_minute:
                tod_volumes.append(float(row["Volume"]))

        if len(tod_volumes) < 5:
            # Fallback: use overall median
            return 1.0, 1.0

        # BarRVOL_TOD
        current_bar_vol = float(intraday["Volume"].iloc[-1])
        median_tod_vol = sorted(tod_volumes)[len(tod_volumes) // 2]
        bar_rvol = current_bar_vol / median_tod_vol if median_tod_vol > 0 else 1.0

        # CumRVOL_TOD
        cum_vol_today = float(intraday["Volume"].sum())
        # Estimate median cumulative volume by this time
        bars_so_far = len(intraday)
        daily_volumes = []
        dates = set()
        for idx in hist_data.index:
            d = idx.date() if hasattr(idx, 'date') else idx
            dates.add(d)
        for d in sorted(dates)[-20:]:
            day_mask = [idx.date() == d if hasattr(idx, 'date') else False for idx in hist_data.index]
            day_data = hist_data[day_mask]
            if len(day_data) >= bars_so_far:
                daily_volumes.append(float(day_data["Volume"].iloc[:bars_so_far].sum()))

        if daily_volumes:
            median_cum = sorted(daily_volumes)[len(daily_volumes) // 2]
            cum_rvol = cum_vol_today / median_cum if median_cum > 0 else 1.0
        else:
            cum_rvol = 1.0

        return round(bar_rvol, 2), round(cum_rvol, 2)
    except Exception:
        return 1.0, 1.0


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

    # Apply Shariah filter (user tickers bypass)
    from stockpulse.config.settings import load_strategies as _ls, load_watchlists as _lw
    if _ls().get("filters", {}).get("shariah_only", False):
        from stockpulse.filters.shariah import is_compliant_fast
        user_set = set(_lw().get("user", []))
        eligible = [t for t in eligible if t in user_set or is_compliant_fast(t)]

    return eligible


def get_top_dippers(limit: int = 20) -> list[str]:
    """Find today's biggest dippers from the FULL S&P 500 + high-beta universe.

    Uses yfinance bulk download (~15s for 500+ tickers).
    Returns tickers sorted by dip size.
    """
    import yfinance as yf
    from stockpulse.data.universe import get_sp500_tickers
    from stockpulse.config.settings import load_watchlists

    # Full S&P 500 + popular high-beta names not in S&P + user watchlist
    EXTRA_VOLATILE = [
        "COIN", "HOOD", "SOFI", "PLTR", "SNOW", "NET", "DDOG", "CRWD",
        "QBTS", "IONQ", "RGTI", "SMCI", "SOUN", "BBAI", "AI", "UPST",
        "CLSK", "MARA", "RIOT", "HUT", "SQ", "SHOP", "ROKU", "SNAP",
        "RBLX", "TTD", "U", "PINS", "CELH", "HIMS", "DUOL",
    ]

    sp500 = get_sp500_tickers()
    user = load_watchlists().get("user", [])
    tickers = list(dict.fromkeys(sp500 + EXTRA_VOLATILE + user))

    try:
        data = yf.download(tickers, period="5d", group_by="ticker",
                           threads=True, progress=False, timeout=30)
    except Exception:
        return []

    dippers = []
    for ticker in tickers:
        try:
            df = data[ticker].dropna(how="all") if len(tickers) > 1 else data.dropna(how="all")
            if df.empty or len(df) < 2:
                continue

            prev_close = float(df["Close"].iloc[-2])
            today_open = float(df["Open"].iloc[-1])
            today_low = float(df["Low"].iloc[-1])
            today_close = float(df["Close"].iloc[-1])

            dip_from_open = ((today_open - today_low) / today_open) * 100 if today_open > 0 else 0
            dip_from_prev = ((prev_close - today_low) / prev_close) * 100 if prev_close > 0 else 0
            dip = max(dip_from_open, dip_from_prev)

            bounced = today_close > today_low * 1.003

            # Liquidity: avg dollar volume > $50M
            avg_vol = float(df["Volume"].iloc[-5:].mean())
            avg_price = float(df["Close"].iloc[-5:].mean())
            dollar_vol = avg_vol * avg_price

            if dip >= 1.0 and bounced and dollar_vol >= 50_000_000:
                dippers.append((ticker, dip))
        except (KeyError, AttributeError):
            continue

    dippers.sort(key=lambda x: x[1], reverse=True)
    result = [t for t, _ in dippers[:limit]]

    # Apply Shariah filter (user tickers bypass)
    from stockpulse.config.settings import load_strategies as _ls
    if _ls().get("filters", {}).get("shariah_only", False):
        from stockpulse.filters.shariah import is_compliant_fast
        user_set = set(load_watchlists().get("user", []))
        result = [t for t in result if t in user_set or is_compliant_fast(t)]

    return result
