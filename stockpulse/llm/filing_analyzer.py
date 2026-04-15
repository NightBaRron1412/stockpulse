"""LLM-powered SEC filing directional analysis using Claude API.

Direction comes from the text and tape.
This module uses Claude to determine if an 8-K filing is bullish, bearish, or neutral.
"""

import json
import logging

from stockpulse.config.settings import get_config

logger = logging.getLogger(__name__)


def analyze_filing_direction(
    ticker: str,
    form: str,
    items: list[str],
    description: str,
) -> dict:
    """Use LLM to determine directional impact of a filing.

    Returns:
        {
            "direction": "bullish" | "bearish" | "neutral",
            "confidence": float (0-1),
            "reasoning": str,
            "source": "llm" | "fallback",
        }
    """
    try:
        from stockpulse.llm.summarizer import _get_client
        client = _get_client()
        if client is None:
            return _fallback_direction(form, items, description)
    except Exception as e:
        logger.warning("LLM client failed for filing analysis: %s", str(e)[:80])
        return _fallback_direction(form, items, description)

    try:
        return _llm_direction(client, ticker, form, items, description)
    except Exception as e:
        logger.warning("LLM filing direction failed for %s %s: %s — using fallback", ticker, form, str(e)[:80])
        return _fallback_direction(form, items, description)


def _llm_direction(client, ticker: str, form: str, items: list[str], description: str) -> dict:
    """Use Claude to classify filing direction."""
    cfg = get_config()
    items_str = ", ".join(items) if items else "unknown"

    prompt = f"""Analyze this SEC filing for {ticker} and determine its likely market impact.

Form: {form}
Items: {items_str}
Description: {description[:500]}

Based on the form type, items, and description:
1. Is this likely bullish, bearish, or neutral for the stock price in the next 1-4 weeks?
2. How confident are you (0.0 to 1.0)?
3. Brief reasoning (one sentence).

Respond with ONLY valid JSON:
{{"direction": "bullish|bearish|neutral", "confidence": 0.X, "reasoning": "..."}}"""

    response = client.messages.create(
        model=cfg["llm_model"],
        max_tokens=150,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    result = json.loads(text)
    return {
        "direction": result.get("direction", "neutral"),
        "confidence": float(result.get("confidence", 0.5)),
        "reasoning": result.get("reasoning", ""),
        "source": "llm",
    }


def _fallback_direction(form: str, items: list[str], description: str) -> dict:
    """Rule-based fallback for filing direction."""
    # Red-flag items are always negative
    negative_items = {"4.02", "1.03", "3.01", "1.05", "2.05", "2.06"}
    if any(item in negative_items for item in items):
        return {"direction": "bearish", "confidence": 0.7,
                "reasoning": "Red-flag filing item detected", "source": "fallback"}

    # Check description for clues
    desc_lower = description.lower()
    if any(kw in desc_lower for kw in ["bankruptcy", "restatement", "delisting", "impairment"]):
        return {"direction": "bearish", "confidence": 0.6,
                "reasoning": "Negative keywords in description", "source": "fallback"}
    if any(kw in desc_lower for kw in ["acquisition", "agreement", "partnership", "contract"]):
        return {"direction": "bullish", "confidence": 0.4,
                "reasoning": "Potentially positive keywords in description", "source": "fallback"}

    return {"direction": "neutral", "confidence": 0.3,
            "reasoning": "Unable to determine direction from metadata alone", "source": "fallback"}
