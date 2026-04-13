"""Rules-based fallback summary engine -- used when LLM is unavailable."""

def fallback_thesis(action: str, signals: dict, composite: float) -> str:
    strongest_name = ""
    strongest_score = 0
    for name, data in signals.items():
        if abs(data.get("score", 0)) > abs(strongest_score):
            strongest_name = name
            strongest_score = data.get("score", 0)
    direction = "Bullish" if composite > 0 else "Bearish"
    parts = [f"{direction} outlook with composite score {composite:.1f}.",
        f"Strongest signal: {strongest_name} ({strongest_score:.0f})."]
    if signals.get("earnings", {}).get("score", 0) > 0:
        parts.append("Earnings approaching -- catalyst potential.")
    if signals.get("sec_filing", {}).get("score", 0) > 0:
        parts.append("Recent SEC filing activity noted.")
    if abs(signals.get("volume", {}).get("score", 0)) > 30:
        parts.append("Unusual volume detected.")
    return " ".join(parts)

def fallback_catalyst_summary(ticker: str, signals: dict) -> str:
    parts = []
    if signals.get("earnings", {}).get("score", 0) > 0:
        parts.append("Earnings event approaching")
    if signals.get("sec_filing", {}).get("score", 0) > 10:
        parts.append("Recent SEC filing activity (8-K or Form 4)")
    if signals.get("news_sentiment", {}).get("score", 0) > 10:
        parts.append("Positive news sentiment detected")
    elif signals.get("news_sentiment", {}).get("score", 0) < -10:
        parts.append("Negative news sentiment detected")
    return ". ".join(parts) if parts else "No significant catalysts detected"
