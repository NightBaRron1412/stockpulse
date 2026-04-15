"""Intraday condition change reports."""
import json
import logging
from datetime import datetime
from pathlib import Path
from stockpulse.config.settings import get_config

logger = logging.getLogger(__name__)

_STATE_FILE = Path(__file__).resolve().parent.parent.parent / "outputs" / ".intraday_state.json"


def _load_previous_actions() -> dict[str, str]:
    try:
        if _STATE_FILE.exists():
            return json.loads(_STATE_FILE.read_text())
    except Exception:
        pass
    return {}


def _save_previous_actions(actions: dict[str, str]) -> None:
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps(actions))
    except Exception:
        logger.debug("Failed to save intraday state")


def detect_changes(recommendations: list[dict]) -> list[dict]:
    """Detect tier changes AND significant score movements.

    Returns changes for:
    - Action tier transitions (HOLD → WATCHLIST, etc.)
    - Score movements > 8 points within the same tier
    - Tickers approaching tier boundaries (within 5 points)
    """
    previous = _load_previous_actions()
    changes = []

    for rec in recommendations:
        ticker = rec["ticker"]
        current_action = rec["action"]
        current_score = rec.get("composite_score", 0)

        prev_entry = previous.get(ticker)
        if isinstance(prev_entry, str):
            # Legacy format: just action string. Migrate.
            prev_action = prev_entry
            prev_score = 0
        elif isinstance(prev_entry, dict):
            prev_action = prev_entry.get("action")
            prev_score = prev_entry.get("score", 0)
        else:
            prev_action = None
            prev_score = 0

        if prev_action is not None:
            # 1. Tier change
            if prev_action != current_action:
                changes.append({
                    "ticker": ticker,
                    "previous_action": prev_action,
                    "new_action": current_action,
                    "confidence": rec.get("confidence", 0),
                    "thesis": rec.get("thesis", ""),
                    "type": "action_change",
                    "score_delta": round(current_score - prev_score, 1),
                })
            else:
                # 2. Significant score movement (>8 points within same tier)
                delta = current_score - prev_score
                if abs(delta) >= 8:
                    direction = "improved" if delta > 0 else "deteriorated"
                    changes.append({
                        "ticker": ticker,
                        "previous_action": prev_action,
                        "new_action": current_action,
                        "confidence": rec.get("confidence", 0),
                        "thesis": f"{ticker} {direction} {abs(delta):.1f} pts ({prev_score:+.1f} → {current_score:+.1f})",
                        "type": "score_movement",
                        "score_delta": round(delta, 1),
                    })

                # 3. Approaching tier boundary (within 5 points of BUY threshold)
                buy_threshold = 55
                if current_action == "WATCHLIST" and current_score >= buy_threshold - 5 and prev_score < buy_threshold - 5:
                    changes.append({
                        "ticker": ticker,
                        "previous_action": prev_action,
                        "new_action": current_action,
                        "confidence": rec.get("confidence", 0),
                        "thesis": f"{ticker} approaching BUY threshold ({current_score:+.1f}, need {buy_threshold})",
                        "type": "approaching_threshold",
                        "score_delta": round(delta, 1),
                    })

        # Save current state (action + score)
        previous[ticker] = {"action": current_action, "score": round(current_score, 1)}

    _save_previous_actions(previous)
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
