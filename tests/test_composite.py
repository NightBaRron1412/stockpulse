"""Tests for stockpulse.signals.composite module."""
from unittest.mock import patch

from stockpulse.signals.composite import (
    compute_composite_score,
    classify_action,
    compute_confidence,
)


# ---------------------------------------------------------------------------
# compute_composite_score
# ---------------------------------------------------------------------------

def test_composite_score_weighted_average():
    """Standard weighted average: (80*0.5 + 60*0.3) / (0.5+0.3) = 72.5."""
    signals = {
        "rsi": {"score": 80.0, "weight": 0.5},
        "macd": {"score": 60.0, "weight": 0.3},
    }
    result = compute_composite_score(signals)
    assert abs(result - 72.5) < 1e-6


def test_composite_score_single_signal():
    signals = {"rsi": {"score": 42.0, "weight": 1.0}}
    assert abs(compute_composite_score(signals) - 42.0) < 1e-6


def test_composite_score_all_zero_signals():
    """Zero scores with nonzero weights should yield 0."""
    signals = {
        "a": {"score": 0.0, "weight": 1.0},
        "b": {"score": 0.0, "weight": 2.0},
    }
    assert compute_composite_score(signals) == 0.0


def test_composite_score_all_zero_weights():
    """Zero total weight returns 0 (avoid division by zero)."""
    signals = {
        "a": {"score": 50.0, "weight": 0.0},
        "b": {"score": -30.0, "weight": 0.0},
    }
    assert compute_composite_score(signals) == 0.0


def test_composite_score_empty_signals():
    assert compute_composite_score({}) == 0.0


def test_composite_score_mixed_positive_negative():
    """Positive and negative scores should partially cancel."""
    signals = {
        "up": {"score": 80.0, "weight": 1.0},
        "down": {"score": -60.0, "weight": 1.0},
    }
    # (80 - 60) / 2 = 10
    assert abs(compute_composite_score(signals) - 10.0) < 1e-6


def test_composite_score_clamps_high():
    """Result is clamped to 100 even if weighted average exceeds it."""
    signals = {"x": {"score": 200.0, "weight": 1.0}}
    assert compute_composite_score(signals) == 100.0


def test_composite_score_clamps_low():
    """Result is clamped to -100 even if weighted average goes below."""
    signals = {"x": {"score": -200.0, "weight": 1.0}}
    assert compute_composite_score(signals) == -100.0


def test_composite_score_missing_keys_default_zero():
    """Signals missing 'score' or 'weight' default to 0."""
    signals = {"a": {}}
    assert compute_composite_score(signals) == 0.0


# ---------------------------------------------------------------------------
# classify_action
# ---------------------------------------------------------------------------

_MOCK_STRATEGIES = {
    "thresholds": {"buy": 55, "watchlist": 32, "caution": -30, "sell": -65}
}


@patch("stockpulse.signals.composite.load_strategies", return_value=_MOCK_STRATEGIES)
def test_classify_buy(mock_strat):
    assert classify_action(55) == "BUY"
    assert classify_action(100) == "BUY"


@patch("stockpulse.signals.composite.load_strategies", return_value=_MOCK_STRATEGIES)
def test_classify_watchlist(mock_strat):
    assert classify_action(32) == "WATCHLIST"
    assert classify_action(54) == "WATCHLIST"


@patch("stockpulse.signals.composite.load_strategies", return_value=_MOCK_STRATEGIES)
def test_classify_sell(mock_strat):
    assert classify_action(-65) == "SELL"
    assert classify_action(-100) == "SELL"


@patch("stockpulse.signals.composite.load_strategies", return_value=_MOCK_STRATEGIES)
def test_classify_caution(mock_strat):
    assert classify_action(-30) == "CAUTION"
    assert classify_action(-64) == "CAUTION"


@patch("stockpulse.signals.composite.load_strategies", return_value=_MOCK_STRATEGIES)
def test_classify_hold(mock_strat):
    assert classify_action(0) == "HOLD"
    assert classify_action(31) == "HOLD"
    assert classify_action(-29) == "HOLD"


@patch("stockpulse.signals.composite.load_strategies", return_value=_MOCK_STRATEGIES)
def test_classify_boundary_between_hold_and_watchlist(mock_strat):
    """Score of 31.9 is HOLD, 32 is WATCHLIST."""
    assert classify_action(31.9) == "HOLD"
    assert classify_action(32.0) == "WATCHLIST"


@patch("stockpulse.signals.composite.load_strategies", return_value=_MOCK_STRATEGIES)
def test_classify_boundary_between_caution_and_hold(mock_strat):
    assert classify_action(-29.9) == "HOLD"
    assert classify_action(-30.0) == "CAUTION"


@patch("stockpulse.signals.composite.load_strategies", return_value={})
def test_classify_uses_defaults_when_no_thresholds(mock_strat):
    """When strategies YAML has no 'thresholds' key, defaults apply."""
    assert classify_action(55) == "BUY"
    assert classify_action(-65) == "SELL"
    assert classify_action(0) == "HOLD"


# ---------------------------------------------------------------------------
# compute_confidence
# ---------------------------------------------------------------------------

def test_confidence_positive_score():
    assert compute_confidence(72.5) == 72


def test_confidence_negative_score():
    """Confidence uses abs(), so negative scores map to positive %."""
    assert compute_confidence(-80.0) == 80


def test_confidence_zero():
    assert compute_confidence(0.0) == 0


def test_confidence_clamped_at_100():
    assert compute_confidence(150.0) == 100
    assert compute_confidence(-150.0) == 100


def test_confidence_fractional_truncated():
    """int() truncates toward zero, so 99.9 -> 99."""
    assert compute_confidence(99.9) == 99
