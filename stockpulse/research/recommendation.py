"""Buy/sell/hold recommendation engine."""
from datetime import datetime
import pandas as pd
from stockpulse.signals.engine import compute_all_signals
from stockpulse.signals.composite import compute_composite_score, classify_action, compute_confidence
from stockpulse.research.scoring import compute_invalidation

def _build_technical_summary(signals: dict) -> str:
    parts = []
    rsi = signals.get("rsi", {})
    if rsi.get("value") is not None:
        parts.append(f"RSI: {rsi['value']:.0f}")
    macd = signals.get("macd", {})
    if macd.get("score", 0) > 20:
        parts.append("MACD: bullish")
    elif macd.get("score", 0) < -20:
        parts.append("MACD: bearish")
    else:
        parts.append("MACD: neutral")
    ma = signals.get("moving_averages", {})
    if ma.get("score", 0) > 0:
        parts.append("Above key SMAs")
    elif ma.get("score", 0) < 0:
        parts.append("Below key SMAs")
    vol = signals.get("volume", {})
    if abs(vol.get("score", 0)) > 30:
        parts.append("Volume spike detected")
    adx = signals.get("adx", {})
    if adx.get("score", 0) > 20:
        parts.append("Strong uptrend (ADX)")
    elif adx.get("score", 0) < -20:
        parts.append("Strong downtrend (ADX)")
    return ". ".join(parts) if parts else "Insufficient technical data"

def _build_catalyst_summary(signals: dict) -> str:
    parts = []
    if signals.get("earnings", {}).get("score", 0) > 0:
        parts.append("Earnings approaching")
    if signals.get("sec_filing", {}).get("score", 0) > 10:
        parts.append("Recent SEC filing activity")
    news = signals.get("news_sentiment", {})
    if news.get("score", 0) > 10:
        parts.append("Positive news sentiment")
    elif news.get("score", 0) < -10:
        parts.append("Negative news sentiment")
    return ". ".join(parts) if parts else "No significant catalysts detected"

def _build_thesis(action: str, signals: dict, composite: float) -> str:
    direction = "Bullish" if composite > 0 else "Bearish"

    # Find strongest SUPPORTING signal (same direction as composite)
    supporting = [(n, d) for n, d in signals.items()
                  if (composite > 0 and d.get("score", 0) > 0) or
                     (composite < 0 and d.get("score", 0) < 0)]
    # Find strongest OPPOSING signal
    opposing = [(n, d) for n, d in signals.items()
                if (composite > 0 and d.get("score", 0) < -10) or
                   (composite < 0 and d.get("score", 0) > 10)]

    if supporting:
        best = max(supporting, key=lambda x: abs(x[1].get("score", 0)))
        parts = [f"{direction} ({composite:.1f}) driven by {best[0]} ({best[1]['score']:+.0f})"]
    else:
        parts = [f"Weakly {direction.lower()} ({composite:.1f}), no strong supporting signals"]

    if opposing:
        worst = max(opposing, key=lambda x: abs(x[1].get("score", 0)))
        parts.append(f"Headwind: {worst[0]} ({worst[1]['score']:+.0f})")

    return ". ".join(parts)

def generate_recommendation(ticker: str, df: pd.DataFrame) -> dict:
    signals = compute_all_signals(ticker, df)
    composite = compute_composite_score(signals)
    action = classify_action(composite)
    confidence = compute_confidence(composite)
    invalidation = compute_invalidation(ticker, action, df)
    return {
        "ticker": ticker,
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "confidence": confidence,
        "composite_score": round(composite, 2),
        "thesis": _build_thesis(action, signals, composite),
        "technical_summary": _build_technical_summary(signals),
        "catalyst_summary": _build_catalyst_summary(signals),
        "invalidation": invalidation,
        "signals": signals,
    }

def rank_recommendations(recommendations: list[dict]) -> list[dict]:
    return sorted(recommendations, key=lambda r: abs(r["composite_score"]), reverse=True)
