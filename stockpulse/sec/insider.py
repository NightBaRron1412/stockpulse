"""Insider transaction scoring —  role/size/cluster model."""

import logging
import os
from datetime import datetime, timedelta

from stockpulse.data.cache import get_cached, set_cached
from stockpulse.config.settings import get_config

logger = logging.getLogger(__name__)

# Role weights
_ROLE_WEIGHTS = {
    "CEO": 1.00, "CFO": 1.00, "Chief Executive": 1.00, "Chief Financial": 1.00,
    "COO": 0.80, "President": 0.80, "Chair": 0.80, "Chairman": 0.80,
    "EVP": 0.65, "General Counsel": 0.65, "SVP": 0.65,
    "Director": 0.50, "VP": 0.50,
    "10%": 0.40, "10% Owner": 0.40,
}


def _get_role_weight(filer_text: str) -> float:
    """Determine role weight from filer text."""
    text = str(filer_text).upper()
    for role_key, weight in _ROLE_WEIGHTS.items():
        if role_key.upper() in text:
            return weight
    return 0.40  # default


def get_insider_transactions(ticker: str, lookback_days: int = 30) -> list[dict]:
    """Get recent insider transactions (Form 4)."""
    cache_key = f"insider_v2_{ticker}_{lookback_days}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        from edgar import Company
        os.environ.setdefault("EDGAR_IDENTITY", get_config()["sec_user_agent"])

        company = Company(ticker)
        filings = company.get_filings(form="4")

        results = []
        cutoff = datetime.now() - timedelta(days=lookback_days)

        for filing in filings[:30]:
            try:
                filed_date = filing.filing_date
                if hasattr(filed_date, 'date'):
                    filed_date = filed_date.date()
                if isinstance(filed_date, str):
                    filed_date = datetime.strptime(filed_date, "%Y-%m-%d").date()

                if filed_date < cutoff.date():
                    continue

                # Get reporting owner name from EdgarTools
                filer_name = "Unknown"
                try:
                    # Try all_entities first (gives reporting owner info)
                    entities = getattr(filing, "all_entities", None)
                    if entities and len(entities) > 1:
                        # Second entity is typically the reporting person
                        filer_name = entities[1].get("company", "") or entities[1].get("name", "Unknown")
                    elif entities and len(entities) == 1:
                        filer_name = entities[0].get("company", "Unknown")
                    # Also try header for officer title
                    header = getattr(filing, "header", None)
                    if header and hasattr(header, "reporting_owner"):
                        ro = header.reporting_owner
                        if hasattr(ro, "name"):
                            filer_name = ro.name
                except Exception:
                    pass

                desc = getattr(filing, "primary_doc_description", "") or ""

                results.append({
                    "form": "4",
                    "date": str(filed_date),
                    "filer": filer_name,
                    "description": desc,
                    "days_ago": (datetime.now().date() - filed_date).days,
                })
            except Exception:
                continue

        set_cached(cache_key, results)
        return results
    except Exception:
        logger.debug("Failed to fetch insider data for %s", ticker)
        return []


def score_insider_activity(ticker: str, lookback_days: int = 30) -> float:
    """Score insider activity using the model.

    Only scores buys (Form 4 with transaction code P).
    Uses role weight, cluster multiplier, and recency decay.

    Since we can't easily parse transaction codes from the filing list metadata,
    we use filing count and filer role as proxies. More filings in a short window
    by C-suite = higher cluster score.

    Returns score from -100 to +100. Positive = insider buying activity.
    """
    transactions = get_insider_transactions(ticker, lookback_days)
    if not transactions:
        return 0.0

    # Score each transaction
    buy_scores = []
    for txn in transactions:
        filer = txn.get("filer", "")
        days_ago = txn.get("days_ago", 30)

        role_weight = _get_role_weight(filer)

        # Recency decay: recent filings matter more
        recency = max(0.1, 1.0 - (days_ago / (lookback_days * 1.5)))

        buy_scores.append(role_weight * recency)

    if not buy_scores:
        return 0.0

    # Cluster multiplier
    recent_filings = sum(1 for t in transactions if t.get("days_ago", 999) <= 14)

    if recent_filings >= 3:
        cluster_mult = 1.50
    elif recent_filings >= 2:
        cluster_mult = 1.25
    else:
        cluster_mult = 1.00

    # Use log1p diminishing returns for filing count 
    # Don't let 30 routine Form 4s score the same as 3 meaningful insider buys
    import math
    avg_score = sum(buy_scores) / len(buy_scores) if buy_scores else 0
    count_factor = math.log1p(len(buy_scores))  # log(1+n): 1->0.69, 3->1.39, 10->2.40, 30->3.43
    raw_score = avg_score * count_factor * cluster_mult

    # Scale: 1.0 raw -> ~25 score, cap at 60 (insider alone shouldn't dominate)
    scaled = min(raw_score * 25, 60.0)

    return max(-100.0, min(100.0, scaled))


def summarize_insider_activity(ticker: str) -> dict:
    """Summarize insider activity for reporting."""
    transactions = get_insider_transactions(ticker)
    return {
        "total_filings": len(transactions),
        "recent_form4s": transactions[:5],
        "has_activity": len(transactions) > 0,
    }
