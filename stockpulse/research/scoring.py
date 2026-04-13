"""Confidence scoring and invalidation generation."""
import pandas as pd
import pandas_ta as ta

def compute_invalidation(ticker: str, action: str, df: pd.DataFrame) -> str:
    if df.empty:
        return "Insufficient data for invalidation levels"
    sma50 = ta.sma(df["Close"], length=50)
    sma50_val = float(sma50.iloc[-1]) if sma50 is not None and not sma50.dropna().empty else None
    parts = []
    if action == "BUY":
        if sma50_val:
            parts.append(f"Close below 50-day SMA (${sma50_val:.2f})")
        parts.append("RSI > 75")
    elif action == "SELL":
        if sma50_val:
            parts.append(f"Close above 50-day SMA (${sma50_val:.2f})")
        parts.append("RSI < 25")
    else:
        parts.append("No specific invalidation for HOLD")
    return " or ".join(parts) if parts else "Monitor for significant change"
