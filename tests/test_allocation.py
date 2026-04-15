"""Tests for allocation advisor logic."""
from unittest.mock import patch
from fastapi.testclient import TestClient
from stockpulse.api.server import app

client = TestClient(app)


def _base_portfolio():
    return {
        "timestamp": "",
        "total_invested": 0,
        "total_current": 0,
        "total_pnl": 0,
        "total_pnl_pct": 0,
        "positions": [],
    }


def _base_risk():
    return {
        "allowed": True,
        "reasons": [],
        "size_multiplier": 1.0,
        "sector": "Tech",
        "industry": "Semis",
        "cluster_tickers": [],
    }


def test_allocation_empty_when_no_signals():
    """No BUY/WATCHLIST signals = no allocations."""
    recs = [{"ticker": "AAPL", "action": "HOLD", "composite_score": 5, "confidence": 5, "thesis": "flat"}]
    with patch("stockpulse.api.server._get_latest_scan", return_value=recs), \
         patch("stockpulse.portfolio.tracker.get_portfolio_status", return_value=_base_portfolio()), \
         patch("stockpulse.config.settings.load_portfolio", return_value={"positions": []}), \
         patch("stockpulse.config.settings.load_strategies", return_value={"risk": {"max_positions": 8, "max_position_pct": 8}}), \
         patch("stockpulse.llm.summarizer._call_llm", return_value=None):
        r = client.post("/api/allocate", json={"amount": 5000})
        data = r.json()
        assert len(data["allocations"]) == 0
        assert data["cash_reserve"] == 5000


def test_allocation_respects_max_positions():
    """Should not exceed max_positions = 1 when 1 position already held."""
    recs = [
        {"ticker": "NVDA", "action": "WATCHLIST", "composite_score": 55, "confidence": 50, "thesis": "momentum"},
        {"ticker": "AMD", "action": "WATCHLIST", "composite_score": 50, "confidence": 45, "thesis": "momentum"},
    ]
    # Positions returned by get_portfolio_status include current_value and pnl_pct
    portfolio_positions = [
        {"ticker": "MSFT", "shares": 10, "entry_price": 300, "current_price": 310,
         "current_value": 3100, "pnl_pct": 3.3, "invested": 3000, "pnl": 100},
    ]
    # Positions from load_portfolio (config) only have raw fields
    config_positions = [{"ticker": "MSFT", "shares": 10, "entry_price": 300}]
    mock_portfolio = {**_base_portfolio(), "total_current": 3100, "positions": portfolio_positions}

    with patch("stockpulse.api.server._get_latest_scan", return_value=recs), \
         patch("stockpulse.portfolio.tracker.get_portfolio_status", return_value=mock_portfolio), \
         patch("stockpulse.config.settings.load_portfolio", return_value={"positions": config_positions}), \
         patch("stockpulse.config.settings.load_strategies", return_value={"risk": {"max_positions": 1, "max_position_pct": 8}}), \
         patch("stockpulse.portfolio.risk.check_concentration_limits", return_value=_base_risk()), \
         patch("stockpulse.llm.summarizer._call_llm", return_value=None):
        r = client.post("/api/allocate", json={"amount": 5000})
        data = r.json()
        # max_positions=1, already holding MSFT -> no new positions allowed
        assert len(data["allocations"]) == 0


def test_allocation_cash_reserve_equals_unallocated():
    """Cash reserve should equal amount minus all suggested_amounts."""
    recs = [{"ticker": "JBL", "action": "WATCHLIST", "composite_score": 37.9, "confidence": 37, "thesis": "ok"}]
    with patch("stockpulse.api.server._get_latest_scan", return_value=recs), \
         patch("stockpulse.portfolio.tracker.get_portfolio_status", return_value=_base_portfolio()), \
         patch("stockpulse.config.settings.load_portfolio", return_value={"positions": []}), \
         patch("stockpulse.config.settings.load_strategies", return_value={"risk": {"max_positions": 8, "max_position_pct": 8}}), \
         patch("stockpulse.portfolio.risk.check_concentration_limits", return_value=_base_risk()), \
         patch("stockpulse.llm.summarizer._call_llm", return_value=None):
        r = client.post("/api/allocate", json={"amount": 5000})
        data = r.json()
        total_allocated = sum(a["suggested_amount"] for a in data["allocations"])
        assert abs(data["cash_reserve"] - (5000 - total_allocated)) < 0.01


