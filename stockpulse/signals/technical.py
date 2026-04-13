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
    """RSI signal -- trend-aware zones per expert:
    In uptrends (price > 50 SMA), RSI 40-50 = buyable pullback.
    Overbought >70 is NOT automatic sell in uptrends.
    For mean-reversion: 20/80 extremes only."""
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
        # In uptrend: pullback to 40-50 is bullish entry zone
        if current_rsi <= 20:
            return 80.0
        elif current_rsi <= 40:
            return 50.0
        elif current_rsi <= 50:
            return 30.0   # pullback zone -- still buyable
        elif current_rsi <= 70:
            return 0.0    # normal range in uptrend
        elif current_rsi <= 80:
            return -15.0  # mildly stretched but NOT sell in uptrend
        else:
            return -40.0  # extreme overbought even in uptrend
    else:
        # In downtrend: standard zones
        if current_rsi <= 20:
            return 60.0   # deeply oversold -- potential reversal
        elif current_rsi <= 30:
            return 30.0
        elif current_rsi <= 50:
            return 0.0
        elif current_rsi <= 70:
            return -20.0
        elif current_rsi <= 80:
            return -50.0
        else:
            return -80.0

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
    """Moving average signal using EMAs for tactical, SMA for regime.
    20 EMA = tactical trend, 50 SMA = swing trend, 200 SMA = regime filter.
    Expert says don't overweight golden/death crosses for 1-4 week horizon."""
    cfg = _get_signal_config("moving_averages")
    close = df["Close"]
    current_price = float(close.iloc[-1])
    score = 0.0

    ema20 = ta.ema(close, length=20)
    sma50 = ta.sma(close, length=50)
    sma200 = ta.sma(close, length=200)

    ema20_val = float(ema20.iloc[-1]) if ema20 is not None and not ema20.dropna().empty else None
    sma50_val = float(sma50.iloc[-1]) if sma50 is not None and not sma50.dropna().empty else None
    sma200_val = float(sma200.iloc[-1]) if sma200 is not None and not sma200.dropna().empty else None

    # Price vs EMAs/SMAs
    if ema20_val and current_price > ema20_val:
        score += 20  # above tactical trend
    elif ema20_val:
        score -= 20

    if sma50_val and current_price > sma50_val:
        score += 20  # above swing trend
    elif sma50_val:
        score -= 20

    # 200 SMA as regime filter (heavier weight)
    if sma200_val and current_price > sma200_val:
        score += 25  # bullish regime
    elif sma200_val:
        score -= 25  # bearish regime

    # EMA/SMA alignment bonus (20 > 50 > 200 = fully aligned uptrend)
    if ema20_val and sma50_val and sma200_val:
        if ema20_val > sma50_val > sma200_val:
            score += 15  # fully aligned uptrend
        elif ema20_val < sma50_val < sma200_val:
            score -= 15  # fully aligned downtrend

    return _clamp(score)

def calc_volume_signal(df: pd.DataFrame) -> float:
    """Volume signal using relative volume (RVOL).
    RVOL >= 1.5 = confirmation. RVOL >= 2.0 = strong.
    Direction matches price direction. Tracks distribution days."""
    cfg = _get_signal_config("volume")
    lookback = cfg.get("lookback", 20)
    rvol_confirm = cfg.get("rvol_confirm", 1.5)
    rvol_strong = cfg.get("rvol_strong", 2.0)

    if len(df) < lookback + 1:
        return 0.0

    current_vol = float(df["Volume"].iloc[-1])
    avg_vol = float(df["Volume"].iloc[-lookback - 1 : -1].mean())
    if avg_vol == 0:
        return 0.0

    rvol = current_vol / avg_vol
    price_change = float(df["Close"].iloc[-1]) - float(df["Close"].iloc[-2])
    direction = 1.0 if price_change > 0 else -1.0

    # Check for distribution days (down days on heavy volume = bearish)
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
    elif rvol >= 1.0:
        score = direction * 15.0
    elif rvol < 0.5:
        score = direction * -10.0  # very low volume = contrarian hint

    # Penalize for distribution pattern
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
            score *= 1.3  # confirmed breakout
        else:
            score *= 0.5  # unconfirmed -- weaker

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
    """Gap signal: gap up/down from prior close. Small gaps (0.5-1%) mild,
    large gaps (>2%) strong. Direction matches gap direction."""
    cfg = _get_signal_config("gap")
    threshold_pct = cfg.get("threshold_pct", 2.0)
    if len(df) < 2:
        return 0.0
    current_open = float(df["Open"].iloc[-1])
    prev_close = float(df["Close"].iloc[-2])
    if prev_close == 0:
        return 0.0
    gap_pct = ((current_open - prev_close) / prev_close) * 100

    if abs(gap_pct) < 0.3:
        return 0.0  # too small to matter

    # Graduated scoring: small gaps get mild scores, big gaps get strong
    score = (gap_pct / threshold_pct) * 40
    return _clamp(score)

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
