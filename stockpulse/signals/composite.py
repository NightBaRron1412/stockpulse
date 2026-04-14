"""Composite score calculation and action classification."""
from stockpulse.config.settings import load_strategies

def compute_composite_score(signals: dict) -> float:
    total = 0.0
    total_weight = 0.0
    for name, sig in signals.items():
        score = sig.get("score", 0.0)
        weight = sig.get("weight", 0.0)
        total += score * weight
        total_weight += weight
    if total_weight == 0:
        return 0.0
    return max(-100.0, min(100.0, total / total_weight))

def classify_action(composite_score: float) -> str:
    """Classify into BUY/WATCHLIST/HOLD/CAUTION/SELL."""
    thresholds = load_strategies().get("thresholds", {})
    buy_threshold = thresholds.get("buy", 55)
    watchlist_threshold = thresholds.get("watchlist", 32)
    caution_threshold = thresholds.get("caution", -30)
    sell_threshold = thresholds.get("sell", -65)

    if composite_score >= buy_threshold:
        return "BUY"
    elif composite_score >= watchlist_threshold:
        return "WATCHLIST"
    elif composite_score <= sell_threshold:
        return "SELL"
    elif composite_score <= caution_threshold:
        return "CAUTION"
    else:
        return "HOLD"

def compute_confidence(composite_score: float) -> int:
    return min(int(abs(composite_score)), 100)
