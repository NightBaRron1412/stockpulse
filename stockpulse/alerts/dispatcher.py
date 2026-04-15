"""Alert dispatcher -- routes alerts to all configured channels."""
import logging
from stockpulse.alerts.log_alert import send_log_alert
from stockpulse.alerts.telegram_alert import send_telegram_alert
from stockpulse.alerts.discord_alert import send_discord_alert
from stockpulse.config.settings import load_strategies

logger = logging.getLogger(__name__)

def dispatch_alert(alert: dict) -> dict[str, bool]:
    # Advisor alerts bypass confidence threshold — they have their own severity system
    is_advisor = alert.get("severity") is not None or (alert.get("type", "") or "").startswith("advisor_")
    if not is_advisor:
        thresholds = load_strategies().get("thresholds", {})
        confidence_min = thresholds.get("confidence_min", 30)
        if alert.get("confidence", 0) < confidence_min:
            logger.debug("Alert for %s suppressed: confidence %d < %d",
                alert.get("ticker"), alert.get("confidence", 0), confidence_min)
            return {"suppressed": True}
    results = {}
    results["log"] = send_log_alert(alert)
    results["telegram"] = send_telegram_alert(alert)
    results["discord"] = send_discord_alert(alert)
    sent = [k for k, v in results.items() if v and k != "suppressed"]
    logger.info("Alert dispatched for %s via: %s", alert.get("ticker"), sent)
    return results

def dispatch_recommendations(recommendations: list[dict]) -> None:
    for rec in recommendations:
        if rec.get("action") == "BUY":
            alert = {"type": "recommendation", **rec}
            if rec.get("high_conviction"):
                alert["thesis"] = "HIGH CONVICTION: " + alert.get("thesis", "")
            dispatch_alert(alert)
        elif rec.get("action") == "SELL":
            dispatch_alert({"type": "recommendation", **rec})
        elif rec.get("action") == "WATCHLIST" and rec.get("confidence", 0) >= 45:
            dispatch_alert({"type": "watchlist", **rec})
        elif rec.get("action") == "CAUTION" and rec.get("position_caution"):
            dispatch_alert({"type": "position_caution", **rec})
