"""Historical pattern matching — store signal snapshots and find similar setups.

After each scan, records signal profiles. When generating suggestions,
finds past instances with similar patterns and reports outcomes.
"""
import json
import logging
import math
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_HISTORY_FILE = Path(__file__).resolve().parent.parent.parent / "outputs" / ".pattern_history.json"
_MAX_HISTORY = 5000  # Max entries to keep


def _load_history() -> list[dict]:
    try:
        if _HISTORY_FILE.exists():
            return json.loads(_HISTORY_FILE.read_text())
    except Exception:
        pass
    return []


def _save_history(history: list[dict]) -> None:
    try:
        _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Trim to max size
        if len(history) > _MAX_HISTORY:
            history = history[-_MAX_HISTORY:]
        _HISTORY_FILE.write_text(json.dumps(history, default=str))
    except Exception:
        logger.debug("Failed to save pattern history")


def record_pattern(rec: dict) -> None:
    """Record a signal snapshot for future pattern matching."""
    signals = rec.get("signals", {})
    entry = {
        "ticker": rec["ticker"],
        "date": datetime.now().strftime("%Y-%m-%d"),
        "action": rec.get("action", "HOLD"),
        "score": round(rec.get("composite_score", 0), 1),
        "rsi": round(signals.get("rsi", {}).get("score", 0), 1),
        "macd": round(signals.get("macd", {}).get("score", 0), 1),
        "ma": round(signals.get("moving_averages", {}).get("score", 0), 1),
        "volume": round(signals.get("volume", {}).get("score", 0), 1),
        "breakout": round(signals.get("breakout", {}).get("score", 0), 1),
        "rs": round(signals.get("relative_strength", {}).get("score", 0), 1),
        "outcome_5d": None,
        "outcome_10d": None,
        "outcome_20d": None,
        "entry_price": None,
    }

    # Get current price for outcome tracking
    try:
        from stockpulse.data.provider import get_current_quote
        quote = get_current_quote(rec["ticker"])
        entry["entry_price"] = quote.get("price", 0)
    except Exception:
        pass

    history = _load_history()

    # Don't duplicate same ticker/date
    history = [h for h in history if not (h["ticker"] == entry["ticker"] and h["date"] == entry["date"])]
    history.append(entry)
    _save_history(history)


def update_outcomes(ticker: str, current_price: float) -> None:
    """Update outcome fields for past patterns of this ticker."""
    history = _load_history()
    modified = False

    for entry in history:
        if entry["ticker"] != ticker or entry.get("entry_price") is None:
            continue
        if entry["entry_price"] <= 0:
            continue

        entry_price = entry["entry_price"]
        pct_change = ((current_price - entry_price) / entry_price) * 100

        try:
            entry_date = datetime.strptime(entry["date"], "%Y-%m-%d")
            days_since = (datetime.now() - entry_date).days
        except Exception:
            continue

        if days_since >= 5 and entry.get("outcome_5d") is None:
            entry["outcome_5d"] = round(pct_change, 2)
            modified = True
        if days_since >= 10 and entry.get("outcome_10d") is None:
            entry["outcome_10d"] = round(pct_change, 2)
            modified = True
        if days_since >= 20 and entry.get("outcome_20d") is None:
            entry["outcome_20d"] = round(pct_change, 2)
            modified = True

    if modified:
        _save_history(history)


def find_similar_patterns(ticker: str, signals: dict, min_matches: int = 3) -> dict | None:
    """Find historical patterns similar to the current signal profile.

    Uses cosine similarity on normalized signal scores.

    Returns {
        match_count: int,
        avg_return_5d: float,
        avg_return_10d: float,
        avg_return_20d: float,
        win_rate: float (% positive outcomes),
        best_case: str,
        worst_case: str,
    } or None if insufficient history.
    """
    history = _load_history()
    if len(history) < 10:
        return None

    # Build current signal vector
    current = _signal_vector(signals)
    if _magnitude(current) == 0:
        return None

    # Find matches (same ticker or any ticker with similar profile)
    matches = []
    for entry in history:
        # Skip entries without outcomes
        if entry.get("outcome_10d") is None:
            continue

        # Build historical vector
        hist_vec = [
            entry.get("rsi", 0), entry.get("macd", 0), entry.get("ma", 0),
            entry.get("volume", 0), entry.get("breakout", 0), entry.get("rs", 0),
        ]

        similarity = _cosine_similarity(current, hist_vec)
        if similarity > 0.7:  # Threshold for "similar"
            matches.append(entry)

    if len(matches) < min_matches:
        return None

    # Compute aggregate stats
    returns_5d = [m["outcome_5d"] for m in matches if m.get("outcome_5d") is not None]
    returns_10d = [m["outcome_10d"] for m in matches if m.get("outcome_10d") is not None]
    returns_20d = [m["outcome_20d"] for m in matches if m.get("outcome_20d") is not None]

    if not returns_10d:
        return None

    wins = sum(1 for r in returns_10d if r > 0)

    best = max(returns_10d)
    worst = min(returns_10d)
    best_entry = next(m for m in matches if m.get("outcome_10d") == best)
    worst_entry = next(m for m in matches if m.get("outcome_10d") == worst)

    return {
        "match_count": len(matches),
        "avg_return_5d": round(sum(returns_5d) / len(returns_5d), 2) if returns_5d else 0,
        "avg_return_10d": round(sum(returns_10d) / len(returns_10d), 2),
        "avg_return_20d": round(sum(returns_20d) / len(returns_20d), 2) if returns_20d else 0,
        "win_rate": round(wins / len(returns_10d) * 100, 0),
        "best_case": f"{best_entry['ticker']} on {best_entry['date']}: +{best:.1f}%",
        "worst_case": f"{worst_entry['ticker']} on {worst_entry['date']}: {worst:+.1f}%",
    }


def _signal_vector(signals: dict) -> list[float]:
    """Extract normalized signal vector for comparison."""
    return [
        signals.get("rsi", {}).get("score", 0),
        signals.get("macd", {}).get("score", 0),
        signals.get("moving_averages", {}).get("score", 0),
        signals.get("volume", {}).get("score", 0),
        signals.get("breakout", {}).get("score", 0),
        signals.get("relative_strength", {}).get("score", 0),
    ]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = _magnitude(a)
    mag_b = _magnitude(b)
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _magnitude(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v))
