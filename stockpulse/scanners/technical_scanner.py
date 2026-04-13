"""Technical scanner -- scans a list of tickers for technical signals."""
import logging
import pandas as pd
from stockpulse.data.provider import get_price_history
from stockpulse.signals.engine import compute_all_signals
from stockpulse.signals.composite import compute_composite_score

logger = logging.getLogger(__name__)

def scan_technical(tickers: list[str]) -> list[dict]:
    results = []
    for ticker in tickers:
        try:
            df = get_price_history(ticker, period="1y")
            if df.empty or len(df) < 50:
                continue
            signals = compute_all_signals(ticker, df)
            composite = compute_composite_score(signals)
            results.append({"ticker": ticker, "composite_score": composite, "signals": signals, "df": df})
        except Exception:
            logger.debug("Technical scan failed for %s", ticker)
    results.sort(key=lambda r: abs(r["composite_score"]), reverse=True)
    return results
