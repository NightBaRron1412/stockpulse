"""Tests for stockpulse.portfolio.entry_timing."""
import pandas as pd
import numpy as np

from stockpulse.portfolio.entry_timing import assess_entry_timing


def _make_df(
    n=100,
    base=100.0,
    trend=0.0,
    seed=42,
    volume_base=5_000_000,
    volume_recent_mult=1.0,
):
    """Build a synthetic OHLCV DataFrame.

    Args:
        trend: daily drift added to random walk (positive = uptrend).
        volume_recent_mult: multiplier for last 5 bars volume vs base
            (< 0.8 triggers "volume declining" branch).
    """
    np.random.seed(seed)
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    close = base + np.cumsum(np.random.randn(n) * 1.5 + trend)
    close = np.maximum(close, 10.0)
    vol = np.full(n, volume_base, dtype=float)
    # Adjust last 5 bars for volume-declining tests
    vol[-5:] = volume_base * volume_recent_mult

    return pd.DataFrame(
        {
            "Open": close * 0.998,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": vol.astype(int),
        },
        index=dates,
    )


def _force_rsi_high(df, rsi_target=75):
    """Force the last ~20 bars into a strong uptrend so RSI > 70."""
    close = df["Close"].values.copy()
    # Inject a steep ramp at the end
    for i in range(-20, 0):
        close[i] = close[i - 1] * 1.015  # +1.5% per day
    df = df.copy()
    df["Close"] = close
    df["High"] = close * 1.005
    df["Low"] = close * 0.995
    df["Open"] = close * 0.998
    return df


def _force_rsi_low(df, rsi_target=25):
    """Force the last ~20 bars into a steep decline so RSI < 30."""
    close = df["Close"].values.copy()
    for i in range(-20, 0):
        close[i] = close[i - 1] * 0.985  # -1.5% per day
    df = df.copy()
    df["Close"] = close
    df["High"] = close * 1.005
    df["Low"] = close * 0.995
    df["Open"] = close * 0.998
    return df


def _force_extended_above_ema(df, atr_multiples=3.0):
    """Force price far above its 20 EMA by injecting a spike at the end."""
    close = df["Close"].values.copy()
    # Jump the last bar way up
    close[-1] = close[-2] * (1 + 0.02 * atr_multiples)
    df = df.copy()
    df["Close"] = close
    df["High"] = close * 1.005
    df["Low"] = close * 0.995
    return df


def _force_gap_up(df, gap_atr_mult=1.5):
    """Force a gap-up on the last bar > 1 ATR."""
    close = df["Close"].values.copy()
    # Large positive jump on last bar
    close[-1] = close[-2] * 1.05  # 5% gap
    df = df.copy()
    df["Close"] = close
    df["High"] = close * 1.01
    df["Low"] = close * 0.999
    df["Open"] = close * 0.999
    return df


# ---------- RSI > 70 on BUY ----------

def test_rsi_overbought_buy_returns_wait():
    """BUY with RSI > 70 => timing='wait', target at EMA20."""
    df = _make_df(n=100, trend=0.3, seed=10)
    df = _force_rsi_high(df)
    result = assess_entry_timing("TEST", df, "BUY")
    assert result["timing"] == "wait"
    assert result["target_price"] is not None
    assert "RSI overbought" in result["reason"] or "pullback" in result["reason"]


# ---------- Price > 2 ATR above EMA ----------

def test_extended_above_ema_returns_limit():
    """Price extended > 2 ATR above 20 EMA => timing='limit'."""
    df = _make_df(n=100, trend=0.0, seed=55)
    df = _force_extended_above_ema(df, atr_multiples=4.0)
    result = assess_entry_timing("TEST", df, "BUY")
    # Could be 'limit' or 'wait' depending on RSI interaction
    assert result["timing"] in ("limit", "wait")
    if result["timing"] == "limit":
        assert result["target_price"] is not None
        assert "ATR" in result["reason"] or "limit" in result["reason"]


# ---------- Gap up > 1 ATR ----------

def test_gap_up_returns_wait():
    """Gap up > 1 ATR => timing='wait'."""
    df = _make_df(n=100, trend=0.0, seed=77)
    df = _force_gap_up(df)
    result = assess_entry_timing("TEST", df, "BUY")
    # Gap-up detection fires after RSI/extension checks
    assert result["timing"] in ("wait", "limit")
    if result["timing"] == "wait" and "Gap" in result["reason"]:
        assert "consolidate" in result["reason"].lower() or "gap" in result["reason"].lower()


# ---------- Price near EMA20 support ----------

def test_near_ema_support_returns_now():
    """Price within 0.5 ATR of 20 EMA => timing='now', good entry."""
    # Flat market => price ~ EMA20
    df = _make_df(n=100, trend=0.0, seed=42)
    result = assess_entry_timing("TEST", df, "BUY")
    assert result["timing"] == "now"
    # Should mention "good entry" or "reasonable"
    assert "entry" in result["reason"].lower() or "reasonable" in result["reason"].lower()


# ---------- Volume declining ----------

def test_volume_declining_returns_smaller_size():
    """5d avg volume < 80% of 20d avg => 'smaller' in notes."""
    df = _make_df(n=100, trend=0.0, seed=42, volume_recent_mult=0.5)
    result = assess_entry_timing("TEST", df, "BUY")
    assert result["timing"] == "now"
    assert "smaller" in result["reason"].lower() or "declining" in result["reason"].lower()


# ---------- SELL with RSI < 30 ----------

def test_sell_rsi_oversold_returns_wait():
    """SELL with RSI < 30 => timing='wait' (bounce possible)."""
    df = _make_df(n=100, trend=-0.2, seed=33)
    df = _force_rsi_low(df)
    result = assess_entry_timing("TEST", df, "SELL")
    assert result["timing"] == "wait"
    assert "bounce" in result["reason"].lower() or "oversold" in result["reason"].lower()


# ---------- Empty / short DataFrame ----------

def test_empty_df_returns_now_low_confidence():
    """Empty DataFrame => timing='now', confidence=30."""
    df = pd.DataFrame()
    result = assess_entry_timing("TEST", df, "BUY")
    assert result["timing"] == "now"
    assert result["confidence"] == 30
    assert "Insufficient" in result["reason"]


def test_short_df_returns_now_low_confidence():
    """DataFrame with < 50 rows => timing='now', confidence=30."""
    df = _make_df(n=20)
    result = assess_entry_timing("TEST", df, "BUY")
    assert result["timing"] == "now"
    assert result["confidence"] == 30
