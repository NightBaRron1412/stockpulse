"""Always-on file logger for alerts."""
import json
import logging
from datetime import datetime
from pathlib import Path
from stockpulse.config.settings import get_config

logger = logging.getLogger(__name__)

def _log_path() -> Path:
    cfg = get_config()
    path = Path(cfg["outputs_dir"]) / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path / "alerts.log"

def send_log_alert(alert: dict) -> bool:
    try:
        entry = {"timestamp": datetime.now().isoformat(), **alert}
        with open(_log_path(), "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
        return True
    except Exception:
        logger.exception("Failed to write alert log")
        return False
