"""Discord webhook alert sender (optional)."""
import logging
import requests
from stockpulse.config.settings import get_config

logger = logging.getLogger(__name__)

def _format_embed(alert: dict) -> dict:
    ticker = alert.get("ticker", "???")
    action = alert.get("action", "???")
    confidence = alert.get("confidence", 0)
    color = {"BUY": 0x00FF00, "SELL": 0xFF0000, "HOLD": 0xFFFF00,
             "WATCHLIST": 0x0099FF, "CAUTION": 0xFF8C00}.get(action, 0x808080)
    return {"embeds": [{"title": f"{ticker} -- {action}", "description": alert.get("thesis", ""),
        "color": color, "fields": [
            {"name": "Confidence", "value": f"{confidence}%", "inline": True},
            {"name": "Type", "value": alert.get("type", "signal"), "inline": True},
            {"name": "Technical", "value": alert.get("technical_summary", "N/A")[:200], "inline": False},
            {"name": "Catalysts", "value": alert.get("catalyst_summary", "N/A")[:200], "inline": False},
            {"name": "Invalidation", "value": alert.get("invalidation", "N/A")[:200], "inline": False},
        ]}]}

def send_discord_alert(alert: dict) -> bool:
    cfg = get_config()
    if not cfg["alerts_discord"]:
        return False
    url = cfg["discord_webhook_url"]
    if not url:
        logger.warning("Discord enabled but webhook URL not configured")
        return False
    try:
        payload = _format_embed(alert)
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception:
        logger.exception("Discord alert failed")
        return False
