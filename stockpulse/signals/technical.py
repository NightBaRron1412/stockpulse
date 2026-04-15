"""Technical indicator signal generators.
Each function takes a price DataFrame (OHLCV) and returns a score from -100 to +100.
Positive = bullish, negative = bearish.
"""
import pandas as pd
import pandas_ta as ta
from stockpulse.config.settings import load_strategies

def _clamp(value: float, lo: float = -100.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))

def _get_signal_config(name: str) -> dict:
    strat = load_strategies()
    return strat.get("signals", {}).get(name, {})

def calc_rsi_signal(df: pd.DataFrame) -> float:
    """RSI signal with professionally calibrated granular zones.
    In uptrends: 70-75 is only -5, not -15. RSI 50-70 is neutral.
    In downtrends: 35-55 is neutral, 55-65 is mild -5."""
    cfg = _get_signal_config("rsi")
    period = cfg.get("period", 14)
    rsi = ta.rsi(df["Close"], length=period)
    if rsi is None or rsi.dropna().empty:
        return 0.0
    current_rsi = float(rsi.iloc[-1])

    # Determine trend context
    sma50 = ta.sma(df["Close"], length=50)
    in_uptrend = False
    if sma50 is not None and not sma50.dropna().empty:
        in_uptrend = float(df["Close"].iloc[-1]) > float(sma50.iloc[-1])

    if in_uptrend:
        zones = cfg.get("uptrend_zones", {})
        if current_rsi <= 20:
            return 80.0
        elif current_rsi <= 30:
            return 50.0
        elif current_rsi <= 40:
            return 30.0
        elif current_rsi <= 50:
            return float(zones.get("40_50", 20))
        elif current_rsi <= 70:
            return float(zones.get("50_70", 0))
        elif current_rsi <= 75:
            return float(zones.get("70_75", -5))
        elif current_rsi <= 80:
            return float(zones.get("75_80", -10))
        else:
            return float(zones.get("gt_80", -20))
    else:
        zones = cfg.get("downtrend_zones", {})
        if current_rsi <= 20:
            return 60.0
        elif current_rsi <= 35:
            return float(zones.get("lt_35", 0))
        elif current_rsi <= 55:
            return float(zones.get("35_55", 0))
        elif current_rsi <= 65:
            return float(zones.get("55_65", -5))
        else:
            return float(zones.get("gt_65", -15))

def calc_macd_signal(df: pd.DataFrame) -> float:
    cfg = _get_signal_config("macd")
    fast = cfg.get("fast", 12)
    slow = cfg.get("slow", 26)
    signal = cfg.get("signal", 9)
    macd_df = ta.macd(df["Close"], fast=fast, slow=slow, signal=signal)
    if macd_df is None or macd_df.dropna().empty:
        return 0.0
    hist_col = f"MACDh_{fast}_{slow}_{signal}"
    if hist_col not in macd_df.columns:
        return 0.0
    hist = macd_df[hist_col].dropna()
    if len(hist) < 2:
        return 0.0
    current_hist = float(hist.iloc[-1])
    prev_hist = float(hist.iloc[-2])
    std = float(hist.tail(50).std()) or 1.0
    score = (current_hist / std) * 40
    if prev_hist < 0 and current_hist > 0:
        score += 30
    elif prev_hist > 0 and current_hist < 0:
        score -= 30
    return _clamp(score)

def calc_ma_signal(df: pd.DataFrame) -> float:
    """Moving average signal split into price-location (60%) and structure/alignment (40%).
    Price above 20/50 should count even if alignment is bearish."""
    cfg = _get_signal_config("moving_averages")
    price_weight = cfg.get("price_vs_ma_weight", 0.60)
    stack_weight = cfg.get("stack_slope_weight", 0.40)

    close = df["Close"]
    current_price = float(close.iloc[-1])

    ema20 = ta.ema(close, length=20)
    sma50 = ta.sma(close, length=50)
    sma200 = ta.sma(close, length=200)

    ema20_val = float(ema20.iloc[-1]) if ema20 is not None and not ema20.dropna().empty else None
    sma50_val = float(sma50.iloc[-1]) if sma50 is not None and not sma50.dropna().empty else None
    sma200_val = float(sma200.iloc[-1]) if sma200 is not None and len(sma200.dropna()) > 0 else None

    # Price location score (where is price vs MAs)
    price_score = 0.0
    if ema20_val:
        price_score += 25 if current_price > ema20_val else -25
    if sma50_val:
        price_score += 25 if current_price > sma50_val else -25
    if sma200_val:
        price_score += 30 if current_price > sma200_val else -30

    # Structure/alignment score (how are the MAs ordered)
    stack_score = 0.0
    if ema20_val and sma50_val and sma200_val:
        if ema20_val > sma50_val > sma200_val:
            stack_score = 80.0  # fully aligned bullish
        elif ema20_val < sma50_val < sma200_val:
            stack_score = -80.0  # fully aligned bearish
        elif ema20_val > sma50_val:
            stack_score = 20.0  # short-term bullish
        elif ema20_val < sma50_val:
            stack_score = -20.0  # short-term bearish
    elif ema20_val and sma50_val:
        # No 200 SMA data
        if ema20_val > sma50_val:
            stack_score = 30.0
        else:
            stack_score = -30.0

    # Weighted combination
    combined = price_score * price_weight + stack_score * stack_weight
    return _clamp(combined)

