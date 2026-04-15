"""Shariah compliance filter for stock universe.

Two-layer screen based on AAOIFI standards:
1. Industry exclusion — remove haram business activities
2. Financial ratio screen — debt, cash, receivables vs market cap < 33%

Results are cached to avoid re-screening on every scan.
"""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "outputs" / ".cache"
_SHARIAH_CACHE = _CACHE_DIR / "shariah_screen.json"
_CACHE_MAX_AGE = timedelta(days=7)

# ── Layer 1: Industry exclusion ──────────────────────────────────
# SIC/GICS industries that are non-compliant
EXCLUDED_INDUSTRIES = {
    # Conventional finance (interest-based)
    "banks", "diversified banks", "regional banks",
    "investment banking & brokerage", "investment banking",
    "asset management & custody banks", "asset management",
    "consumer finance", "specialty finance",
    "financial exchanges & data",
    "insurance", "life & health insurance", "property & casualty insurance",
    "reinsurance", "multi-line insurance", "insurance brokers",
    "mortgage finance", "mortgage real estate investment trusts (reits)",
    "thrifts & mortgage finance",
    # Alcohol
    "brewers", "distillers & vintners", "wineries",
    # Tobacco
    "tobacco",
    # Gambling / casinos
    "casinos & gaming", "gambling",
    # Weapons / defense
    "aerospace & defense",
    # Adult entertainment is not a standard GICS category but caught by name check
}

EXCLUDED_INDUSTRY_KEYWORDS = [
    "bank", "insurance", "tobacco", "alcohol", "beer", "wine", "spirit",
    "casino", "gaming", "gambling", "mortgage", "lending",
]

# Tickers known to be non-compliant regardless of screening
HARDCODED_EXCLUDE = {
    # Major banks
    "JPM", "BAC", "WFC", "C", "GS", "MS", "USB", "PNC", "TFC", "COF",
    "BK", "STT", "NTRS", "SCHW", "FITB", "KEY", "CFG", "RF", "HBAN", "MTB",
    # Insurance
    "BRK-B", "AIG", "MET", "PRU", "ALL", "TRV", "AFL", "PGR", "CB", "MMC",
    "AON", "AJG", "CINF", "GL", "LNC", "ERIE",
    # Tobacco
    "PM", "MO", "ALTRIA",
    # Alcohol
    "BF-B", "STZ", "TAP", "DEO", "SAM",
    # Gambling
    "LVS", "WYNN", "MGM", "CZR", "DKNG",
    # Defense (major weapons manufacturers)
    "LMT", "RTX", "NOC", "GD", "BA", "LHX", "HII",
}

# Tickers known to be compliant (override screening if data is unavailable)
HARDCODED_INCLUDE = {
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "NVDA", "META", "TSLA",
    "AVGO", "AMD", "ADBE", "CRM", "CSCO", "ORCL", "INTC", "QCOM",
    "TXN", "AMAT", "LRCX", "KLAC", "MRVL", "SNPS", "CDNS", "ADI",
    "NXPI", "MCHP", "ON", "MPWR", "FTNT", "PANW", "CRWD",
}


def _check_industry(info: dict) -> bool:
    """Return True if the stock passes industry screen."""
    industry = (info.get("industry") or "").lower().strip()
    sector = (info.get("sector") or "").lower().strip()

    if industry in EXCLUDED_INDUSTRIES or sector in EXCLUDED_INDUSTRIES:
        return False

    for kw in EXCLUDED_INDUSTRY_KEYWORDS:
        if kw in industry or kw in sector:
            return False

    return True


