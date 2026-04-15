"""Unified market data provider. Finnhub for quotes/news/earnings, yfinance for OHLCV."""
import logging
import time
from datetime import datetime, timedelta

import finnhub
import pandas as pd
import yfinance as yf

from stockpulse.config.settings import get_config
from stockpulse.data.cache import get_cached, set_cached

logger = logging.getLogger(__name__)

_client = None
_last_call_time = 0.0
_MIN_CALL_INTERVAL = 1.0  # seconds between Finnhub API calls (60/min limit)


def _get_client() -> finnhub.Client:
    """Lazy-init Finnhub client."""
    global _client
    if _client is None:
        cfg = get_config()
        api_key = cfg["finnhub_api_key"]
        if not api_key:
            raise ValueError(
                "FINNHUB_API_KEY not set. Get a free key at https://finnhub.io"
            )
        _client = finnhub.Client(api_key=api_key)
    return _client


def _rate_limit():
    """Simple rate limiter — wait if needed to stay under 60 calls/min."""
    global _last_call_time
    now = time.time()
    elapsed = now - _last_call_time
    if elapsed < _MIN_CALL_INTERVAL:
        time.sleep(_MIN_CALL_INTERVAL - elapsed)
    _last_call_time = time.time()


def get_price_history(
    ticker: str, period: str = "6mo", interval: str = "1d"
) -> pd.DataFrame:
    """Fetch OHLCV price history via yfinance (free, no API key needed).

    Finnhub's stock_candles endpoint requires a paid plan, so we use yfinance
    for historical candle data. Finnhub is used for quotes, news, and earnings.
    """
    cache_key = f"price_{ticker}_{period}_{interval}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    # Use start/end dates instead of period to avoid yfinance 'possibly delisted' bug
    period_days = {"1y": 365, "6mo": 180, "3mo": 90, "1mo": 30, "5d": 5}
    days = period_days.get(period, 365)
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    try:
        df = yf.download(ticker, start=start, interval=interval, progress=False, timeout=15)
        if df.empty:
            logger.warning("No price data for %s", ticker)
            return pd.DataFrame()
        # yf.download returns MultiIndex columns for single ticker — flatten
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        set_cached(cache_key, df)
        return df
    except Exception:
        logger.exception("Failed to fetch price data for %s", ticker)
        return pd.DataFrame()


def get_current_quote(ticker: str) -> dict:
    """Get current price and key quote data via Finnhub."""
    cache_key = f"quote_{ticker}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        _rate_limit()
        client = _get_client()
        q = client.quote(ticker)

        quote = {
            "price": float(q.get("c", 0)),  # current price
            "previous_close": float(q.get("pc", 0)),  # previous close
            "open": float(q.get("o", 0)),
            "high": float(q.get("h", 0)),
            "low": float(q.get("l", 0)),
            "change": float(q.get("d", 0)),
            "change_percent": float(q.get("dp", 0)),
            "market_cap": 0.0,  # Not in quote endpoint
        }
        set_cached(cache_key, quote)
        return quote
    except ValueError:
        raise
    except Exception:
        logger.exception("Failed to fetch quote for %s", ticker)
        return {"price": 0.0, "previous_close": 0.0, "market_cap": 0.0}


def get_earnings_dates(ticker: str) -> list[dict]:
    """Get upcoming earnings dates for a ticker via Finnhub."""
    cache_key = f"earnings_{ticker}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        _rate_limit()
        client = _get_client()
        today = datetime.now().strftime("%Y-%m-%d")
        future = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")
        data = client.earnings_calendar(_from=today, to=future, symbol=ticker)

        results = []
        for item in data.get("earningsCalendar", []):
            if item.get("symbol") == ticker:
                date_str = item.get("date", "")
                if date_str:
                    try:
                        d = datetime.strptime(date_str, "%Y-%m-%d")
                        results.append({
                            "date": date_str,
                            "days_away": (d - datetime.now()).days,
                        })
                    except ValueError:
                        pass

        set_cached(cache_key, results)
        return results
    except ValueError:
        raise
    except Exception:
        logger.debug("No earnings data for %s", ticker)
        return []


def get_news(ticker: str) -> list[dict]:
    """Get recent news for a ticker via Finnhub."""
    cache_key = f"news_{ticker}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        _rate_limit()
        client = _get_client()
        today = datetime.now().strftime("%Y-%m-%d")
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        news = client.company_news(ticker, _from=week_ago, to=today)

        results = []
        for item in (news or [])[:10]:
            results.append({
                "title": item.get("headline", ""),
                "publisher": item.get("source", ""),
                "link": item.get("url", ""),
                "published": item.get("datetime", 0),
            })

        set_cached(cache_key, results)
        return results
    except ValueError:
        raise
    except Exception:
        logger.debug("No news for %s", ticker)
        return []


def bulk_download(tickers: list[str], period: str = "1y") -> dict[str, pd.DataFrame]:
    """Download price data for multiple tickers via yfinance bulk download.

    Uses explicit start/end dates instead of period='1y' to avoid
    yfinance bug where period-based requests randomly fail with
    'possibly delisted' for valid tickers.
    """
    # Convert period to start date
    period_days = {"1y": 365, "6mo": 180, "3mo": 90, "1mo": 30, "5d": 5}
    days = period_days.get(period, 365)
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    end = datetime.now().strftime("%Y-%m-%d")

    try:
        data = yf.download(
            tickers, start=start, end=end, group_by="ticker", threads=True,
            progress=False, timeout=30,
        )
        result = {}
        # Flatten MultiIndex columns if single ticker
        if isinstance(data.columns, pd.MultiIndex) and len(tickers) == 1:
            data.columns = data.columns.get_level_values(0)

        if len(tickers) == 1:
            if not data.empty:
                result[tickers[0]] = data
                set_cached(f"price_{tickers[0]}_{period}_1d", data)
        else:
            for ticker in tickers:
                try:
                    df = data[ticker].dropna(how="all")
                    if not df.empty and len(df) >= 10:
                        result[ticker] = df
                        # Cache individual tickers for intraday single lookups
                        set_cached(f"price_{ticker}_{period}_1d", df)
                except (KeyError, AttributeError):
                    continue
        return result
    except Exception:
        logger.exception("Bulk download failed")
        return {}
