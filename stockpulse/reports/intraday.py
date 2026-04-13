"""Intraday condition change reports."""
import logging
from datetime import datetime
from pathlib import Path
from stockpulse.config.settings import get_config

logger = logging.getLogger(__name__)
_previous_actions: dict[str, str] = {}

def detect_changes(recommendations: list[dict]) -> list[dict]:
    global _previous_actions
    changes = []
    for rec in recommendations:
        ticker = rec["ticker"]
        current_action = rec["action"]
        prev_action = _previous_actions.get(ticker)
        if prev_action is not None and prev_action != current_action:
            changes.append({"ticker": ticker, "previous_action": prev_action,
                "new_action": current_action, "confidence": rec["confidence"],
                "thesis": rec["thesis"], "type": "action_change"})
        _previous_actions[ticker] = current_action
    return changes

def generate_intraday_report(changes: list[dict]) -> str | None:
    if not changes:
        return None
    cfg = get_config()
    reports_dir = Path(cfg["outputs_dir"]) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    report_path = reports_dir / f"{timestamp}-intraday.md"
    lines = [f"# StockPulse Intraday Update -- {timestamp}", "",
        f"**{len(changes)} condition change(s) detected**", ""]
    for c in changes:
        lines.append(f"- **{c['ticker']}**: {c['previous_action']} -> {c['new_action']} "
            f"(confidence: {c['confidence']}%) -- {c['thesis']}")
    lines.extend(["", "---"])
    report_path.write_text("\n".join(lines))
    logger.info("Intraday report: %d changes written to %s", len(changes), report_path)
    return str(report_path)