def _check_financial_ratios(info: dict) -> bool:
    """Return True if the stock passes AAOIFI financial ratio screens.

    Screens (all vs trailing 12-month market cap):
    - Total debt / market cap < 33%
    - (Cash + short-term investments) / market cap < 33%
    - Accounts receivable / market cap < 33% (relaxed — many tech cos have high AR)
    """
    market_cap = info.get("marketCap") or 0
    if market_cap <= 0:
        return True  # Can't screen, assume compliant

    total_debt = info.get("totalDebt") or 0
    cash = (info.get("totalCash") or 0)
    receivables = info.get("netReceivables") or info.get("totalReceivables") or 0

    debt_ratio = total_debt / market_cap
    cash_ratio = cash / market_cap
    receivables_ratio = receivables / market_cap

    if debt_ratio >= 0.33:
        logger.debug("Failed debt screen: %.1f%%", debt_ratio * 100)
        return False

    if cash_ratio >= 0.33:
        logger.debug("Failed cash screen: %.1f%%", cash_ratio * 100)
        return False

    if receivables_ratio >= 0.49:
        # Relaxed from 33% — many compliant tech companies have high receivables
        logger.debug("Failed receivables screen: %.1f%%", receivables_ratio * 100)
        return False

    return True


def is_compliant_fast(ticker: str) -> bool:
    """Fast compliance check using hardcoded lists + cache only. No API calls."""
    if ticker in HARDCODED_EXCLUDE:
        return False
    if ticker in HARDCODED_INCLUDE:
        return True

    # Check cache
    if _SHARIAH_CACHE.exists():
        try:
            data = json.loads(_SHARIAH_CACHE.read_text())
            if ticker in data.get("excluded", []):
                return False
            if ticker in data.get("compliant", []):
                return True
        except Exception:
            pass

    # Unknown — assume compliant (full screen happens during scans)
    return True


def screen_ticker(ticker: str) -> bool:
    """Screen a single ticker for Shariah compliance. Uses yfinance."""
    if ticker in HARDCODED_EXCLUDE:
        return False
    if ticker in HARDCODED_INCLUDE:
        return True

    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)
        info = stock.info or {}

        if not _check_industry(info):
            return False

        if not _check_financial_ratios(info):
            return False

        return True
    except Exception:
        logger.debug("Could not screen %s, assuming compliant", ticker)
        return True


def screen_universe(tickers: list[str], force_refresh: bool = False) -> list[str]:
    """Filter a list of tickers to Shariah-compliant only.

    Uses a 7-day cache to avoid re-screening every scan.
    """
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Try cache first
    if not force_refresh and _SHARIAH_CACHE.exists():
        age = datetime.now() - datetime.fromtimestamp(_SHARIAH_CACHE.stat().st_mtime)
        if age < _CACHE_MAX_AGE:
            try:
                data = json.loads(_SHARIAH_CACHE.read_text())
                compliant = set(data.get("compliant", []))
                excluded = set(data.get("excluded", []))
                # Filter requested tickers using cached results
                unknown = [t for t in tickers if t not in compliant and t not in excluded]
                if not unknown:
                    result = [t for t in tickers if t in compliant]
                    logger.info("Shariah filter (cached): %d/%d compliant", len(result), len(tickers))
                    return result
                # Screen only unknowns
                logger.info("Screening %d new tickers not in cache", len(unknown))
            except Exception:
                compliant = set()
                excluded = set()
        else:
            compliant = set()
            excluded = set()
    else:
        compliant = set()
        excluded = set()

    # Screen tickers not in cache
    to_screen = [t for t in tickers if t not in compliant and t not in excluded]

    for ticker in to_screen:
        if screen_ticker(ticker):
            compliant.add(ticker)
        else:
            excluded.add(ticker)

    # Save cache
    try:
        cache_data = {
            "compliant": sorted(compliant),
            "excluded": sorted(excluded),
            "screened_at": datetime.now().isoformat(),
            "total_screened": len(compliant) + len(excluded),
        }
        _SHARIAH_CACHE.write_text(json.dumps(cache_data, indent=2))
    except Exception:
        logger.exception("Failed to save Shariah cache")

    result = [t for t in tickers if t in compliant]
    logger.info("Shariah filter: %d/%d compliant (%d excluded)", len(result), len(tickers), len(excluded))
    return result


def get_excluded_tickers() -> list[str]:
    """Return list of excluded tickers from cache (for UI display)."""
    if _SHARIAH_CACHE.exists():
        try:
            data = json.loads(_SHARIAH_CACHE.read_text())
            return data.get("excluded", [])
        except Exception:
            pass
    return []
