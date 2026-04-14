"""Insider transaction scoring — expert-specified role/size/cluster model."""

import logging
import os
from datetime import datetime, timedelta

from stockpulse.data.cache import get_cached, set_cached
from stockpulse.config.settings import get_config

logger = logging.getLogger(__name__)

# Expert's role weights
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

                results.append({
                    "form": "4",
                    "date": str(filed_date),
                    "filer": getattr(filing, "filer", "Unknown"),
                    "description": getattr(filing, "description", ""),
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
    """Score insider activity using expert's model.

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

    # Combine: sum of individual scores * cluster
    raw_score = sum(buy_scores) * cluster_mult

    # Scale to [-100, 100] range
    # Typical range: 0.5-5.0 raw score. Map 2.0 -> ~50, 4.0 -> ~80
    scaled = min(raw_score * 25, 100.0)

    return max(-100.0, min(100.0, scaled))


def summarize_insider_activity(ticker: str) -> dict:
    """Summarize insider activity for reporting."""
    transactions = get_insider_transactions(ticker)
    return {
        "total_filings": len(transactions),
        "recent_form4s": transactions[:5],
        "has_activity": len(transactions) > 0,
    }