def calc_volume_signal(df: pd.DataFrame) -> float:
    """Volume signal using RVOL with soft positive band .
    0.8-1.0 RVOL gets small positive if price closes well and trend intact."""
    cfg = _get_signal_config("volume")
    lookback = cfg.get("lookback", 20)
    rvol_confirm = cfg.get("rvol_confirm", 1.5)
    rvol_strong = cfg.get("rvol_strong", 2.0)
    soft_band = cfg.get("soft_positive_band", [0.8, 1.0])
    soft_score = cfg.get("soft_positive_score", 5)

    if len(df) < lookback + 1:
        return 0.0

    current_vol = float(df["Volume"].iloc[-1])
    avg_vol = float(df["Volume"].iloc[-lookback - 1 : -1].mean())
    if avg_vol == 0:
        return 0.0

    rvol = current_vol / avg_vol
    price_change = float(df["Close"].iloc[-1]) - float(df["Close"].iloc[-2])
    direction = 1.0 if price_change > 0 else -1.0

    # Distribution day check
    distribution_count = 0
    for i in range(-5, 0):
        if i >= -len(df):
            day_change = float(df["Close"].iloc[i]) - float(df["Close"].iloc[i - 1])
            day_vol = float(df["Volume"].iloc[i])
            if day_change < 0 and day_vol > avg_vol * 1.2:
                distribution_count += 1

    score = 0.0
    if rvol >= rvol_strong:
        score = direction * 80.0
    elif rvol >= rvol_confirm:
        score = direction * 50.0
    elif rvol >= 1.2:
        score = direction * 20.0
    elif rvol >= 1.0:
        score = direction * 15.0
    elif rvol >= soft_band[0]:
        # Soft positive band: small positive if price direction is favorable
        if direction > 0:
            score = float(soft_score)
        else:
            score = 0.0
    elif rvol < 0.5:
        score = direction * -10.0

    if distribution_count >= 3:
        score -= 20.0

    return _clamp(score)

def calc_breakout_signal(df: pd.DataFrame) -> float:
    """Multi-timeframe breakout: 20-day, 55-day, 52-week.
    Requires volume confirmation (RVOL >= 1.5).
    Fakeout detection: if it fails back under within 1-3 days, penalize."""
    cfg = _get_signal_config("breakout")
    periods = cfg.get("periods", [20, 55, 252])
    require_volume = cfg.get("require_volume", True)
    rvol_min = cfg.get("rvol_min", 1.5)

    if len(df) < max(periods, default=20) + 1:
        # Use available periods
        periods = [p for p in periods if p < len(df)]
    if not periods:
        return 0.0

    current_price = float(df["Close"].iloc[-1])
    current_vol = float(df["Volume"].iloc[-1])
    avg_vol = float(df["Volume"].iloc[-21:-1].mean()) if len(df) > 21 else 1.0
    rvol = current_vol / avg_vol if avg_vol > 0 else 0.0

    score = 0.0
    breakout_count = 0

    for period in periods:
        lookback = df.iloc[-period:]
        high = float(lookback["High"].max())
        low = float(lookback["Low"].min())
        price_range = high - low
        if price_range == 0:
            continue

        position = (current_price - low) / price_range

        if position > 0.95:  # near high
            breakout_count += 1
            if period <= 20:
                score += 25
            elif period <= 55:
                score += 35
            else:
                score += 40  # 52-week breakout is strongest
        elif position < 0.05:  # near low
            if period <= 20:
                score -= 20
            elif period <= 55:
                score -= 30
            else:
                score -= 35

    # Volume confirmation
    if breakout_count > 0 and require_volume:
        if rvol >= rvol_min:
            score *= 1.3  # confirmed breakout — stronger
        elif rvol >= 1.0:
            pass  # average volume — keep base score
        else:
            score *= 0.7  # below-average volume — mild discount

    # Fakeout check: was there a breakout 1-3 days ago that failed?
    if len(df) > 5:
        for day_back in range(2, min(5, len(df))):
            prev_price = float(df["Close"].iloc[-day_back])
            prev_high_20 = float(df["High"].iloc[-20 - day_back:-day_back].max()) if len(df) > 20 + day_back else 0
            if prev_price > prev_high_20 > 0 and current_price < prev_high_20:
                score -= 25  # fakeout penalty
                break

    return _clamp(score)

