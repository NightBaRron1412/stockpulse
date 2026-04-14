from unittest.mock import patch

from stockpulse.portfolio.risk import (
    check_concentration_limits,
    compute_position_size,
    check_drawdown_status,
)


def test_drawdown_status_normal():
    result = check_drawdown_status(current_equity=95000, peak_equity=100000)
    assert result["drawdown_pct"] == 5.0
    assert result["size_multiplier"] == 1.0
    assert result["new_buys_paused"] is False


def test_drawdown_status_half():
    result = check_drawdown_status(current_equity=91000, peak_equity=100000)
    assert result["drawdown_pct"] == 9.0
    assert result["size_multiplier"] == 0.5
    assert result["new_buys_paused"] is False


def test_drawdown_status_paused():
    result = check_drawdown_status(current_equity=87000, peak_equity=100000)
    assert result["drawdown_pct"] == 13.0
    assert result["new_buys_paused"] is True


def test_position_size_basic():
    result = compute_position_size(
        portfolio_value=100000, entry_price=150.0, atr=5.0, confidence=50
    )
    assert result["shares"] > 0
    assert result["stop_price"] < 150.0
    assert result["dollar_amount"] <= 8000  # max 8% of portfolio


def test_concentration_max_positions():
    positions = [
        {"ticker": f"T{i}", "shares": 10, "entry_price": 100} for i in range(8)
    ]
    with patch(
        "stockpulse.portfolio.risk._get_ticker_info",
        return_value={"sector": "Unknown", "industry": "Unknown"},
    ), patch(
        "stockpulse.portfolio.risk._compute_correlation",
        return_value=0.0,
    ), patch(
        "stockpulse.portfolio.risk.get_earnings_dates",
        return_value=[],
    ):
        result = check_concentration_limits("NEW", positions, 100000)
    assert result["allowed"] is False
    assert "Max positions" in result["reasons"][0]


def test_concentration_sector_cap():
    """Sector at 20% + 8% new = 28% > 25% cap -> blocked."""
    positions = [
        {"ticker": "A", "shares": 100, "entry_price": 100},  # 10%
        {"ticker": "B", "shares": 100, "entry_price": 100},  # 10%
    ]

    def mock_info(ticker):
        return {"sector": "Technology", "industry": f"Industry_{ticker}"}

    with patch(
        "stockpulse.portfolio.risk._get_ticker_info", side_effect=mock_info
    ), patch(
        "stockpulse.portfolio.risk._compute_correlation", return_value=0.0
    ), patch(
        "stockpulse.portfolio.risk.get_earnings_dates", return_value=[]
    ):
        result = check_concentration_limits("C", positions, 100000)
    assert result["allowed"] is False
    assert any("Sector" in r for r in result["reasons"])


def test_concentration_allowed():
    """No limits hit -> allowed with full size."""
    positions = [
        {"ticker": "A", "shares": 10, "entry_price": 100},
    ]

    def mock_info(ticker):
        if ticker == "NEW":
            return {"sector": "Healthcare", "industry": "Biotech"}
        return {"sector": "Technology", "industry": "Software"}

    with patch(
        "stockpulse.portfolio.risk._get_ticker_info", side_effect=mock_info
    ), patch(
        "stockpulse.portfolio.risk._compute_correlation", return_value=0.1
    ), patch(
        "stockpulse.portfolio.risk.get_earnings_dates", return_value=[]
    ):
        result = check_concentration_limits("NEW", positions, 100000)
    assert result["allowed"] is True
    assert result["size_multiplier"] == 1.0
    assert result["reasons"] == []


def test_concentration_cluster_penalty():
    """Same industry -> cluster penalty applied."""
    positions = [
        {"ticker": "A", "shares": 10, "entry_price": 50},
    ]

    def mock_info(ticker):
        return {"sector": "Technology", "industry": "Semiconductors"}

    with patch(
        "stockpulse.portfolio.risk._get_ticker_info", side_effect=mock_info
    ), patch(
        "stockpulse.portfolio.risk._compute_correlation", return_value=0.0
    ), patch(
        "stockpulse.portfolio.risk.get_earnings_dates", return_value=[]
    ):
        result = check_concentration_limits("B", positions, 100000)
    assert result["size_multiplier"] == 0.6
    assert "A" in result["cluster_tickers"]


def test_drawdown_zero_peak():
    result = check_drawdown_status(current_equity=100, peak_equity=0)
    assert result["drawdown_pct"] == 0
    assert result["size_multiplier"] == 1.0


def test_position_size_high_confidence():
    low = compute_position_size(100000, 150.0, 5.0, confidence=20)
    high = compute_position_size(100000, 150.0, 5.0, confidence=90)
    assert high["shares"] >= low["shares"]
    assert high["confidence_multiplier"] > low["confidence_multiplier"]
