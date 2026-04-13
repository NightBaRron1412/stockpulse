"""Telegram alert sender (optional)."""
import asyncio
import logging
from stockpulse.config.settings import get_config

logger = logging.getLogger(__name__)

def _format_message(alert: dict) -> str:
    ticker = alert.get("ticker", "???")
    action = alert.get("action", "???")
    confidence = alert.get("confidence", 0)
    thesis = alert.get("thesis", "")
    emoji = {"BUY": "\u2705", "SELL": "\ud83d\udd34", "HOLD": "\u26a0\ufe0f"}.get(action, "\u2139\ufe0f")
    return (f"{emoji} *{ticker}* -- {action} (confidence: {confidence}%)\n\n"
            f"{thesis}\n\n_{alert.get('type', 'signal')}_")

async def _send_async(token: str, chat_id: str, text: str) -> bool:
    try:
        from telegram import Bot
        bot = Bot(token=token)
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
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
        return asyncio.run(_send_async(token, chat_id, text))
    except Exception:
        logger.exception("Telegram alert failed")
        return False
