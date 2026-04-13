"""Insider transaction monitoring via EdgarTools."""
import logging
import os
from datetime import datetime, timedelta
from stockpulse.data.cache import get_cached, set_cached
from stockpulse.config.settings import get_config

logger = logging.getLogger(__name__)

def get_insider_transactions(ticker: str, lookback_days: int = 30) -> list[dict]:
    cache_key = f"insider_{ticker}_{lookback_days}"
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
        for filing in filings[:20]:
            try:
                filed_date = filing.filing_date
                if hasattr(filed_date, 'date'):
                    filed_date = filed_date.date()
                if isinstance(filed_date, str):
                    filed_date = datetime.strptime(filed_date, "%Y-%m-%d").date()
                if filed_date >= cutoff.date():
                    results.append({
                        "form": "4",
                        "date": str(filed_date),
                        "filer": getattr(filing, "filer", "Unknown"),
                        "description": getattr(filing, "description", ""),
                    })
            except Exception:
                continue
        set_cached(cache_key, results)
        return results
    except Exception:
        logger.debug("Failed to fetch insider data for %s", ticker)
        return []

def summarize_insider_activity(ticker: str) -> dict:
    transactions = get_insider_transactions(ticker)
    return {
        "total_filings": len(transactions),
        "recent_form4s": transactions[:5],
        "has_activity": len(transactions) > 0,
    }
