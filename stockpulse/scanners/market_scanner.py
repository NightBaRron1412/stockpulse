"""Market scanner -- orchestrates full scan across universe."""
import logging
from datetime import datetime
from stockpulse.data.universe import get_full_universe
from stockpulse.data.provider import get_price_history
from stockpulse.research.recommendation import generate_recommendation, rank_recommendations
from stockpulse.config.settings import load_strategies

logger = logging.getLogger(__name__)

def run_full_scan(tickers: list[str] | None = None) -> list[dict]:
    if tickers is None:
        tickers = get_full_universe()
    logger.info("Starting full scan of %d tickers at %s", len(tickers), datetime.now())
    recommendations = []
    for i, ticker in enumerate(tickers):
        try:
            df = get_price_history(ticker, period="1y")
            if df.empty or len(df) < 50:
                logger.debug("Skipping %s: insufficient data (%d rows)", ticker, len(df))
                continue
            rec = generate_recommendation(ticker, df)
            recommendations.append(rec)
            if (i + 1) % 50 == 0:
                logger.info("Scanned %d/%d tickers", i + 1, len(tickers))
        except Exception:
            logger.debug("Scan failed for %s", ticker)
    ranked = rank_recommendations(recommendations)
    logger.info("Scan complete: %d tickers scanned, %d recommendations generated", len(tickers), len(ranked))
    return ranked

def run_watchlist_scan(tickers: list[str]) -> list[dict]:
    return run_full_scan(tickers=tickers)
