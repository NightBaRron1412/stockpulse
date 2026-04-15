"""Tests for FastAPI API endpoints."""
import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from stockpulse.api.server import app

client = TestClient(app)


def test_dashboard_returns_200():
    with patch("stockpulse.api.server._get_latest_scan", return_value=[]), \
         patch("stockpulse.api.server._parse_activity_log", return_value=[]), \
         patch("stockpulse.api.server._get_scan_status", return_value={"running": False, "progress": "", "last_completed": "Never", "next_scheduled": "09:35 ET"}), \
         patch("stockpulse.portfolio.tracker.get_portfolio_status", return_value={"timestamp": "", "total_invested": 0, "total_current": 0, "total_pnl": 0, "total_pnl_pct": 0, "positions": []}):
        r = client.get("/api/dashboard")
        assert r.status_code == 200
        data = r.json()
        assert "portfolio" in data
        assert "top_signals" in data
        assert "activity" in data
        assert "scan_status" in data
        assert "signal_count" in data


def test_watchlist_returns_list():
    with patch("stockpulse.api.server._get_latest_scan", return_value=[]), \
         patch("stockpulse.config.settings.load_watchlists", return_value={"user": ["AAPL"], "discovered": [], "priority": []}):
        r = client.get("/api/watchlist")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["ticker"] == "AAPL"
        assert data[0]["source"] == "user"


def test_portfolio_returns_positions():
    mock_status = {"timestamp": "", "total_invested": 1000, "total_current": 1100, "total_pnl": 100, "total_pnl_pct": 10, "positions": []}
    with patch("stockpulse.portfolio.tracker.get_portfolio_status", return_value=mock_status), \
         patch("stockpulse.portfolio.risk.check_drawdown_status", return_value={"drawdown_pct": 0, "size_multiplier": 1.0, "new_buys_paused": False}):
        r = client.get("/api/portfolio")
        assert r.status_code == 200
        data = r.json()
        assert data["total_pnl"] == 100
        assert "drawdown" in data


def test_validation_returns_tracker_data():
    mock_tracker = {"signals": [], "stats": {}, "validation": {}}
    with patch("stockpulse.api.server._read_json", return_value=mock_tracker):
        r = client.get("/api/validation")
        assert r.status_code == 200
        data = r.json()
        assert "signals" in data


def test_reports_list():
    with patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.glob", return_value=[]):
        r = client.get("/api/reports")
        assert r.status_code == 200


def test_alerts_recent():
    with patch("pathlib.Path.exists", return_value=False):
        r = client.get("/api/alerts/recent")
        assert r.status_code == 200
        assert r.json() == []


def test_scan_status():
    with patch("stockpulse.api.server._get_scan_status", return_value={"running": False, "progress": "", "last_completed": "Never", "next_scheduled": "09:35 ET"}):
        r = client.get("/api/scan/status")
        assert r.status_code == 200
        data = r.json()
        assert "running" in data


def test_config_returns_data():
    mock_strat = {"signals": {"rsi": {"weight": 0.07}}, "thresholds": {"buy": 55}, "risk": {}, "scheduling": {}}
    mock_wl = {"user": ["AAPL"], "discovered": []}
    with patch("stockpulse.config.settings.load_strategies", return_value=mock_strat), \
         patch("stockpulse.config.settings.load_watchlists", return_value=mock_wl):
        r = client.get("/api/config")
        assert r.status_code == 200
        data = r.json()
        assert "weights" in data
        assert "watchlist" in data
        assert "thresholds" in data


def test_watchlist_add():
    with patch("stockpulse.config.settings.load_watchlists", return_value={"user": [], "discovered": [], "priority": []}), \
         patch("stockpulse.config.settings.save_watchlists"):
        r = client.post("/api/watchlist/add", json={"ticker": "TSLA"})
        assert r.status_code == 200
        assert r.json()["ticker"] == "TSLA"


def test_watchlist_remove():
    with patch("stockpulse.config.settings.load_watchlists", return_value={"user": ["TSLA"], "discovered": [], "priority": []}), \
         patch("stockpulse.config.settings.save_watchlists"):
        r = client.post("/api/watchlist/remove", json={"ticker": "TSLA"})
        assert r.status_code == 200


def test_allocate_requires_amount():
    r = client.post("/api/allocate", json={"amount": 0})
    assert r.status_code == 400


def test_allocate_returns_plan():
    mock_recs = [{"ticker": "JBL", "action": "WATCHLIST", "composite_score": 37.9, "confidence": 37, "thesis": "test"}]
    mock_portfolio = {"timestamp": "", "total_invested": 5000, "total_current": 5100, "total_pnl": 100, "total_pnl_pct": 2, "positions": []}
    mock_risk = {"allowed": True, "reasons": [], "size_multiplier": 1.0, "sector": "Tech", "industry": "Semis", "cluster_tickers": []}

    with patch("stockpulse.api.server._get_latest_scan", return_value=mock_recs), \
         patch("stockpulse.portfolio.tracker.get_portfolio_status", return_value=mock_portfolio), \
         patch("stockpulse.config.settings.load_portfolio", return_value={"positions": []}), \
         patch("stockpulse.config.settings.load_strategies", return_value={"risk": {"max_positions": 8, "max_position_pct": 8}}), \
         patch("stockpulse.portfolio.risk.check_concentration_limits", return_value=mock_risk), \
         patch("stockpulse.llm.summarizer._call_llm", return_value="Test rationale"):
        r = client.post("/api/allocate", json={"amount": 5000})
        assert r.status_code == 200
        data = r.json()
        assert "allocations" in data
        assert "rationale" in data
        assert data["amount"] == 5000


