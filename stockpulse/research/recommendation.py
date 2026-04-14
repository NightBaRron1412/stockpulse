"""Buy/sell/hold recommendation engine."""
import logging
from datetime import datetime

import pandas as pd

from stockpulse.signals.engine import (
    compute_all_signals, check_confirmation_buckets, compute_score_acceleration,
)
from stockpulse.signals.composite import compute_composite_score, classify_action, compute_confidence
from stockpulse.signals.pead import calc_pead_score
from stockpulse.research.scoring import compute_invalidation

logger = logging.getLogger(__name__)

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

    # Use WEIGHTED contribution to find the actual driver, not raw score
    def weighted(name, data):
        return data.get("score", 0) * data.get("weight", 0)

    # Find strongest SUPPORTING signal by weighted contribution
    supporting = [(n, d) for n, d in signals.items()
                  if d.get("weight", 0) > 0 and (
                     (composite > 0 and d.get("score", 0) > 0) or
                     (composite < 0 and d.get("score", 0) < 0))]
    # Find strongest OPPOSING signal by weighted contribution
    opposing = [(n, d) for n, d in signals.items()
                if d.get("weight", 0) > 0 and (
                   (composite > 0 and d.get("score", 0) < -10) or
                   (composite < 0 and d.get("score", 0) > 10))]

    if supporting:
        best = max(supporting, key=lambda x: abs(weighted(x[0], x[1])))
        parts = [f"{direction} ({composite:.1f}) driven by {best[0]} ({best[1]['score']:+.0f})"]
    else:
        parts = [f"Weakly {direction.lower()} ({composite:.1f}), no strong supporting signals"]

    if opposing:
        worst = max(opposing, key=lambda x: abs(weighted(x[0], x[1])))
        parts.append(f"Headwind: {worst[0]} ({worst[1]['score']:+.0f})")

    return ". ".join(parts)

def generate_recommendation(ticker: str, df: pd.DataFrame) -> dict:
    signals = compute_all_signals(ticker, df)
    composite = compute_composite_score(signals)
    action = classify_action(composite)
    confidence = compute_confidence(composite)
    invalidation = compute_invalidation(ticker, action, df)

    # Check confirmation buckets
    confirmation = check_confirmation_buckets(signals)

    # Downgrade BUY to WATCHLIST if not enough buckets confirm
    if action == "BUY" and not confirmation["passes"]:
        action = "WATCHLIST"

    # ---- PEAD overlay (event-driven, not weighted) ----
    pead_score = calc_pead_score(ticker)
    if abs(pead_score) > 5:
        signals["pead"] = {"score": pead_score, "weight": 0.0, "value": pead_score}
        # PEAD modifies the composite directly (not weighted, it's an event overlay)
        composite += pead_score * 0.15

    # ---- Score acceleration modifier ----
    accel_bonus = compute_score_acceleration(ticker, composite, confirmation)
    composite += accel_bonus

    # Re-classify with updated composite
    action = classify_action(composite)
    confidence = compute_confidence(composite)

    # Re-apply confirmation downgrade after PEAD/accel adjustments
    if action == "BUY" and not confirmation["passes"]:
        action = "WATCHLIST"

    # ---- WATCHLIST -> BUY auto-upgrade per expert ----
    if action == "WATCHLIST" and composite >= 50:
        vol_score = signals.get("volume", {}).get("score", 0)
        breakout_score = signals.get("breakout", {}).get("score", 0)

        # Fast-track: score >= 70 AND RVOL >= 2.5 (volume score > 60)
        if composite >= 70 and vol_score >= 60:
            action = "BUY"
        # Normal upgrade: volume or breakout confirmation
        elif vol_score >= 30 or breakout_score >= 20:
            if confirmation.get("passes", False):
                action = "BUY"

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
        "confirmation": confirmation,
    }

def rank_recommendations(recommendations: list[dict]) -> list[dict]:
    return sorted(recommendations, key=lambda r: abs(r["composite_score"]), reverse=True)
