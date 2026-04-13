from unittest.mock import patch
from stockpulse.portfolio.tracker import get_portfolio_status


def test_get_portfolio_status_empty():
    with patch("stockpulse.portfolio.tracker.load_portfolio", return_value={"positions": []}):
        status = get_portfolio_status()
        assert status["total_invested"] == 0
        assert status["total_pnl"] == 0
        assert status["positions"] == []


def test_get_portfolio_status_calculates_pnl():
    mock_portfolio = {
        "positions": [
            {"ticker": "TEST", "shares": 10, "entry_price": 100.0, "entry_date": "2025-01-01"},
        ],
        "alerts": {"pnl_milestones": [5, 10], "check_invalidation": True},
    }
    mock_quote = {"price": 110.0, "previous_close": 108.0, "market_cap": 0}

    with patch("stockpulse.portfolio.tracker.load_portfolio", return_value=mock_portfolio), \
         patch("stockpulse.portfolio.tracker.get_current_quote", return_value=mock_quote):
        status = get_portfolio_status()
        assert len(status["positions"]) == 1
        pos = status["positions"][0]
        assert pos["ticker"] == "TEST"
        assert pos["invested"] == 1000.0
        assert pos["current_value"] == 1100.0
        assert pos["pnl"] == 100.0
        assert pos["pnl_pct"] == 10.0
        assert status["total_pnl"] == 100.0
        assert status["total_pnl_pct"] == 10.0
