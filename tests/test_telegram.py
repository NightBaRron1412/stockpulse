"""Tests for stockpulse.alerts.telegram_alert module."""
from unittest.mock import patch, AsyncMock

from stockpulse.alerts.telegram_alert import (
    _format_message,
    _format_advisor_message,
    send_telegram_alert,
)


# ---------------------------------------------------------------------------
# _format_message -- action emoji mapping
# ---------------------------------------------------------------------------

def test_format_message_buy_emoji():
    msg = _format_message({"ticker": "AAPL", "action": "BUY", "confidence": 80, "thesis": "Strong"})
    assert "\u2705" in msg  # green check
    assert "AAPL" in msg
    assert "BUY" in msg
    assert "80%" in msg


def test_format_message_sell_emoji():
    msg = _format_message({"ticker": "TSLA", "action": "SELL", "confidence": 70, "thesis": "Weak"})
    assert "\ud83d\udd34" in msg  # red circle
    assert "SELL" in msg


def test_format_message_hold_emoji():
    msg = _format_message({"ticker": "MSFT", "action": "HOLD", "confidence": 50, "thesis": "Neutral"})
    assert "\u26a0\ufe0f" in msg  # warning
    assert "HOLD" in msg


def test_format_message_watchlist_emoji():
    msg = _format_message({"ticker": "GOOG", "action": "WATCHLIST", "confidence": 40, "thesis": "Watch"})
    assert "\ud83d\udd0d" in msg  # magnifying glass
    assert "WATCHLIST" in msg


def test_format_message_caution_emoji():
    msg = _format_message({"ticker": "META", "action": "CAUTION", "confidence": 60, "thesis": "Risk"})
    assert "\ud83d\udea8" in msg  # rotating light
    assert "CAUTION" in msg


def test_format_message_unknown_action_gets_info_emoji():
    msg = _format_message({"ticker": "X", "action": "UNKNOWN", "confidence": 10, "thesis": ""})
    assert "\u2139\ufe0f" in msg  # info


def test_format_message_includes_type():
    msg = _format_message({"ticker": "T", "action": "BUY", "confidence": 90, "thesis": "Go", "type": "intraday"})
    assert "[intraday]" in msg


def test_format_message_defaults_type_to_signal():
    msg = _format_message({"ticker": "T", "action": "BUY", "confidence": 90, "thesis": "Go"})
    assert "[signal]" in msg


# ---------------------------------------------------------------------------
# _format_message -- truncation at 4000 chars
# ---------------------------------------------------------------------------

def test_format_message_truncates_long_thesis():
    long_thesis = "A" * 5000
    msg = _format_message({"ticker": "T", "action": "BUY", "confidence": 1, "thesis": long_thesis})
    assert len(msg) <= 4000
    assert msg.endswith("...")


def test_format_message_short_message_not_truncated():
    msg = _format_message({"ticker": "T", "action": "BUY", "confidence": 1, "thesis": "short"})
    assert len(msg) < 4000
    assert not msg.endswith("...")


# ---------------------------------------------------------------------------
# _format_message -- delegation to _format_advisor_message
# ---------------------------------------------------------------------------

def test_format_message_delegates_when_severity_present():
    """If 'severity' key is present, _format_message delegates to advisor formatter."""
    alert = {"severity": "urgent", "ticker": "AAPL", "action": "SELL", "thesis": "Drop"}
    msg = _format_message(alert)
    assert "URGENT" in msg


# ---------------------------------------------------------------------------
# _format_advisor_message -- severity prefix
# ---------------------------------------------------------------------------

def test_advisor_urgent_prefix():
    alert = {"severity": "urgent", "ticker": "AAPL", "action": "SELL", "thesis": "Crash"}
    msg = _format_advisor_message(alert)
    assert "URGENT" in msg
    assert "AAPL" in msg


def test_advisor_actionable_prefix():
    alert = {"severity": "actionable", "ticker": "GOOG", "action": "BUY", "thesis": "Breakout"}
    msg = _format_advisor_message(alert)
    assert "ACTION" in msg