def test_allocate_with_tickers():
    mock_portfolio = {"timestamp": "", "total_invested": 5000, "total_current": 5100, "total_pnl": 100, "total_pnl_pct": 2, "positions": []}
    mock_risk = {"allowed": True, "reasons": [], "size_multiplier": 1.0, "sector": "Tech", "industry": "Semis", "cluster_tickers": []}
    mock_rec = {"ticker": "AAPL", "action": "HOLD", "composite_score": 10, "confidence": 10, "thesis": "test"}

    with patch("stockpulse.api.server._get_latest_scan", return_value=[mock_rec]), \
         patch("stockpulse.portfolio.tracker.get_portfolio_status", return_value=mock_portfolio), \
         patch("stockpulse.config.settings.load_portfolio", return_value={"positions": []}), \
         patch("stockpulse.config.settings.load_strategies", return_value={"risk": {"max_positions": 8, "max_position_pct": 8}}), \
         patch("stockpulse.portfolio.risk.check_concentration_limits", return_value=mock_risk), \
         patch("stockpulse.llm.summarizer._call_llm", return_value=None):
        r = client.post("/api/allocate", json={"amount": 5000, "tickers": ["AAPL"]})
        assert r.status_code == 200


def test_backtest_status():
    r = client.get("/api/backtest/status")
    assert r.status_code == 200
    data = r.json()
    assert "running" in data


def test_activity():
    with patch("stockpulse.api.server._parse_activity_log", return_value=[]):
        r = client.get("/api/activity")
        assert r.status_code == 200


def test_dashboard_signal_counts():
    """Dashboard should count signal actions correctly."""
    recs = [
        {"ticker": "A", "action": "BUY", "composite_score": 60},
        {"ticker": "B", "action": "BUY", "composite_score": 55},
        {"ticker": "C", "action": "HOLD", "composite_score": 10},
    ]
    mock_portfolio = {"timestamp": "", "total_invested": 0, "total_current": 0, "total_pnl": 0, "total_pnl_pct": 0, "positions": []}
    with patch("stockpulse.api.server._get_latest_scan", return_value=recs), \
         patch("stockpulse.api.server._parse_activity_log", return_value=[]), \
         patch("stockpulse.api.server._get_scan_status", return_value={"running": False, "progress": "", "last_completed": "Never", "next_scheduled": "09:35 ET"}), \
         patch("stockpulse.portfolio.tracker.get_portfolio_status", return_value=mock_portfolio):
        r = client.get("/api/dashboard")
        assert r.status_code == 200
        data = r.json()
        assert data["signal_count"].get("BUY") == 2
        assert data["signal_count"].get("HOLD") == 1
        assert data["total_scanned"] == 3


def test_watchlist_add_duplicate_not_duplicated():
    """Adding an already-present ticker should not create duplicates."""
    saved = {}

    def capture_save(data):
        saved.update(data)

    with patch("stockpulse.config.settings.load_watchlists", return_value={"user": ["AAPL"], "discovered": [], "priority": []}), \
         patch("stockpulse.config.settings.save_watchlists", side_effect=capture_save):
        r = client.post("/api/watchlist/add", json={"ticker": "AAPL"})
        assert r.status_code == 200
        # save_watchlists should NOT have been called (ticker already in list)
        assert saved == {}


def test_watchlist_remove_unknown_ticker():
    """Removing a ticker not in any list should still return 200."""
    with patch("stockpulse.config.settings.load_watchlists", return_value={"user": [], "discovered": [], "priority": []}), \
         patch("stockpulse.config.settings.save_watchlists"):
        r = client.post("/api/watchlist/remove", json={"ticker": "UNKNOWN"})
        assert r.status_code == 200


def test_allocate_no_buy_signals():
    """When all recs are HOLD, allocations list should be empty."""
    mock_recs = [{"ticker": "AAPL", "action": "HOLD", "composite_score": 5, "confidence": 5, "thesis": "flat"}]
    mock_portfolio = {"timestamp": "", "total_invested": 0, "total_current": 0, "total_pnl": 0, "total_pnl_pct": 0, "positions": []}
    with patch("stockpulse.api.server._get_latest_scan", return_value=mock_recs), \
         patch("stockpulse.portfolio.tracker.get_portfolio_status", return_value=mock_portfolio), \
         patch("stockpulse.config.settings.load_portfolio", return_value={"positions": []}), \
         patch("stockpulse.config.settings.load_strategies", return_value={"risk": {"max_positions": 8, "max_position_pct": 8}}), \
         patch("stockpulse.llm.summarizer._call_llm", return_value=None):
        r = client.post("/api/allocate", json={"amount": 5000})
        assert r.status_code == 200
        data = r.json()
        assert len(data["allocations"]) == 0
        assert data["cash_reserve"] == 5000.0
