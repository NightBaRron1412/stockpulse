"""EdgarTools wrapper for SEC filing data."""
import logging
import os
from datetime import datetime, timedelta
from stockpulse.config.settings import get_config
from stockpulse.data.cache import get_cached, set_cached

logger = logging.getLogger(__name__)

def get_recent_filings(ticker: str, lookback_days: int = 30) -> list[dict]:
    cache_key = f"sec_filings_{ticker}_{lookback_days}"
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
                if filed_date >= cutoff.date():
                    results.append({
                        "form": filing.form,
                        "date": str(filed_date),
                        "description": getattr(filing, "description", ""),
                        "url": getattr(filing, "filing_url", ""),
                    })
            except Exception:
                continue
        set_cached(cache_key, results)
        return results
    except Exception:
        logger.debug("Failed to fetch SEC filings for %s", ticker)
        return []
