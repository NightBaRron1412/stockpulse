import pandas as pd
import numpy as np
from stockpulse.research.recommendation import generate_recommendation

def _make_price_df(n=260, base=100.0, trend=0.1):
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    close = base + np.cumsum(np.random.randn(n) * 2 + trend)
    close = np.maximum(close, 1.0)
    return pd.DataFrame({
        "Open": close * 0.99, "High": close * 1.02,
        "Low": close * 0.98, "Close": close,
        "Volume": np.random.randint(1_000_000, 10_000_000, n),
    }, index=dates)

def test_generate_recommendation_returns_valid_structure():
    df = _make_price_df()
    rec = generate_recommendation("TEST", df)
    assert rec["ticker"] == "TEST"
    assert rec["action"] in ("BUY", "HOLD", "SELL")
    assert 0 <= rec["confidence"] <= 100
    assert isinstance(rec["thesis"], str)
    assert isinstance(rec["technical_summary"], str)
    assert isinstance(rec["catalyst_summary"], str)
    assert isinstance(rec["invalidation"], str)
    assert isinstance(rec["signals"], dict)
    assert "timestamp" in rec
