"""Market regime detection using SPY trend and VIX levels.

Regimes:
- TRENDING: SPY > 20 EMA > 50 SMA, ADX > 25 → full deployment
- RANGING: SPY between 20 EMA and 50 SMA, ADX < 20 → cautious
- CORRECTING: SPY < 50 SMA or drawdown > 5% → defensive
- SELLING_OFF: SPY < 200 SMA or VIX > 25 → pause new buys
"""
import logging

import pandas as pd
import pandas_ta as ta

from stockpulse.data.provider import get_price_history
from stockpulse.config.settings import load_strategies

logger = logging.getLogger(__name__)


def detect_regime() -> dict:
    """Detect current market regime from SPY and VIX data.

    Returns {
        regime: "trending" | "ranging" | "correcting" | "selling_off",
        spy_price: float,
        spy_ema20: float,
        spy_sma50: float,
        spy_sma200: float,
        spy_adx: float,
        spy_rsi: float,
        spy_drawdown_pct: float,
        vix_level: float,
        confidence: int (0-100),
        adjustment: dict,
    }
    """
    config = load_strategies().get("market_regime", {})
    if not config.get("enabled", True):
        return _default_regime()

    try:
        spy_df = get_price_history("SPY", period="1y")
        if spy_df.empty or len(spy_df) < 200:
            return _default_regime()

        # Compute SPY technicals
        close = spy_df["Close"]
        ema20 = ta.ema(close, length=20)
        sma50 = ta.sma(close, length=50)
        sma200 = ta.sma(close, length=200)
        adx_data = ta.adx(spy_df["High"], spy_df["Low"], close, length=14)
        rsi = ta.rsi(close, length=14)

        price = float(close.iloc[-1])
        ema20_val = float(ema20.iloc[-1])
        sma50_val = float(sma50.iloc[-1])
        sma200_val = float(sma200.iloc[-1])
        adx_val = float(adx_data.iloc[-1, 0]) if adx_data is not None else 15.0
        rsi_val = float(rsi.iloc[-1]) if rsi is not None else 50.0

        # SPY drawdown from 52-week high
        high_52w = float(close.rolling(252).max().iloc[-1])
        spy_dd = ((high_52w - price) / high_52w) * 100 if high_52w > 0 else 0

        # VIX level
        vix_level = _get_vix()

        # Determine regime
        vix_high = config.get("vix_high", 25)
        vix_extreme = config.get("vix_extreme", 35)
        correction_thresh = config.get("correction_threshold_pct", 5)

        if price < sma200_val or vix_level >= vix_extreme:
            regime = "selling_off"
            confidence = 90 if vix_level >= vix_extreme else 75
        elif price < sma50_val or spy_dd > correction_thresh or vix_level >= vix_high:
            regime = "correcting"
            confidence = 80 if spy_dd > correction_thresh else 65
        elif price > ema20_val and ema20_val > sma50_val and adx_val > 25:
            regime = "trending"
            confidence = min(90, int(50 + adx_val))
        else:
            regime = "ranging"
            confidence = 60

        adjustment = get_regime_adjustments(regime, config)

        return {
            "regime": regime,
            "spy_price": round(price, 2),
            "spy_ema20": round(ema20_val, 2),
            "spy_sma50": round(sma50_val, 2),
            "spy_sma200": round(sma200_val, 2),
            "spy_adx": round(adx_val, 1),
            "spy_rsi": round(rsi_val, 1),
            "spy_drawdown_pct": round(spy_dd, 1),
            "vix_level": round(vix_level, 1),
            "confidence": confidence,
            "adjustment": adjustment,
        }

    except Exception:
        logger.exception("Failed to detect market regime")
        return _default_regime()


def get_regime_adjustments(regime: str, config: dict | None = None) -> dict:
    """Get advisor adjustments for the given regime."""
    if config is None:
        config = load_strategies().get("market_regime", {})

    adjustments = config.get("regime_adjustments", {})
    defaults = {
        "trending": {"cash_reserve_mult": 1.0, "buy_threshold_add": 0, "starter_enabled": True},
        "ranging": {"cash_reserve_mult": 1.2, "buy_threshold_add": 5, "starter_enabled": True},
        "correcting": {"cash_reserve_mult": 1.5, "buy_threshold_add": 10, "starter_enabled": False},
        "selling_off": {"cash_reserve_mult": 2.0, "buy_threshold_add": 20, "starter_enabled": False},
    }

    return adjustments.get(regime, defaults.get(regime, defaults["ranging"]))


def _get_vix() -> float:
    """Get current VIX level."""
    try:
        import yfinance as yf
        vix = yf.download("^VIX", period="5d", progress=False)
        if isinstance(vix.columns, pd.MultiIndex):
            vix.columns = vix.columns.get_level_values(0)
        if not vix.empty:
            return float(vix["Close"].iloc[-1])
    except Exception:
        logger.debug("Failed to fetch VIX")
    return 15.0  # Default calm market


def _default_regime() -> dict:
    """Fallback when regime detection is unavailable."""
    return {
        "regime": "ranging",
        "spy_price": 0, "spy_ema20": 0, "spy_sma50": 0, "spy_sma200": 0,
        "spy_adx": 0, "spy_rsi": 50, "spy_drawdown_pct": 0,
        "vix_level": 15, "confidence": 0,
        "adjustment": get_regime_adjustments("ranging"),
    }
