"""Tests for stockpulse.research.patterns."""
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from stockpulse.research.patterns import (
    record_pattern,
    find_similar_patterns,
    update_outcomes,
    _cosine_similarity,
    _magnitude,
)


def _make_rec(ticker="AAPL", action="BUY", score=75.0, rsi=60, macd=50, ma=40, volume=30, breakout=20, rs=10):
    """Build a minimal signal record for record_pattern."""
    return {
        "ticker": ticker,
        "action": action,
        "composite_score": score,
        "signals": {
            "rsi": {"score": rsi},
            "macd": {"score": macd},
            "moving_averages": {"score": ma},
            "volume": {"score": volume},
            "breakout": {"score": breakout},
            "relative_strength": {"score": rs},
        },
    }


def _make_history_entry(
    ticker="AAPL",
    date=None,
    rsi=60, macd=50, ma=40, volume=30, breakout=20, rs=10,
    outcome_5d=2.5, outcome_10d=4.0, outcome_20d=6.0,
    entry_price=150.0,
):
    """Build a single history entry dict."""
    return {
        "ticker": ticker,
        "date": date or datetime.now().strftime("%Y-%m-%d"),
        "action": "BUY",
        "score": 75.0,
        "rsi": rsi, "macd": macd, "ma": ma,
        "volume": volume, "breakout": breakout, "rs": rs,
        "outcome_5d": outcome_5d,
        "outcome_10d": outcome_10d,
        "outcome_20d": outcome_20d,
        "entry_price": entry_price,
    }


# ---------- record_pattern ----------

@patch("stockpulse.data.provider.get_current_quote", return_value={"price": 150.0})
@patch("stockpulse.research.patterns._save_history")
@patch("stockpulse.research.patterns._load_history", return_value=[])
def test_record_pattern_saves_entry(mock_load, mock_save, mock_quote):
    """record_pattern writes a new entry to history."""
    rec = _make_rec()
    record_pattern(rec)

    mock_save.assert_called_once()
    saved = mock_save.call_args[0][0]
    assert len(saved) == 1
    assert saved[0]["ticker"] == "AAPL"
    assert saved[0]["entry_price"] == 150.0
    assert saved[0]["rsi"] == 60


@patch("stockpulse.data.provider.get_current_quote", return_value={"price": 155.0})
@patch("stockpulse.research.patterns._save_history")
@patch("stockpulse.research.patterns._load_history")
def test_record_pattern_no_duplicate(mock_load, mock_save, mock_quote):
    """Same ticker/date should replace, not duplicate."""
    today = datetime.now().strftime("%Y-%m-%d")
    existing = [_make_history_entry(ticker="AAPL", date=today)]
    mock_load.return_value = existing

    rec = _make_rec(ticker="AAPL")
    record_pattern(rec)

    saved = mock_save.call_args[0][0]
    aapl_entries = [e for e in saved if e["ticker"] == "AAPL" and e["date"] == today]
    assert len(aapl_entries) == 1


# ---------- find_similar_patterns ----------

@patch("stockpulse.research.patterns._load_history", return_value=[])
def test_find_similar_insufficient_history(mock_load):
    """Returns None with < 10 history entries."""
    signals = _make_rec()["signals"]
    result = find_similar_patterns("AAPL", signals)
    assert result is None


@patch("stockpulse.research.patterns._load_history")
def test_find_similar_high_similarity_match(mock_load):
    """Finds matches with high cosine similarity and returns stats."""
    # Build 15 similar history entries (same signal profile)
    history = []
    for i in range(15):
        entry = _make_history_entry(
            ticker=f"TICK{i}",
            date=(datetime.now() - timedelta(days=30 + i)).strftime("%Y-%m-%d"),
            rsi=60, macd=50, ma=40, volume=30, breakout=20, rs=10,
            outcome_5d=2.0 + i * 0.1,
            outcome_10d=3.0 + i * 0.2,
            outcome_20d=5.0 + i * 0.3,
        )
        history.append(entry)
    mock_load.return_value = history

    # Query with identical signal profile => high similarity
    signals = _make_rec()["signals"]
    result = find_similar_patterns("NEW", signals, min_matches=3)

    assert result is not None
    assert result["match_count"] >= 3
    assert "avg_return_5d" in result
    assert "avg_return_10d" in result
    assert "avg_return_20d" in result


