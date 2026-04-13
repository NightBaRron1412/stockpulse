import pandas as pd
import numpy as np
from stockpulse.signals.engine import compute_all_signals
from stockpulse.signals.composite import compute_composite_score, classify_action

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

def test_compute_all_signals_returns_dict():
    df = _make_price_df(n=260)
    signals = compute_all_signals("TEST", df)
    assert isinstance(signals, dict)
    assert "rsi" in signals
    assert "macd" in signals
    assert "moving_averages" in signals
    assert all("score" in v for v in signals.values())

def test_composite_score_bounded():
    signals = {
        "rsi": {"score": 50, "weight": 0.15, "value": 35},
        "macd": {"score": 30, "weight": 0.15, "value": "bullish"},
        "moving_averages": {"score": 20, "weight": 0.15, "value": "above_50_200"},
        "volume": {"score": 0, "weight": 0.10, "value": 1.2},
        "breakout": {"score": 10, "weight": 0.10, "value": 0.7},
        "gap": {"score": 0, "weight": 0.05, "value": 0.5},
        "adx": {"score": 40, "weight": 0.10, "value": 30},
        "earnings": {"score": 20, "weight": 0.05, "value": 8},
        "sec_filing": {"score": 15, "weight": 0.10, "value": 2},
        "news_sentiment": {"score": 10, "weight": 0.05, "value": 0.3},
    }
    score = compute_composite_score(signals)
    assert -100 <= score <= 100

def test_classify_action():
    assert classify_action(50) == "BUY"
    assert classify_action(20) == "HOLD"
    assert classify_action(0) == "HOLD"
    assert classify_action(-50) == "SELL"
