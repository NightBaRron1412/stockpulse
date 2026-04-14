"""SEC filing analysis — 8-K event classification per expert specs."""

import logging
import os
import re
from datetime import datetime, timedelta

from stockpulse.config.settings import get_config, load_strategies
from stockpulse.data.cache import get_cached, set_cached

logger = logging.getLogger(__name__)

# Expert's 8-K item importance map
_8K_IMPORTANCE = {
    "2.02": 1.00,  # Results of operations / financial condition
    "4.02": 1.00,  # Non-reliance on prior financials / restatement
    "1.03": 0.90,  # Bankruptcy or receivership
    "3.01": 0.90,  # Delisting / continued listing failure
    "1.05": 0.90,  # Material cybersecurity incident
    "2.01": 0.80,  # Acquisition or disposition of assets
    "1.01": 0.65,  # Material definitive agreement
    "2.03": 0.65,  # Creation of direct financial obligation
    "2.04": 0.65,  # Triggering events modifying obligations
    "2.05": 0.55,  # Costs for exit/disposal
    "2.06": 0.55,  # Material impairments
    "5.02": 0.50,  # Officer/director departure or appointment
    "8.01": 0.20,  # Other events (catch-all)
}

# Red-flag items that are almost always negative
_NEGATIVE_ITEMS = {"4.02", "1.03", "3.01", "1.05", "2.05", "2.06"}


def get_recent_filings(ticker: str, lookback_days: int = 30) -> list[dict]:
    """Get recent SEC filings with 8-K event classification."""
    cache_key = f"sec_filings_v2_{ticker}_{lookback_days}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        from edgar import Company
        cfg = get_config()
        os.environ.setdefault("EDGAR_IDENTITY", cfg["sec_user_agent"])

        company = Company(ticker)
        filings = company.get_filings()

        results = []
        cutoff = datetime.now() - timedelta(days=lookback_days)

        for filing in filings[:50]:
            try:
                filed_date = filing.filing_date
                if hasattr(filed_date, 'date'):
                    filed_date = filed_date.date()
                if isinstance(filed_date, str):
                    filed_date = datetime.strptime(filed_date, "%Y-%m-%d").date()

                if filed_date < cutoff.date():
                    continue

                form = filing.form
                description = getattr(filing, "description", "")

                # Parse 8-K items from description
                items = []
                importance = 0.20  # default
                is_negative = False

                if form == "8-K" or form == "8-K/A":
                    items = _parse_8k_items(description)
                    if items:
                        # Use the highest-importance item
                        importance = max(_8K_IMPORTANCE.get(item, 0.20) for item in items)
                        is_negative = any(item in _NEGATIVE_ITEMS for item in items)
                    else:
                        importance = 0.20
                elif form in ("10-K", "10-K/A"):
                    importance = 0.40
                elif form in ("10-Q", "10-Q/A"):
                    importance = 0.30
                elif "13D" in form or "13G" in form:
                    importance = 0.70  # beneficial ownership stake

                results.append({
                    "form": form,
                    "date": str(filed_date),
                    "description": description,
                    "items": items,
                    "importance": importance,
                    "is_negative": is_negative,
                    "url": getattr(filing, "filing_url", ""),
                })
            except Exception:
                continue

        set_cached(cache_key, results)
        return results
    except Exception:
        logger.debug("Failed to fetch SEC filings for %s", ticker)
        return []


def _parse_8k_items(description: str) -> list[str]:
    """Extract 8-K item numbers from filing description text.

    8-K descriptions often contain patterns like:
    'Items 2.02, 9.01' or 'Item 1.01' or 'Results of Operations'
    """
    items = []
    # Match item patterns like "1.01", "2.02", etc.
    matches = re.findall(r'\b(\d\.\d{2})\b', description)
    for m in matches:
        if m in _8K_IMPORTANCE:
            items.append(m)

    # Also check for keyword-based detection if no item numbers found
    if not items:
        desc_lower = description.lower()
        keyword_map = {
            "results of operations": "2.02",
            "financial condition": "2.02",
            "acquisition": "2.01",
            "disposition": "2.01",
            "material agreement": "1.01",
            "definitive agreement": "1.01",
            "departure": "5.02",
            "appointment": "5.02",
            "officer": "5.02",
            "director": "5.02",
            "bankruptcy": "1.03",
            "restatement": "4.02",
            "non-reliance": "4.02",
            "delisting": "3.01",
            "cybersecurity": "1.05",
            "impairment": "2.06",
        }
        for keyword, item in keyword_map.items():
            if keyword in desc_lower:
                items.append(item)
                break  # Take the first match

    return list(set(items))


def score_filings(ticker: str, lookback_days: int = 30) -> float:
    """Score filings with expert caps: unparsed SEC capped at +25,
    half-life decay, log1p diminishing returns for filing count."""
    cfg_sec = load_strategies().get("signals", {}).get("sec_filing", {})
    raw_cap = cfg_sec.get("raw_cap_without_direction", 25)
    half_lives = cfg_sec.get("half_life_days", {"8k": 3, "10k_10q": 2, "form4_purchase": 10})

    filings = get_recent_filings(ticker, lookback_days)
    if not filings:
        return 0.0

    import math

    score = 0.0
    filing_count = 0

    for filing in filings:
        importance = filing["importance"]
        form = filing["form"]
        days_ago = 0
        try:
            from datetime import datetime
            filed = datetime.strptime(filing["date"], "%Y-%m-%d").date()
            days_ago = (datetime.now().date() - filed).days
        except Exception:
            days_ago = 15

        # Half-life decay
        if form in ("8-K", "8-K/A"):
            hl = half_lives.get("8k", 3)
        elif form in ("10-K", "10-K/A", "10-Q", "10-Q/A"):
            hl = half_lives.get("10k_10q", 2)
        else:
            hl = 5

        decay = 0.5 ** (days_ago / max(hl, 1))

        if filing["is_negative"]:
            score -= importance * 60 * decay
            continue

        # LLM directional parsing for important 8-Ks
        if form in ("8-K", "8-K/A") and importance >= 0.50:
            try:
                from stockpulse.llm.filing_analyzer import analyze_filing_direction
                direction = analyze_filing_direction(
                    ticker, form, filing.get("items", []), filing.get("description", "")
                )
                if direction["direction"] == "bullish":
                    contribution = importance * 35 * (0.5 + direction["confidence"] * 0.5) * decay
                    score += contribution
                elif direction["direction"] == "bearish":
                    score -= importance * 35 * (0.5 + direction["confidence"] * 0.5) * decay
                else:
                    score += min(importance * 10 * decay, raw_cap)
            except Exception:
                score += min(importance * 10 * decay, raw_cap)
        elif "13D" in form or "13G" in form:
            score += importance * 25 * decay
        else:
            # Routine filings — cap contribution
            score += min(importance * 10 * decay, raw_cap * 0.5)

        filing_count += 1

    # Diminishing returns: log1p scaling for count
    if filing_count > 1:
        count_factor = math.log1p(filing_count) / math.log1p(1)  # normalize so 1 filing = 1.0x
        score = score / max(count_factor, 1.0)

    # Cap total score if no directional parsing was used
    score = max(-100.0, min(score, raw_cap if score > 0 else 100.0))

    return max(-100.0, min(100.0, score))
