"""SEC filing analysis — 8-K event classification per expert specs."""

import logging
import os
import re
from datetime import datetime, timedelta

from stockpulse.config.settings import get_config
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
    """Score recent filings using expert's importance map.

    Returns a score from -100 to +100.
    Positive = catalysts present, negative = red flags detected.
    """
    filings = get_recent_filings(ticker, lookback_days)
    if not filings:
        return 0.0

    score = 0.0
    for filing in filings:
        importance = filing["importance"]
        form = filing["form"]

        if filing["is_negative"]:
            # Red-flag items are scored negatively
            score -= importance * 60
        elif form in ("8-K", "8-K/A"):
            # Normal 8-K: importance determines magnitude
            score += importance * 30
        elif form in ("10-K", "10-K/A", "10-Q", "10-Q/A"):
            score += importance * 10
        elif "13D" in form or "13G" in form:
            score += importance * 25  # beneficial ownership = notable catalyst

    return max(-100.0, min(100.0, score))
