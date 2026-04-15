"""Tests for intraday change detection."""
import pytest
from stockpulse.reports.intraday import detect_changes, _previous_actions


def test_detect_changes_finds_action_change():
    _previous_actions.clear()
    _previous_actions["AAPL"] = "HOLD"

    recs = [{"ticker": "AAPL", "action": "WATCHLIST", "confidence": 35, "thesis": "test"}]
    changes = detect_changes(recs)

    assert len(changes) == 1
    assert changes[0]["ticker"] == "AAPL"
    assert changes[0]["previous_action"] == "HOLD"
    assert changes[0]["new_action"] == "WATCHLIST"


def test_detect_changes_no_change():
    _previous_actions.clear()
    _previous_actions["AAPL"] = "HOLD"

    recs = [{"ticker": "AAPL", "action": "HOLD", "confidence": 10, "thesis": "test"}]
    changes = detect_changes(recs)

    assert len(changes) == 0


def test_detect_changes_first_scan():
    _previous_actions.clear()

    recs = [{"ticker": "NVDA", "action": "WATCHLIST", "confidence": 30, "thesis": "test"}]
    changes = detect_changes(recs)

    # First scan — no previous action, so no change detected
    assert len(changes) == 0
    # But it should record the action for next time
    assert _previous_actions["NVDA"] == "WATCHLIST"


def test_detect_changes_multiple_tickers_mixed():
    """Only tickers whose action actually changed should appear."""
    _previous_actions.clear()
    _previous_actions["AAPL"] = "HOLD"
    _previous_actions["MSFT"] = "WATCHLIST"
    _previous_actions["GOOG"] = "BUY"

    recs = [
        {"ticker": "AAPL", "action": "BUY", "confidence": 60, "thesis": "breakout"},
        {"ticker": "MSFT", "action": "WATCHLIST", "confidence": 35, "thesis": "sideways"},
        {"ticker": "GOOG", "action": "HOLD", "confidence": 10, "thesis": "fading"},
    ]
    changes = detect_changes(recs)

    changed_tickers = {c["ticker"] for c in changes}
    assert "AAPL" in changed_tickers   # HOLD -> BUY
    assert "GOOG" in changed_tickers   # BUY -> HOLD
    assert "MSFT" not in changed_tickers  # unchanged


def test_detect_changes_updates_previous_state():
    """After detect_changes, _previous_actions should reflect the latest actions."""
    _previous_actions.clear()
    _previous_actions["TSLA"] = "HOLD"

    recs = [{"ticker": "TSLA", "action": "SELL", "confidence": 5, "thesis": "breakdown"}]
    detect_changes(recs)

    assert _previous_actions["TSLA"] == "SELL"


def test_detect_changes_records_new_tickers_for_next_call():
    """A ticker seen for the first time should be stored but not flagged as changed."""
    _previous_actions.clear()

    recs = [{"ticker": "NEW", "action": "BUY", "confidence": 70, "thesis": "momentum"}]
    changes = detect_changes(recs)

    assert len(changes) == 0
    assert _previous_actions["NEW"] == "BUY"

    # Second call — now action changes from BUY to HOLD
    recs2 = [{"ticker": "NEW", "action": "HOLD", "confidence": 15, "thesis": "fading"}]
    changes2 = detect_changes(recs2)

    assert len(changes2) == 1
    assert changes2[0]["previous_action"] == "BUY"
    assert changes2[0]["new_action"] == "HOLD"


def test_detect_changes_change_includes_required_fields():
    """Each detected change dict must have all expected keys."""
    _previous_actions.clear()
    _previous_actions["AMD"] = "HOLD"

    recs = [{"ticker": "AMD", "action": "WATCHLIST", "confidence": 38, "thesis": "recovering"}]
    changes = detect_changes(recs)

    assert len(changes) == 1
    change = changes[0]
    for key in ("ticker", "previous_action", "new_action", "confidence", "thesis", "type"):
        assert key in change, f"Missing key: {key}"
    assert change["type"] == "action_change"


def test_detect_changes_empty_input():
    """Empty recs list should produce empty changes and not crash."""
    _previous_actions.clear()
    changes = detect_changes([])
    assert changes == []


def test_detect_changes_preserves_all_ticker_states():
    """All tickers in the input should be tracked even if no change occurred."""
    _previous_actions.clear()

    recs = [
        {"ticker": "A", "action": "BUY", "confidence": 65, "thesis": "up"},
        {"ticker": "B", "action": "HOLD", "confidence": 10, "thesis": "flat"},
        {"ticker": "C", "action": "SELL", "confidence": 5, "thesis": "down"},
    ]
    detect_changes(recs)

    assert _previous_actions["A"] == "BUY"
    assert _previous_actions["B"] == "HOLD"
    assert _previous_actions["C"] == "SELL"