@patch("stockpulse.research.patterns._load_history")
def test_find_similar_win_rate(mock_load):
    """Win rate reflects fraction of positive 10d outcomes."""
    history = []
    for i in range(12):
        # 8 winners (positive), 4 losers (negative)
        outcome = 5.0 if i < 8 else -3.0
        entry = _make_history_entry(
            ticker=f"T{i}",
            date=(datetime.now() - timedelta(days=30 + i)).strftime("%Y-%m-%d"),
            outcome_5d=outcome,
            outcome_10d=outcome,
            outcome_20d=outcome,
        )
        history.append(entry)
    mock_load.return_value = history

    signals = _make_rec()["signals"]
    result = find_similar_patterns("X", signals, min_matches=3)

    assert result is not None
    # 8 out of 12 positive => ~66.7% win rate
    assert 60 <= result["win_rate"] <= 70


# ---------- _cosine_similarity ----------

def test_cosine_identical_vectors():
    """Identical vectors => similarity = 1.0."""
    v = [1.0, 2.0, 3.0, 4.0]
    assert abs(_cosine_similarity(v, v) - 1.0) < 1e-9


def test_cosine_orthogonal_vectors():
    """Orthogonal vectors => similarity = 0.0."""
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert abs(_cosine_similarity(a, b)) < 1e-9


def test_cosine_opposite_vectors():
    """Opposite vectors => similarity = -1.0."""
    a = [1.0, 2.0, 3.0]
    b = [-1.0, -2.0, -3.0]
    assert abs(_cosine_similarity(a, b) - (-1.0)) < 1e-9


def test_cosine_zero_vector():
    """Zero vector => similarity = 0.0 (no division error)."""
    a = [0.0, 0.0, 0.0]
    b = [1.0, 2.0, 3.0]
    assert _cosine_similarity(a, b) == 0.0


# ---------- update_outcomes ----------

@patch("stockpulse.research.patterns._save_history")
@patch("stockpulse.research.patterns._load_history")
def test_update_outcomes_fills_5d(mock_load, mock_save):
    """5d outcome filled when entry is >= 5 days old."""
    old_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    entry = _make_history_entry(
        ticker="MSFT", date=old_date, entry_price=100.0,
        outcome_5d=None, outcome_10d=None, outcome_20d=None,
    )
    mock_load.return_value = [entry]

    update_outcomes("MSFT", current_price=105.0)

    mock_save.assert_called_once()
    updated = mock_save.call_args[0][0]
    assert updated[0]["outcome_5d"] == 5.0  # (105-100)/100 * 100
    assert updated[0]["outcome_10d"] is None  # only 7 days old


@patch("stockpulse.research.patterns._save_history")
@patch("stockpulse.research.patterns._load_history")
def test_update_outcomes_fills_10d(mock_load, mock_save):
    """10d outcome filled when entry is >= 10 days old."""
    old_date = (datetime.now() - timedelta(days=12)).strftime("%Y-%m-%d")
    entry = _make_history_entry(
        ticker="GOOG", date=old_date, entry_price=200.0,
        outcome_5d=None, outcome_10d=None, outcome_20d=None,
    )
    mock_load.return_value = [entry]

    update_outcomes("GOOG", current_price=210.0)

    updated = mock_save.call_args[0][0]
    assert updated[0]["outcome_5d"] == 5.0
    assert updated[0]["outcome_10d"] == 5.0
    assert updated[0]["outcome_20d"] is None


@patch("stockpulse.research.patterns._save_history")
@patch("stockpulse.research.patterns._load_history")
def test_update_outcomes_fills_20d(mock_load, mock_save):
    """20d outcome filled when entry is >= 20 days old."""
    old_date = (datetime.now() - timedelta(days=25)).strftime("%Y-%m-%d")
    entry = _make_history_entry(
        ticker="AMZN", date=old_date, entry_price=180.0,
        outcome_5d=None, outcome_10d=None, outcome_20d=None,
    )
    mock_load.return_value = [entry]

    update_outcomes("AMZN", current_price=189.0)

    updated = mock_save.call_args[0][0]
    assert updated[0]["outcome_5d"] == 5.0
    assert updated[0]["outcome_10d"] == 5.0
    assert updated[0]["outcome_20d"] == 5.0


@patch("stockpulse.research.patterns._save_history")
@patch("stockpulse.research.patterns._load_history")
def test_update_outcomes_skips_no_entry_price(mock_load, mock_save):
    """Entries without entry_price are skipped."""
    entry = _make_history_entry(ticker="NVDA", entry_price=None, outcome_5d=None, outcome_10d=None, outcome_20d=None)
    mock_load.return_value = [entry]

    update_outcomes("NVDA", current_price=500.0)

    mock_save.assert_not_called()
