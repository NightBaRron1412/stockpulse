"""Tests for stockpulse.signals.market_regime."""
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock

from stockpulse.signals.market_regime import (
    detect_regime,
    get_regime_adjustments,
    _default_regime,
    _get_vix,
)


def _make_spy_df(n=260, base=450.0, trend=0.1):
    """Build a synthetic SPY DataFrame with enough rows for SMA200."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    close = base + np.cumsum(np.random.randn(n) * 2 + trend)
    close = np.maximum(close, 1.0)
    return pd.DataFrame(
        {
            "Open": close * 0.99,
            "High": close * 1.02,
            "Low": close * 0.98,
            "Close": close,
            "Volume": np.random.randint(50_000_000, 200_000_000, n),
        },
        index=dates,
    )


def _cfg(**overrides):
    """Base market_regime config dict with sensible defaults."""
    c = {
        "enabled": True,
        "vix_high": 25,
        "vix_extreme": 35,
        "correction_threshold_pct": 5,
    }
    c.update(overrides)
    return c


# ---------- detect_regime: trending ----------

@patch("stockpulse.signals.market_regime._get_vix", return_value=14.0)
@patch("stockpulse.signals.market_regime.get_price_history")
@patch("stockpulse.signals.market_regime.load_strategies")
def test_detect_regime_trending(mock_strats, mock_hist, mock_vix):
    """SPY > EMA20 > SMA50 and ADX > 25 => trending."""
    # Build an uptrend DF: strong positive trend so price stays above all MAs
    np.random.seed(7)
    n = 260
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    close = 400 + np.arange(n) * 0.5 + np.random.randn(n) * 0.5
    close = np.maximum(close, 1.0)
    df = pd.DataFrame(
        {
            "Open": close * 0.999,
            "High": close * 1.005,
            "Low": close * 0.995,
            "Close": close,
            "Volume": np.full(n, 100_000_000),
        },
        index=dates,
    )

    mock_strats.return_value = {"market_regime": _cfg()}
    mock_hist.return_value = df

    with patch("stockpulse.signals.market_regime._compute_breadth", return_value=70.0):
        result = detect_regime()
    assert result["regime"] == "trending"
    assert result["confidence"] > 50


# ---------- detect_regime: correcting ----------

@patch("stockpulse.signals.market_regime._get_vix", return_value=14.0)
@patch("stockpulse.signals.market_regime.get_price_history")
@patch("stockpulse.signals.market_regime.load_strategies")
def test_detect_regime_correcting(mock_strats, mock_hist, mock_vix):
    """SPY < SMA50 => correcting."""
    np.random.seed(99)
    n = 260
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    # Downtrend in the last portion so price drops below SMA50
    close = np.concatenate([
        400 + np.arange(200) * 0.3,
        460 - np.arange(60) * 1.5,
    ]) + np.random.randn(n) * 0.3
    close = np.maximum(close, 1.0)
    df = pd.DataFrame(
        {
            "Open": close * 0.999,
            "High": close * 1.005,
            "Low": close * 0.995,
            "Close": close,
            "Volume": np.full(n, 100_000_000),
        },
        index=dates,
    )

    mock_strats.return_value = {"market_regime": _cfg()}
    mock_hist.return_value = df

    result = detect_regime()
    # Price is below SMA50 at end => correcting or selling_off
    assert result["regime"] in ("correcting", "selling_off")


# ---------- detect_regime: selling_off ----------

@patch("stockpulse.signals.market_regime._get_vix", return_value=40.0)
@patch("stockpulse.signals.market_regime.get_price_history")
@patch("stockpulse.signals.market_regime.load_strategies")
def test_detect_regime_selling_off_vix(mock_strats, mock_hist, mock_vix):
    """VIX > 35 => selling_off regardless of price position."""
    df = _make_spy_df()
    mock_strats.return_value = {"market_regime": _cfg()}
    mock_hist.return_value = df

    result = detect_regime()
    assert result["regime"] == "selling_off"
    assert result["vix_level"] == 40.0
    assert result["confidence"] == 90


# ---------- detect_regime: ranging (default) ----------

@patch("stockpulse.signals.market_regime._get_vix", return_value=14.0)
@patch("stockpulse.signals.market_regime.get_price_history")
@patch("stockpulse.signals.market_regime.load_strategies")
def test_detect_regime_ranging_default(mock_strats, mock_hist, mock_vix):
    """Flat, low-ADX market => ranging."""
    np.random.seed(0)
    n = 260
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    # Flat close values with small noise => ADX will be low
    close = 450.0 + np.random.randn(n) * 0.5
    close = np.maximum(close, 1.0)
    df = pd.DataFrame(
        {
            "Open": close * 0.999,
            "High": close * 1.001,
            "Low": close * 0.999,
            "Close": close,
            "Volume": np.full(n, 100_000_000),
        },
        index=dates,
    )

    mock_strats.return_value = {"market_regime": _cfg()}
    mock_hist.return_value = df

    result = detect_regime()
    assert result["regime"] == "ranging"
    assert result["confidence"] in (55, 60, 65)  # varies by breadth availability


# ---------- get_regime_adjustments ----------

@patch("stockpulse.signals.market_regime.load_strategies")
def test_get_regime_adjustments_defaults(mock_strats):
    """Returns correct multipliers when config has no overrides."""
    mock_strats.return_value = {"market_regime": {}}

    adj_trend = get_regime_adjustments("trending")
    assert adj_trend["cash_reserve_mult"] == 1.0
    assert adj_trend["starter_enabled"] is True

    adj_sell = get_regime_adjustments("selling_off")
    assert adj_sell["cash_reserve_mult"] == 2.0
    assert adj_sell["starter_enabled"] is False

    adj_correct = get_regime_adjustments("correcting")
    assert adj_correct["cash_reserve_mult"] == 1.5
    assert adj_correct["buy_threshold_add"] == 10

    adj_range = get_regime_adjustments("ranging")
    assert adj_range["cash_reserve_mult"] == 1.2
    assert adj_range["buy_threshold_add"] == 5


def test_get_regime_adjustments_with_custom_config():
    """Config overrides take precedence over defaults."""
    custom_cfg = {
        "regime_adjustments": {
            "trending": {"cash_reserve_mult": 0.8, "buy_threshold_add": -5, "starter_enabled": True},
        }
    }
    adj = get_regime_adjustments("trending", config=custom_cfg)
    assert adj["cash_reserve_mult"] == 0.8
    assert adj["buy_threshold_add"] == -5


# ---------- _default_regime ----------

@patch("stockpulse.signals.market_regime.load_strategies", return_value={"market_regime": {}})
def test_default_regime(mock_strats):
    """Fallback returns ranging with 0 confidence."""
    result = _default_regime()
    assert result["regime"] == "ranging"
    assert result["confidence"] == 0
    assert result["spy_price"] == 0
    assert result["vix_level"] == 15


# ---------- _get_vix: fallback on failure ----------

def test_get_vix_fallback_on_failure():
    """VIX download failure falls back to 15.0."""
    mock_yf = MagicMock()
    mock_yf.download.side_effect = Exception("network error")

    with patch.dict("sys.modules", {"yfinance": mock_yf}):
        # Force re-import inside the function
        result = _get_vix()
    assert result == 15.0


def test_get_vix_returns_close_value():
    """VIX download success returns the Close value."""
    vix_df = pd.DataFrame({"Close": [18.5, 19.2, 20.1]})
    mock_yf = MagicMock()
    mock_yf.download.return_value = vix_df

    with patch.dict("sys.modules", {"yfinance": mock_yf}):
        result = _get_vix()
    assert result == 20.1