def test_advisor_info_prefix():
    alert = {"severity": "info", "ticker": "MSFT", "action": "HOLD", "thesis": "Stable"}
    msg = _format_advisor_message(alert)
    assert "INFO" in msg


def test_advisor_unknown_severity_falls_back():
    alert = {"severity": "weird", "ticker": "X", "action": "HOLD", "thesis": "?"}
    msg = _format_advisor_message(alert)
    # Should still produce a message without crashing
    assert "X" in msg
    assert "HOLD" in msg


def test_advisor_includes_technical_summary():
    alert = {
        "severity": "urgent",
        "ticker": "AAPL",
        "action": "SELL",
        "thesis": "Drop",
        "technical_summary": "RSI oversold",
    }
    msg = _format_advisor_message(alert)
    assert "RSI oversold" in msg


def test_advisor_includes_type():
    alert = {"severity": "info", "ticker": "T", "action": "HOLD", "thesis": "ok", "type": "advisor"}
    msg = _format_advisor_message(alert)
    assert "[advisor]" in msg


def test_advisor_truncates_long_message():
    alert = {
        "severity": "urgent",
        "ticker": "T",
        "action": "SELL",
        "thesis": "B" * 5000,
    }
    msg = _format_advisor_message(alert)
    assert len(msg) <= 4000
    assert msg.endswith("...")


# ---------------------------------------------------------------------------
# send_telegram_alert -- returns False when not configured
# ---------------------------------------------------------------------------

_DISABLED_CONFIG = {
    "alerts_telegram": False,
    "telegram_bot_token": "",
    "telegram_chat_id": "",
}


@patch("stockpulse.alerts.telegram_alert.get_config", return_value=_DISABLED_CONFIG)
def test_send_returns_false_when_disabled(mock_cfg):
    result = send_telegram_alert({"ticker": "X", "action": "BUY", "confidence": 50, "thesis": ""})
    assert result is False


_ENABLED_NO_TOKEN = {
    "alerts_telegram": True,
    "telegram_bot_token": "",
    "telegram_chat_id": "",
}


@patch("stockpulse.alerts.telegram_alert.get_config", return_value=_ENABLED_NO_TOKEN)
def test_send_returns_false_when_token_missing(mock_cfg):
    result = send_telegram_alert({"ticker": "X", "action": "BUY", "confidence": 50, "thesis": ""})
    assert result is False


_ENABLED_NO_CHAT = {
    "alerts_telegram": True,
    "telegram_bot_token": "fake-token",
    "telegram_chat_id": "",
}


@patch("stockpulse.alerts.telegram_alert.get_config", return_value=_ENABLED_NO_CHAT)
def test_send_returns_false_when_chat_id_missing(mock_cfg):
    result = send_telegram_alert({"ticker": "X", "action": "BUY", "confidence": 50, "thesis": ""})
    assert result is False


_ENABLED_FULL = {
    "alerts_telegram": True,
    "telegram_bot_token": "fake-token",
    "telegram_chat_id": "123456",
}


@patch("stockpulse.alerts.telegram_alert.get_config", return_value=_ENABLED_FULL)
@patch("stockpulse.alerts.telegram_alert._send_async", new_callable=AsyncMock, return_value=True)
def test_send_calls_async_when_configured(mock_send, mock_cfg):
    """When fully configured, send_telegram_alert formats and dispatches."""
    result = send_telegram_alert({"ticker": "AAPL", "action": "BUY", "confidence": 90, "thesis": "Go"})
    assert result is True


@patch("stockpulse.alerts.telegram_alert.get_config", return_value=_ENABLED_FULL)
@patch("stockpulse.alerts.telegram_alert.asyncio")
def test_send_passes_token_and_chat_id(mock_asyncio, mock_cfg):
    """Verify asyncio loop is created and used."""
    mock_loop = mock_asyncio.new_event_loop.return_value
    mock_loop.run_until_complete.return_value = True
    send_telegram_alert({"ticker": "X", "action": "BUY", "confidence": 50, "thesis": ""})
    mock_asyncio.new_event_loop.assert_called_once()
    mock_loop.run_until_complete.assert_called_once()
    mock_loop.close.assert_called_once()
