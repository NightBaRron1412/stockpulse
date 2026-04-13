"""Catalyst scanner -- scans for SEC filings, earnings, insider activity."""
import logging
from stockpulse.sec.filings import get_recent_filings
from stockpulse.sec.insider import get_insider_transactions
from stockpulse.data.provider import get_earnings_dates

logger = logging.getLogger(__name__)

def scan_catalysts(tickers: list[str]) -> dict[str, dict]:
    results = {}
    for ticker in tickers:
        try:
            catalysts = {
                "filings": get_recent_filings(ticker, lookback_days=30),
                "insiders": get_insider_transactions(ticker, lookback_days=30),
                "earnings": get_earnings_dates(ticker),
            }
            if any(catalysts.values()):
                results[ticker] = catalysts
        except Exception:
            logger.debug("Catalyst scan failed for %s", ticker)
    return results