def test_allocation_skips_risk_blocked_tickers():
    """Tickers blocked by concentration limits should not appear in allocations."""
    recs = [{"ticker": "AAPL", "action": "BUY", "composite_score": 70, "confidence": 65, "thesis": "strong"}]
    blocked_risk = {"allowed": False, "reasons": ["Max positions reached"], "size_multiplier": 1.0, "sector": "Tech", "industry": "Consumer", "cluster_tickers": []}

    with patch("stockpulse.api.server._get_latest_scan", return_value=recs), \
         patch("stockpulse.portfolio.tracker.get_portfolio_status", return_value=_base_portfolio()), \
         patch("stockpulse.config.settings.load_portfolio", return_value={"positions": []}), \
         patch("stockpulse.config.settings.load_strategies", return_value={"risk": {"max_positions": 8, "max_position_pct": 8}}), \
         patch("stockpulse.portfolio.risk.check_concentration_limits", return_value=blocked_risk), \
         patch("stockpulse.llm.summarizer._call_llm", return_value=None):
        r = client.post("/api/allocate", json={"amount": 5000})
        data = r.json()
        tickers_allocated = [a["ticker"] for a in data["allocations"]]
        assert "AAPL" not in tickers_allocated


def test_allocation_total_portfolio_after():
    """total_portfolio_after should equal portfolio current + amount."""
    mock_portfolio = {**_base_portfolio(), "total_current": 3000}
    with patch("stockpulse.api.server._get_latest_scan", return_value=[]), \
         patch("stockpulse.portfolio.tracker.get_portfolio_status", return_value=mock_portfolio), \
         patch("stockpulse.config.settings.load_portfolio", return_value={"positions": []}), \
         patch("stockpulse.config.settings.load_strategies", return_value={"risk": {"max_positions": 8, "max_position_pct": 8}}), \
         patch("stockpulse.llm.summarizer._call_llm", return_value=None):
        r = client.post("/api/allocate", json={"amount": 2000})
        data = r.json()
        assert data["total_portfolio_after"] == 5000


def test_allocation_amount_zero_rejected():
    """Amount of 0 should return 400."""
    r = client.post("/api/allocate", json={"amount": 0})
    assert r.status_code == 400


def test_allocation_amount_negative_rejected():
    """Negative amount should return 400."""
    r = client.post("/api/allocate", json={"amount": -100})
    assert r.status_code == 400


def test_allocation_rationale_fallback_when_llm_off():
    """When LLM returns None, rationale should fall back to a non-empty default."""
    recs = [{"ticker": "MSFT", "action": "BUY", "composite_score": 65, "confidence": 60, "thesis": "cloud growth"}]
    with patch("stockpulse.api.server._get_latest_scan", return_value=recs), \
         patch("stockpulse.portfolio.tracker.get_portfolio_status", return_value=_base_portfolio()), \
         patch("stockpulse.config.settings.load_portfolio", return_value={"positions": []}), \
         patch("stockpulse.config.settings.load_strategies", return_value={"risk": {"max_positions": 8, "max_position_pct": 8}}), \
         patch("stockpulse.portfolio.risk.check_concentration_limits", return_value=_base_risk()), \
         patch("stockpulse.llm.summarizer._call_llm", return_value=None):
        r = client.post("/api/allocate", json={"amount": 5000})
        data = r.json()
        assert data["rationale"]  # non-empty fallback
