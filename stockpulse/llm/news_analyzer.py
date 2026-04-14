"""LLM-powered news event classification using AMD Claude API.

Replaces keyword-based sentiment with structured event analysis.
Expert recommended classifying event TYPE, not just sentiment:
- guidance raise/cut
- earnings beat/miss
- lawsuit/regulatory action
- M&A
- buyback
- contract win/loss
- management change
"""

import json
import logging

from stockpulse.config.settings import get_config
from stockpulse.data.provider import get_news

logger = logging.getLogger(__name__)


def _get_llm_client():
    """Get Anthropic client (reuses summarizer's client setup)."""
    try:
        from stockpulse.llm.summarizer import _get_client
        return _get_client()
    except Exception:
        return None


def analyze_news_sentiment(ticker: str) -> dict:
    """Analyze recent news headlines using LLM for structured event classification.

    Returns:
        {
            "score": float (-100 to +100),
            "event_count": int,
            "events": [{"headline": str, "event_type": str, "sentiment": str, "impact": str}],
            "summary": str,
            "source": "llm" or "fallback",
        }
    """
    news = get_news(ticker)
    if not news:
        return {"score": 0.0, "event_count": 0, "events": [], "summary": "No recent news", "source": "none"}

    headlines = [n.get("title", "") for n in news if n.get("title")]
    if not headlines:
        return {"score": 0.0, "event_count": 0, "events": [], "summary": "No headlines", "source": "none"}

    # Try LLM analysis
    client = _get_llm_client()
    if client is not None:
        try:
            return _llm_analyze(client, ticker, headlines)
        except Exception:
            logger.debug("LLM news analysis failed for %s, using fallback", ticker)

    # Fallback: simple keyword counting (weight stays low)
    return _fallback_analyze(ticker, headlines)


def _llm_analyze(client, ticker: str, headlines: list[str]) -> dict:
    """Use Claude to classify news events and score sentiment."""
    cfg = get_config()
    headlines_text = "\n".join(f"- {h}" for h in headlines[:10])

    prompt = f"""Analyze these recent news headlines for {ticker}. For each headline, classify:
1. event_type: one of [earnings, guidance, m_and_a, buyback, contract, lawsuit, regulatory, management_change, product, partnership, analyst, macro, other]
2. sentiment: one of [very_positive, positive, neutral, negative, very_negative]
3. impact: one of [high, medium, low]

Headlines:
{headlines_text}

Respond with ONLY valid JSON (no markdown, no explanation):
{{"events": [{{"headline": "...", "event_type": "...", "sentiment": "...", "impact": "..."}}], "overall_score": <number from -100 to 100>, "summary": "<one sentence>"}}"""

    response = client.messages.create(
        model=cfg["llm_model"],
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()

    # Parse JSON response
    # Handle potential markdown wrapping
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    result = json.loads(text)

    score = float(result.get("overall_score", 0))
    score = max(-100.0, min(100.0, score))

    return {
        "score": score,
        "event_count": len(result.get("events", [])),
        "events": result.get("events", []),
        "summary": result.get("summary", ""),
        "source": "llm",
    }


_POSITIVE_KEYWORDS = [
    "beat", "surge", "jump", "soar", "upgrade", "strong", "growth",
    "profit", "record", "exceeded", "outperform", "bullish",
    "rally", "breakout", "dividend", "partnership", "expansion", "approval",
]

_NEGATIVE_KEYWORDS = [
    "miss", "decline", "drop", "fall", "downgrade", "weak", "loss",
    "layoff", "cut", "warning", "concern", "sell", "bearish",
    "crash", "lawsuit", "investigation", "recall", "debt",
    "bankruptcy", "fraud", "resign", "delay",
]


def _fallback_analyze(ticker: str, headlines: list[str]) -> dict:
    """Keyword-based fallback when LLM is unavailable."""
    positive = 0
    negative = 0

    for headline in headlines:
        h = headline.lower()
        for kw in _POSITIVE_KEYWORDS:
            if kw in h:
                positive += 1
        for kw in _NEGATIVE_KEYWORDS:
            if kw in h:
                negative += 1

    total = positive + negative
    if total == 0:
        return {"score": 0.0, "event_count": len(headlines), "events": [],
                "summary": "No clear sentiment from keywords", "source": "fallback"}

    ratio = (positive - negative) / total
    score = max(-100.0, min(100.0, ratio * 50))  # lower magnitude for fallback

    return {
        "score": score,
        "event_count": len(headlines),
        "events": [],
        "summary": f"Keyword analysis: {positive} positive, {negative} negative mentions",
        "source": "fallback",
    }
