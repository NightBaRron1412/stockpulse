from unittest.mock import patch
from stockpulse.research.tracker import log_signal, _compute_stats


def test_log_signal_only_tracks_buy_watchlist():
    """Should only log BUY and WATCHLIST signals."""
    mock_quote = {"price": 150.0, "previous_close": 148.0}
    with patch("stockpulse.research.tracker.get_current_quote", return_value=mock_quote), \
         patch("stockpulse.research.tracker._load_tracker", return_value={"signals": [], "stats": {}}), \
         patch("stockpulse.research.tracker._save_tracker") as mock_save:

        # HOLD should not be logged
        log_signal({"ticker": "TEST", "action": "HOLD", "composite_score": 10})
        mock_save.assert_not_called()

        # BUY should be logged
        log_signal({"ticker": "TEST", "action": "BUY", "composite_score": 60, "confidence": 60, "thesis": "test"})
        mock_save.assert_called_once()


def test_compute_stats_empty():
    stats = _compute_stats([])
    assert stats["5d"]["count"] == 0
    assert stats["10d"]["count"] == 0
    assert stats["20d"]["count"] == 0


def test_compute_stats_with_data():
    signals = [
        {
            "ticker": "A", "action": "BUY", "signal_date": "2026-01-01",
            "entry_price": 100, "composite_score": 60, "confidence": 60, "thesis": "",
            "checkpoints": {
                "5d": {"checked": True, "return_pct": 5.0, "price": 105, "date": "2026-01-08"},
                "10d": {"checked": True, "return_pct": -2.0, "price": 98, "date": "2026-01-15"},
                "20d": {"checked": False, "return_pct": None, "price": None, "date": None},
            },
        },
        {
            "ticker": "B", "action": "BUY", "signal_date": "2026-01-01",
            "entry_price": 200, "composite_score": 55, "confidence": 55, "thesis": "",
            "checkpoints": {
                "5d": {"checked": True, "return_pct": 3.0, "price": 206, "date": "2026-01-08"},
                "10d": {"checked": True, "return_pct": 8.0, "price": 216, "date": "2026-01-15"},
                "20d": {"checked": False, "return_pct": None, "price": None, "date": None},
            },
        },
    ]
    stats = _compute_stats(signals)
    assert stats["5d"]["count"] == 2
    assert stats["5d"]["hit_rate"] == 100.0  # both positive
    assert stats["5d"]["avg_return"] == 4.0  # (5+3)/2
    assert stats["10d"]["count"] == 2
    assert stats["10d"]["hit_rate"] == 50.0  # one positive, one negative
