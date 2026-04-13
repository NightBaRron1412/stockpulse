"""Confidence scoring and invalidation generation."""
import pandas as pd
import pandas_ta as ta

def compute_invalidation(ticker: str, action: str, df: pd.DataFrame) -> str:
    """Generate invalidation conditions with ATR-based levels per expert."""
    if df.empty:
        return "Insufficient data for invalidation levels"

    current_price = float(df["Close"].iloc[-1])
    sma50 = ta.sma(df["Close"], length=50)
    ema20 = ta.ema(df["Close"], length=20)
    atr = ta.atr(df["High"], df["Low"], df["Close"], length=14)

    sma50_val = float(sma50.iloc[-1]) if sma50 is not None and not sma50.dropna().empty else None
    ema20_val = float(ema20.iloc[-1]) if ema20 is not None and not ema20.dropna().empty else None
    atr_val = float(atr.iloc[-1]) if atr is not None and not atr.dropna().empty else None

    parts = []
    if action in ("BUY", "WATCHLIST"):
        if atr_val:
            stop = current_price - 1.5 * atr_val
            parts.append(f"Stop: ${stop:.2f} (1.5 ATR below entry)")
        if ema20_val:
            parts.append(f"Close below 20 EMA (${ema20_val:.2f}) on heavy volume")
        if sma50_val:
            parts.append(f"Break below 50 SMA (${sma50_val:.2f})")
    elif action == "SELL":
        if sma50_val:
            parts.append(f"Close above 50 SMA (${sma50_val:.2f})")
        if atr_val:
            stop = current_price + 1.5 * atr_val
            parts.append(f"Stop: ${stop:.2f} (1.5 ATR above)")
    else:
        # HOLD — still provide key levels
        levels = []
        if ema20_val:
            levels.append(f"20 EMA: ${ema20_val:.2f}")
        if sma50_val:
            levels.append(f"50 SMA: ${sma50_val:.2f}")
        if levels:
            parts.append(f"Key levels: {', '.join(levels)}")
        else:
            parts.append("Monitor for trend change")

    return " | ".join(parts) if parts else "Monitor for significant change"
