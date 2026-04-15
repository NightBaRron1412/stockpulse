"""Tests for stockpulse.research.scoring module."""
import numpy as np
import pandas as pd

from stockpulse.research.scoring import compute_invalidation


def _make_price_df(n=100, base=100.0, trend=0.1):
    """Build a synthetic OHLCV DataFrame with enough bars for indicators."""
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    close = base + np.cumsum(np.random.randn(n) * 2 + trend)
    close = np.maximum(close, 1.0)
    return pd.DataFrame(
        {
            "Open": close * 0.99,
            "High": close * 1.02,
            "Low": close * 0.98,
            "Close": close,
            "Volume": np.random.randint(1_000_000, 10_000_000, n),
        },
        index=dates,
    )


# ---------------------------------------------------------------------------
# BUY action
# ---------------------------------------------------------------------------

def test_buy_includes_atr_stop():
    df = _make_price_df(n=100)
    result = compute_invalidation("TEST", "BUY", df)
    assert "Stop:" in result
    assert "ATR" in result


def test_buy_includes_ema20():
    df = _make_price_df(n=100)
    result = compute_invalidation("TEST", "BUY", df)
    assert "20 EMA" in result


def test_buy_includes_sma50():
    df = _make_price_df(n=100)
    result = compute_invalidation("TEST", "BUY", df)
    assert "50 SMA" in result


def test_watchlist_same_as_buy():
    """WATCHLIST follows the same branch as BUY."""
    df = _make_price_df(n=100)
    result = compute_invalidation("TEST", "WATCHLIST", df)
    assert "Stop:" in result
    assert "ATR" in result
    assert "20 EMA" in result


# ---------------------------------------------------------------------------
# SELL action
# ---------------------------------------------------------------------------

def test_sell_includes_sma50_above():
    df = _make_price_df(n=100)
    result = compute_invalidation("TEST", "SELL", df)
    assert "50 SMA" in result
    assert "above" in result.lower() or "Close above" in result


def test_sell_includes_atr_stop_above():
    df = _make_price_df(n=100)
    result = compute_invalidation("TEST", "SELL", df)
    assert "Stop:" in result
    assert "ATR above" in result


def test_sell_stop_is_above_current_price():
    """For SELL, the ATR stop must be above the current price."""
    df = _make_price_df(n=100)
    current_price = float(df["Close"].iloc[-1])
    result = compute_invalidation("TEST", "SELL", df)
    # Extract dollar amount from "Stop: $XXX.XX"
    for part in result.split("|"):
        if "Stop:" in part:
            dollar = part.split("$")[1].split()[0]
            stop_price = float(dollar)
            assert stop_price > current_price
            break


def test_buy_stop_is_below_current_price():
    """For BUY, the ATR stop must be below the current price."""
    df = _make_price_df(n=100)
    current_price = float(df["Close"].iloc[-1])
    result = compute_invalidation("TEST", "BUY", df)
    for part in result.split("|"):
        if "Stop:" in part:
            dollar = part.split("$")[1].split()[0]
            stop_price = float(dollar)
            assert stop_price < current_price
            break


# ---------------------------------------------------------------------------
# HOLD action
# ---------------------------------------------------------------------------

def test_hold_shows_key_levels():
    df = _make_price_df(n=100)
    result = compute_invalidation("TEST", "HOLD", df)
    assert "Key levels" in result


def test_hold_includes_ema_and_sma():
    df = _make_price_df(n=100)
    result = compute_invalidation("TEST", "HOLD", df)
    assert "20 EMA" in result
    assert "50 SMA" in result


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_dataframe():
    df = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    result = compute_invalidation("TEST", "BUY", df)
    assert result == "Insufficient data for invalidation levels"


def test_very_short_dataframe():
    """With only a few rows, indicators may return NaN -- function should
    still return a string without crashing."""
    df = _make_price_df(n=5, base=50.0)
    result = compute_invalidation("TEST", "BUY", df)
    assert isinstance(result, str)
    assert len(result) > 0


def test_result_is_pipe_separated():
    """Multiple invalidation parts are joined with ' | '."""
    df = _make_price_df(n=100)
    result = compute_invalidation("TEST", "BUY", df)
    assert "|" in result