def calc_gap_signal(df: pd.DataFrame) -> float:
    """Two-tier gap signal normalized by ATR.
    Don't overreact to macro-driven gaps on volatile names.

    Tiers:
    - 0.20-0.30 ATR: info only, minimal score
    - 0.30-0.50 ATR: normal scoreable gap
    - > 0.50 ATR: strong gap signal
    """
    cfg = _get_signal_config("gap")
    normalize_by_atr = cfg.get("normalize_by_atr", True)

    if len(df) < 2:
        return 0.0
    current_open = float(df["Open"].iloc[-1])
    prev_close = float(df["Close"].iloc[-2])
    if prev_close == 0:
        return 0.0

    gap_pct = ((current_open - prev_close) / prev_close) * 100

    if abs(gap_pct) < 0.15:
        return 0.0

    if normalize_by_atr:
        atr = ta.atr(df["High"], df["Low"], df["Close"], length=14)
        if atr is not None and not atr.dropna().empty:
            atr_pct = (float(atr.iloc[-1]) / prev_close) * 100
            if atr_pct > 0:
                gap_atr_ratio = abs(gap_pct) / atr_pct
                direction = 1 if gap_pct > 0 else -1

                if gap_atr_ratio < 0.20:
                    return 0.0  # noise
                elif gap_atr_ratio < 0.30:
                    # Info tier: note it, minimal score
                    return _clamp(direction * gap_atr_ratio * 10, -10.0, 10.0)
                elif gap_atr_ratio < 0.50:
                    # Normal scoreable gap
                    return _clamp(direction * gap_atr_ratio * 25, -40.0, 40.0)
                else:
                    # Strong gap signal
                    return _clamp(direction * gap_atr_ratio * 30, -60.0, 60.0)

    # Fallback: raw percentage scoring
    score = gap_pct * 20
    return _clamp(score, -60.0, 60.0)

def calc_adx_signal(df: pd.DataFrame) -> float:
    """Trend strength signal using ADX and directional indicators.
    ADX >20 = some trend, >25 = solid trend, >40 = strong trend.
    Direction from +DI/-DI difference."""
    cfg = _get_signal_config("adx")
    period = cfg.get("period", 14)
    trend_threshold = cfg.get("trend_threshold", 25)
    adx_df = ta.adx(df["High"], df["Low"], df["Close"], length=period)
    if adx_df is None or adx_df.dropna().empty:
        return 0.0
    adx_col = f"ADX_{period}"
    dmp_col = f"DMP_{period}"
    dmn_col = f"DMN_{period}"
    if adx_col not in adx_df.columns:
        return 0.0
    adx_val = float(adx_df[adx_col].iloc[-1])
    plus_di = float(adx_df[dmp_col].iloc[-1]) if dmp_col in adx_df.columns else 0
    minus_di = float(adx_df[dmn_col].iloc[-1]) if dmn_col in adx_df.columns else 0

    # Direction from DI spread
    di_diff = plus_di - minus_di
    direction = 1.0 if di_diff > 0 else -1.0

    # ADX-based strength (lower threshold for partial credit)
    if adx_val < 15:
        return 0.0  # no meaningful trend
    elif adx_val < trend_threshold:
        # Weak trend — partial score based on DI direction
        strength = (adx_val - 15) * 2  # 15-25 ADX → 0-20 score
        return _clamp(direction * strength)
    else:
        # Solid trend
        strength = min((adx_val - 15) * 2.5, 80.0)
        return _clamp(direction * strength)
