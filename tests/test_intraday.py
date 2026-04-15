"""Tests for intraday change detection."""
from unittest.mock import patch
from stockpulse.reports.intraday import detect_changes


def _mock_load(data=None):
    return data or {}


def _mock_save(data):
    pass


@patch("stockpulse.reports.intraday._save_previous_actions", side_effect=_mock_save)
@patch("stockpulse.reports.intraday._load_previous_actions", return_value={"AAPL": "HOLD"})
def test_detect_changes_finds_action_change(mock_load, mock_save):
    recs = [{"ticker": "AAPL", "action": "WATCHLIST", "confidence": 35, "thesis": "test"}]
    changes = detect_changes(recs)

    assert len(changes) == 1
    assert changes[0]["ticker"] == "AAPL"
    assert changes[0]["previous_action"] == "HOLD"
    assert changes[0]["new_action"] == "WATCHLIST"


@patch("stockpulse.reports.intraday._save_previous_actions", side_effect=_mock_save)
@patch("stockpulse.reports.intraday._load_previous_actions", return_value={"AAPL": "HOLD"})
def test_detect_changes_no_change(mock_load, mock_save):
    recs = [{"ticker": "AAPL", "action": "HOLD", "confidence": 10, "thesis": "test"}]
    changes = detect_changes(recs)
    assert len(changes) == 0


@patch("stockpulse.reports.intraday._save_previous_actions", side_effect=_mock_save)
@patch("stockpulse.reports.intraday._load_previous_actions", return_value={})
def test_detect_changes_first_scan(mock_load, mock_save):
    recs = [{"ticker": "NVDA", "action": "WATCHLIST", "confidence": 30, "thesis": "test"}]
    changes = detect_changes(recs)
    assert len(changes) == 0


@patch("stockpulse.reports.intraday._save_previous_actions", side_effect=_mock_save)
@patch("stockpulse.reports.intraday._load_previous_actions",
       return_value={"AAPL": "HOLD", "MSFT": "WATCHLIST", "GOOG": "BUY"})
def test_detect_changes_multiple_tickers_mixed(mock_load, mock_save):
    recs = [
        {"ticker": "AAPL", "action": "BUY", "confidence": 60, "thesis": "breakout"},
        {"ticker": "MSFT", "action": "WATCHLIST", "confidence": 35, "thesis": "sideways"},
        {"ticker": "GOOG", "action": "HOLD", "confidence": 10, "thesis": "fading"},
    ]
    changes = detect_changes(recs)
    changed_tickers = {c["ticker"] for c in changes}
    assert "AAPL" in changed_tickers
    assert "GOOG" in changed_tickers
    assert "MSFT" not in changed_tickers


@patch("stockpulse.reports.intraday._save_previous_actions", side_effect=_mock_save)
@patch("stockpulse.reports.intraday._load_previous_actions", return_value={})
def test_detect_changes_empty_input(mock_load, mock_save):
    changes = detect_changes([])
    assert changes == []


@patch("stockpulse.reports.intraday._save_previous_actions")
@patch("stockpulse.reports.intraday._load_previous_actions", return_value={})
def test_detect_changes_saves_state(mock_load, mock_save):
    recs = [
        {"ticker": "A", "action": "BUY", "confidence": 65, "thesis": "up"},
        {"ticker": "B", "action": "HOLD", "confidence": 10, "thesis": "flat"},
    ]
    detect_changes(recs)
    # Verify save was called with the updated actions
    saved = mock_save.call_args[0][0]
    assert saved["A"] == "BUY"
    assert saved["B"] == "HOLD"


@patch("stockpulse.reports.intraday._save_previous_actions", side_effect=_mock_save)
@patch("stockpulse.reports.intraday._load_previous_actions", return_value={"AMD": "HOLD"})
def test_detect_changes_change_includes_required_fields(mock_load, mock_save):
    recs = [{"ticker": "AMD", "action": "WATCHLIST", "confidence": 38, "thesis": "recovering"}]
    changes = detect_changes(recs)
    assert len(changes) == 1
    for key in ("ticker", "previous_action", "new_action", "confidence", "thesis", "type"):
        assert key in changes[0]
    assert changes[0]["type"] == "action_change"
