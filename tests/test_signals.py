import pandas as pd
import numpy as np
from stockpulse.signals.technical import (
    calc_rsi_signal, calc_macd_signal, calc_ma_signal,
    calc_volume_signal, calc_breakout_signal, calc_gap_signal, calc_adx_signal,
)

def _make_price_df(n=100, base=100.0, trend=0.1):
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    close = base + np.cumsum(np.random.randn(n) * 2 + trend)
    close = np.maximum(close, 1.0)
    return pd.DataFrame({
        "Open": close * 0.99, "High": close * 1.02,
        "Low": close * 0.98, "Close": close,
        "Volume": np.random.randint(1_000_000, 10_000_000, n),
    }, index=dates)

def test_rsi_signal_returns_bounded_score():
    df = _make_price_df()
    score = calc_rsi_signal(df)
    assert -100 <= score <= 100

def test_macd_signal_returns_bounded_score():
    df = _make_price_df()
    score = calc_macd_signal(df)
    assert -100 <= score <= 100

def test_ma_signal_returns_bounded_score():
    df = _make_price_df()
    score = calc_ma_signal(df)
    assert -100 <= score <= 100

def test_volume_signal_returns_bounded_score():
    df = _make_price_df()
    score = calc_volume_signal(df)
    assert -100 <= score <= 100

def test_breakout_signal_returns_bounded_score():
    df = _make_price_df(n=260)
    score = calc_breakout_signal(df)
    assert -100 <= score <= 100

def test_gap_signal_returns_bounded_score():
    df = _make_price_df()
    score = calc_gap_signal(df)
    assert -100 <= score <= 100

def test_adx_signal_returns_bounded_score():
    df = _make_price_df()
    score = calc_adx_signal(df)
    assert -100 <= score <= 100
