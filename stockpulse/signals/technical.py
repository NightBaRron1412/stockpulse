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
    cfg = _get_signal_config("rsi")
    period = cfg.get("period", 14)
    oversold = cfg.get("oversold", 30)
    overbought = cfg.get("overbought", 70)
    rsi = ta.rsi(df["Close"], length=period)
    if rsi is None or rsi.dropna().empty:
        return 0.0
    current_rsi = float(rsi.iloc[-1])
    midpoint = (oversold + overbought) / 2
    half_range = (overbought - oversold) / 2
    score = -((current_rsi - midpoint) / half_range) * 100
    return _clamp(score)

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
    cfg = _get_signal_config("moving_averages")
    periods = cfg.get("periods", [20, 50, 200])
    close = df["Close"]
    current_price = float(close.iloc[-1])
    score = 0.0
    smas = {}
    for p in periods:
        sma = ta.sma(close, length=p)
        if sma is not None and not sma.dropna().empty:
            smas[p] = float(sma.iloc[-1])
    for p, sma_val in smas.items():
        if current_price > sma_val:
            score += 20
        else:
            score -= 20
    if 50 in smas and 200 in smas:
        sma50 = ta.sma(close, length=50)
        sma200 = ta.sma(close, length=200)
        if sma50 is not None and sma200 is not None and len(sma50.dropna()) > 1 and len(sma200.dropna()) > 1:
            curr_50 = float(sma50.iloc[-1])
            prev_50 = float(sma50.iloc[-2])
            curr_200 = float(sma200.iloc[-1])
            prev_200 = float(sma200.iloc[-2])
            if prev_50 <= prev_200 and curr_50 > curr_200:
                score += 30
            elif prev_50 >= prev_200 and curr_50 < curr_200:
                score -= 30
    return _clamp(score)

def calc_volume_signal(df: pd.DataFrame) -> float:
    cfg = _get_signal_config("volume")
    lookback = cfg.get("lookback", 20)
    spike_threshold = cfg.get("spike_threshold", 2.0)
    if len(df) < lookback + 1:
        return 0.0
    current_vol = float(df["Volume"].iloc[-1])
    avg_vol = float(df["Volume"].iloc[-lookback - 1 : -1].mean())
    if avg_vol == 0:
        return 0.0
    ratio = current_vol / avg_vol
    if ratio < 1.0:
        return 0.0
    price_change = float(df["Close"].iloc[-1]) - float(df["Close"].iloc[-2])
    if ratio >= spike_threshold:
        magnitude = min((ratio - 1.0) * 30, 100.0)
        return _clamp(magnitude if price_change > 0 else -magnitude)
    return 0.0

def calc_breakout_signal(df: pd.DataFrame) -> float:
    cfg = _get_signal_config("breakout")
    lookback = cfg.get("lookback_days", 252)
    if len(df) < lookback:
        lookback = len(df) - 1
    if lookback < 20:
        return 0.0
    current_price = float(df["Close"].iloc[-1])
    high_52w = float(df["High"].iloc[-lookback:].max())
    low_52w = float(df["Low"].iloc[-lookback:].min())
    price_range = high_52w - low_52w
    if price_range == 0:
        return 0.0
    position = (current_price - low_52w) / price_range
    if position > 0.95:
        return _clamp(80.0)
    elif position < 0.05:
        return _clamp(-80.0)
    else:
        return _clamp((position - 0.5) * 100)

def calc_gap_signal(df: pd.DataFrame) -> float:
    cfg = _get_signal_config("gap")
    threshold_pct = cfg.get("threshold_pct", 2.0)
    if len(df) < 2:
        return 0.0
    current_open = float(df["Open"].iloc[-1])
    prev_close = float(df["Close"].iloc[-2])
    if prev_close == 0:
        return 0.0
    gap_pct = ((current_open - prev_close) / prev_close) * 100
    if abs(gap_pct) < threshold_pct:
        return 0.0
    score = (gap_pct / threshold_pct) * 30
    return _clamp(score)

def calc_adx_signal(df: pd.DataFrame) -> float:
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
    if adx_val < trend_threshold:
        return 0.0
    plus_di = float(adx_df[dmp_col].iloc[-1]) if dmp_col in adx_df.columns else 0
    minus_di = float(adx_df[dmn_col].iloc[-1]) if dmn_col in adx_df.columns else 0
    direction = 1.0 if plus_di > minus_di else -1.0
    strength = min((adx_val - trend_threshold) * 2, 80.0)
    return _clamp(direction * strength)
