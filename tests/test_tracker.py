from unittest.mock import patch
from stockpulse.research.tracker import log_signal, _compute_stats, _run_validation_tests
import numpy as np


def test_log_signal_only_tracks_buy_watchlist():
    mock_quote = {"price": 150.0, "previous_close": 148.0}
    with patch("stockpulse.research.tracker.get_current_quote", return_value=mock_quote), \
         patch("stockpulse.research.tracker._load_tracker", return_value={"signals": [], "stats": {}, "validation": {}}), \
         patch("stockpulse.research.tracker._save_tracker") as mock_save:
        log_signal({"ticker": "TEST", "action": "HOLD", "composite_score": 10})
        mock_save.assert_not_called()
        log_signal({"ticker": "TEST", "action": "BUY", "composite_score": 60, "confidence": 60, "thesis": "test"})
        mock_save.assert_called_once()


def test_compute_stats_empty():
    stats = _compute_stats([])
    assert stats["5d"]["count"] == 0
    assert stats["10d"]["count"] == 0


def test_validation_insufficient_data():
    result = _run_validation_tests([])
    assert result["status"] == "insufficient_data"


def test_validation_runs_with_data():
    """Test that validation produces correct test structure with enough signals."""
    signals = []
    for i in range(15):
        signals.append({
            "ticker": f"T{i}", "action": "BUY", "signal_date": f"2026-01-{i+1:02d}",
            "entry_price": 100, "spy_entry_price": 450,
            "composite_score": 60, "confidence": 60, "thesis": "test",
            "checkpoints": {
                "5d": {"checked": True, "stock_price": 103, "stock_return_pct": 3.0,
                       "spy_price": 452, "spy_return_pct": 0.44, "excess_vs_spy": 2.56, "date": "2026-01-15"},
                "10d": {"checked": True, "stock_price": 105, "stock_return_pct": 5.0,
                        "spy_price": 454, "spy_return_pct": 0.89, "excess_vs_spy": 4.11, "date": "2026-01-20"},
                "20d": {"checked": False, "stock_price": None, "stock_return_pct": None,
                        "spy_price": None, "spy_return_pct": None, "excess_vs_spy": None, "date": None},
            },
        })

    result = _run_validation_tests(signals)
    assert result["status"] == "collecting"  # < 100 signals
    assert "paired_t" in result["tests"]
    assert "binomial_hit_rate" in result["tests"]
    assert "bootstrap" in result["tests"]
    assert result["tests"]["paired_t"]["mean_excess"] > 0
    assert result["tests"]["binomial_hit_rate"]["hit_rate"] == 100.0  # all positive
