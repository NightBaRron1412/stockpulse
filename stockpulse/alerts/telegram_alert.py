"""Telegram alert sender (optional)."""
import asyncio
import logging
from stockpulse.config.settings import get_config

logger = logging.getLogger(__name__)

def _format_message(alert: dict) -> str:
    # Advisor alerts get severity-based formatting
    if alert.get("severity"):
        return _format_advisor_message(alert)

    ticker = alert.get("ticker", "???")
    action = alert.get("action", "???")
    confidence = alert.get("confidence", 0)
    thesis = alert.get("thesis", "")
    emoji = {"BUY": "\u2705", "SELL": "\ud83d\udd34", "HOLD": "\u26a0\ufe0f",
             "WATCHLIST": "\ud83d\udd0d", "CAUTION": "\ud83d\udea8"}.get(action, "\u2139\ufe0f")
    alert_type = alert.get("type", "signal")
    msg = f"{emoji} {ticker} — {action} ({confidence}%)\n\n{thesis}\n\n[{alert_type}]"
    if len(msg) > 4000:
        msg = msg[:3997] + "..."
    return msg


def _format_advisor_message(alert: dict) -> str:
    severity = alert.get("severity", "info")
    prefix = {
        "urgent": "\U0001f6a8 URGENT",
        "actionable": "\U0001f4cb ACTION",
        "info": "\u2139\ufe0f INFO",
    }.get(severity, "\U0001f4cb")

    ticker = alert.get("ticker", "???")
    action = alert.get("action", "???")
    summary = alert.get("thesis", "")
    details = alert.get("technical_summary", "")
    stype = alert.get("type", "advisor")

    msg = f"{prefix} | {ticker} -- {action}\n\n{summary}"
    if details:
        msg += f"\n\n{details}"
    msg += f"\n\n[{stype}]"

    if len(msg) > 4000:
        msg = msg[:3997] + "..."
    return msg

async def _send_async(token: str, chat_id: str, text: str) -> bool:
    try:
        from telegram import Bot
        bot = Bot(token=token)
        await bot.send_message(chat_id=chat_id, text=text)
        return True
    except Exception:
        logger.exception("Telegram send failed")
        return False

def send_telegram_alert(alert: dict) -> bool:
    cfg = get_config()
    if not cfg["alerts_telegram"]:
        return False
    token = cfg["telegram_bot_token"]
    chat_id = cfg["telegram_chat_id"]
    if not token or not chat_id:
        logger.warning("Telegram enabled but token/chat_id not configured")
        return False
    text = _format_message(alert)
    try:
        # Use new event loop to avoid conflict with any running loop (e.g. FastAPI/uvicorn)
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_send_async(token, chat_id, text))
        finally:
            loop.close()
    except Exception:
        logger.exception("Telegram alert failed")
        return False
