from unittest.mock import patch, MagicMock
from stockpulse.portfolio.entry import enter_position


def test_enter_position_warns_on_hold_signal():
    """Should warn when entering against a HOLD signal."""
    mock_quote = {"price": 150.0, "previous_close": 148.0}
    mock_portfolio = {"positions": [], "alerts": {"pnl_milestones": [5], "check_invalidation": True}}

    import pandas as pd
    import numpy as np
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=260, freq="B")
    close = 100 + np.cumsum(np.random.randn(260) * 2 + 0.1)
    close = np.maximum(close, 1.0)
    mock_df = pd.DataFrame({
        "Open": close * 0.99, "High": close * 1.02,
        "Low": close * 0.98, "Close": close,
        "Volume": np.random.randint(1_000_000, 10_000_000, 260),
    }, index=dates)

    with patch("stockpulse.portfolio.entry.get_current_quote", return_value=mock_quote), \
         patch("stockpulse.portfolio.entry.get_price_history", return_value=mock_df), \
         patch("stockpulse.portfolio.entry.load_portfolio", return_value=mock_portfolio), \
         patch("stockpulse.portfolio.entry.save_portfolio"), \
         patch("stockpulse.portfolio.entry.dispatch_alert"):

        result = enter_position("TEST", shares=10)
        assert result["success"] is True
        assert result["position"]["ticker"] == "TEST"
        assert result["position"]["shares"] == 10
