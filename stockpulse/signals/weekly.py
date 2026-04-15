"""Weekly trend filter — uses completed weekly bars as quality overlay.

NOT a co-equal signal engine. Used as a filter for position sizing:
- Weekly aligned: normal BUY size
- Weekly mixed: WATCHLIST / reduced size
- Weekly down: block full-size BUYs (except strong event-driven)
"""
import logging

import pandas as pd
import pandas_ta as ta

logger = logging.getLogger(__name__)


def assess_weekly_trend(df_daily: pd.DataFrame) -> dict:
    """Assess weekly trend from daily data (resampled to weekly).

    Uses only the last COMPLETED week to avoid partial bar bias.

    Returns {
        trend: "up" | "mixed" | "down",
        above_10w: bool,
        above_30w: bool,
        slope_30w_positive: bool,
        weekly_rsi: float,
        size_multiplier: float (1.0 / 0.75 / 0.5),
    }
    """
    if df_daily.empty or len(df_daily) < 150:
        return {"trend": "mixed", "above_10w": False, "above_30w": False,
                "slope_30w_positive": False, "weekly_rsi": 50.0, "size_multiplier": 1.0}

    try:
        # Resample to weekly (use last completed week only)
        weekly = df_daily.resample("W-FRI").agg({
            "Open": "first", "High": "max", "Low": "min",
            "Close": "last", "Volume": "sum",
        }).dropna()

        if len(weekly) < 30:
            return {"trend": "mixed", "above_10w": False, "above_30w": False,
                    "slope_30w_positive": False, "weekly_rsi": 50.0, "size_multiplier": 1.0}

        # Use the second-to-last row (last COMPLETED week)
        close = weekly["Close"]
        last_close = float(close.iloc[-2])  # last completed week

        sma10w = ta.sma(close, length=10)
        sma30w = ta.sma(close, length=30)
        rsi_w = ta.rsi(close, length=14)

        sma10_val = float(sma10w.iloc[-2]) if sma10w is not None else last_close
        sma30_val = float(sma30w.iloc[-2]) if sma30w is not None else last_close
        rsi_val = float(rsi_w.iloc[-2]) if rsi_w is not None else 50.0

        above_10w = last_close > sma10_val
        above_30w = last_close > sma30_val

        # 30-week slope: positive if current > 4 weeks ago
        slope_positive = False
        if sma30w is not None and len(sma30w) > 6:
            slope_positive = float(sma30w.iloc[-2]) > float(sma30w.iloc[-6])

        # Determine trend
        if above_10w and above_30w and slope_positive:
            trend = "up"
            size_mult = 1.0
        elif not above_10w and not above_30w:
            trend = "down"
            size_mult = 0.5  # block full-size, reduce to half
        else:
            trend = "mixed"
            size_mult = 0.75

        return {
            "trend": trend,
            "above_10w": above_10w,
            "above_30w": above_30w,
            "slope_30w_positive": slope_positive,
            "weekly_rsi": round(rsi_val, 1),
            "size_multiplier": size_mult,
        }

    except Exception:
        logger.debug("Weekly trend assessment failed")
        return {"trend": "mixed", "above_10w": False, "above_30w": False,
                "slope_30w_positive": False, "weekly_rsi": 50.0, "size_multiplier": 1.0}
