"""Stock universe management — S&P 500 + user watchlist."""
import logging
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
from stockpulse.config.settings import load_watchlists, load_strategies

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "outputs" / ".cache"
_SP500_CACHE = _CACHE_DIR / "sp500.csv"
_CACHE_MAX_AGE = timedelta(days=7)

def get_sp500_tickers() -> list[str]:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if _SP500_CACHE.exists():
        age = datetime.now() - datetime.fromtimestamp(_SP500_CACHE.stat().st_mtime)
        if age < _CACHE_MAX_AGE:
            df = pd.read_csv(_SP500_CACHE)
            return df["Symbol"].tolist()
    try:
        import io
        import requests
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        headers = {"User-Agent": "stockpulse/1.0 (educational; https://github.com/stockpulse)"}
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        tables = pd.read_html(io.StringIO(response.text))
        df = tables[0]
        tickers = df["Symbol"].str.replace(".", "-", regex=False).tolist()
        pd.DataFrame({"Symbol": tickers}).to_csv(_SP500_CACHE, index=False)
        logger.info("Fetched %d S&P 500 tickers from Wikipedia", len(tickers))
        return tickers
    except Exception:
        logger.exception("Failed to fetch S&P 500 list from Wikipedia")
        if _SP500_CACHE.exists():
            df = pd.read_csv(_SP500_CACHE)
            return df["Symbol"].tolist()
        return []

def get_user_watchlist() -> list[str]:
    wl = load_watchlists()
    return wl.get("user", [])

def get_full_universe() -> list[str]:
    sp500 = get_sp500_tickers()
    user = get_user_watchlist()
    combined = list(dict.fromkeys(sp500 + user))

    # Apply Shariah filter if enabled — but always keep user watchlist tickers
    filters = load_strategies().get("filters", {})
    if filters.get("shariah_only", False):
        from stockpulse.filters.shariah import screen_universe
        user_set = set(user)
        filtered = screen_universe([t for t in combined if t not in user_set])
        combined = list(dict.fromkeys(user + filtered))

    return combined
