"""Entry timing assessment for advisor suggestions.

Evaluates whether now is a good time to enter, or if the setup
suggests waiting for a better price.
"""
import logging

import pandas as pd
import pandas_ta as ta

logger = logging.getLogger(__name__)


def assess_entry_timing(ticker: str, df: pd.DataFrame, action: str) -> dict:
    """Assess entry timing for a ticker.

    Returns {
        timing: "now" | "wait" | "limit",
        reason: str,
        target_price: float | None,
        confidence: int (0-100),
    }
    """
    if df.empty or len(df) < 50:
        return {"timing": "now", "reason": "Insufficient data for timing analysis", "target_price": None, "confidence": 30}

    try:
        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        price = float(close.iloc[-1])

        # Compute indicators
        rsi = ta.rsi(close, length=14)
        ema20 = ta.ema(close, length=20)
        sma50 = ta.sma(close, length=50)
        atr = ta.atr(high, low, close, length=14)

        rsi_val = float(rsi.iloc[-1]) if rsi is not None else 50.0
        ema20_val = float(ema20.iloc[-1]) if ema20 is not None else price
        sma50_val = float(sma50.iloc[-1]) if sma50 is not None else price
        atr_val = float(atr.iloc[-1]) if atr is not None else price * 0.02

        # Volume trend (last 5 days vs 20-day avg)
        vol = df["Volume"]
        vol_5d = float(vol.iloc[-5:].mean()) if len(vol) >= 5 else float(vol.mean())
        vol_20d = float(vol.iloc[-20:].mean()) if len(vol) >= 20 else float(vol.mean())
        vol_declining = vol_5d < vol_20d * 0.8

        # Gap detection
        prev_close = float(close.iloc[-2]) if len(close) >= 2 else price
        gap_pct = ((price - prev_close) / prev_close) * 100 if prev_close > 0 else 0
        gap_vs_atr = abs(price - prev_close) / atr_val if atr_val > 0 else 0

        # Distance from 20 EMA
        distance_from_ema = ((price - ema20_val) / ema20_val) * 100 if ema20_val > 0 else 0
        distance_in_atr = (price - ema20_val) / atr_val if atr_val > 0 else 0

        # Evaluate timing
        reasons = []
        timing = "now"
        target_price = None
        confidence = 70

        # 1. RSI overbought on buy signal
        if action in ("BUY", "WATCHLIST", "WATCH") and rsi_val > 70:
            timing = "wait"
            target_price = round(ema20_val, 2)
            reasons.append(f"RSI overbought at {rsi_val:.0f} — wait for pullback to 20 EMA (${ema20_val:.2f})")
            confidence = 80

        # 2. Price extended above 20 EMA (> 2 ATR)
        elif action in ("BUY", "WATCHLIST", "WATCH") and distance_in_atr > 2.0:
            timing = "limit"
            target_price = round(ema20_val + atr_val, 2)
            reasons.append(f"Extended {distance_in_atr:.1f} ATR above 20 EMA — limit order at ${target_price:.2f}")
            confidence = 75

        # 3. Gap up today > 1 ATR
        elif action in ("BUY", "WATCHLIST", "WATCH") and gap_vs_atr > 1.0 and gap_pct > 0:
            timing = "wait"
            target_price = round(prev_close + atr_val * 0.5, 2)
            reasons.append(f"Gapped up {gap_pct:.1f}% today — let it consolidate before entry")
            confidence = 70

        # 4. Volume declining
        elif action in ("BUY", "WATCHLIST", "WATCH") and vol_declining:
            timing = "now"
            reasons.append(f"Volume declining (5d avg {vol_5d/vol_20d:.0%} of 20d) — consider smaller position size")
            confidence = 55

        # 5. Price at support (within 0.5 ATR of 20 EMA or 50 SMA)
        elif action in ("BUY", "WATCHLIST", "WATCH"):
            if abs(distance_in_atr) < 0.5:
                reasons.append(f"Near 20 EMA support (${ema20_val:.2f}) — good entry zone")
                confidence = 85
            elif abs(price - sma50_val) / atr_val < 0.5 and price > sma50_val:
                reasons.append(f"Near 50 SMA support (${sma50_val:.2f}) — good entry zone")
                confidence = 80
            else:
                reasons.append("No timing concerns — entry at current levels is reasonable")
                confidence = 65

        # 6. SELL timing
        if action in ("SELL", "TRIM"):
            if rsi_val < 30:
                timing = "wait"
                reasons = [f"RSI oversold at {rsi_val:.0f} — may bounce, consider waiting for rally to trim"]
                confidence = 60
            elif distance_in_atr < -2.0:
                timing = "wait"
                target_price = round(ema20_val, 2)
                reasons = [f"Already {abs(distance_in_atr):.1f} ATR below 20 EMA — selling into weakness"]
                confidence = 55
            else:
                reasons = ["Reasonable exit level"]
                confidence = 70

        return {
            "timing": timing,
            "reason": "; ".join(reasons) if reasons else "No timing signal",
            "target_price": target_price,
            "confidence": confidence,
        }

    except Exception:
        logger.debug("Entry timing failed for %s", ticker)
        return {"timing": "now", "reason": "Timing analysis unavailable", "target_price": None, "confidence": 30}
