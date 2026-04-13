"""Unified market data provider using yfinance."""
import logging
import pandas as pd
import yfinance as yf
from stockpulse.data.cache import get_cached, set_cached

logger = logging.getLogger(__name__)

def get_price_history(ticker: str, period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
    cache_key = f"price_{ticker}_{period}_{interval}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached
    try:
        t = yf.Ticker(ticker)
        df = t.history(period=period, interval=interval)
        if df.empty:
            logger.warning("No price data for %s", ticker)
            return pd.DataFrame()
        set_cached(cache_key, df)
        return df
    except Exception:
        logger.exception("Failed to fetch price data for %s", ticker)
        return pd.DataFrame()

def get_current_quote(ticker: str) -> dict:
    cache_key = f"quote_{ticker}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info
        quote = {
            "price": float(info.last_price) if hasattr(info, "last_price") else 0.0,
            "previous_close": float(info.previous_close) if hasattr(info, "previous_close") else 0.0,
            "market_cap": float(info.market_cap) if hasattr(info, "market_cap") else 0.0,
            "fifty_day_average": float(info.fifty_day_average) if hasattr(info, "fifty_day_average") else 0.0,
            "two_hundred_day_average": float(info.two_hundred_day_average) if hasattr(info, "two_hundred_day_average") else 0.0,
        }
        set_cached(cache_key, quote)
        return quote
    except Exception:
        logger.exception("Failed to fetch quote for %s", ticker)
        return {"price": 0.0, "previous_close": 0.0, "market_cap": 0.0}

def get_earnings_dates(ticker: str) -> list[dict]:
    cache_key = f"earnings_{ticker}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached
    try:
        t = yf.Ticker(ticker)
        cal = t.calendar
        if cal is None or (isinstance(cal, pd.DataFrame) and cal.empty):
            return []
        results = []
        if isinstance(cal, dict):
            if "Earnings Date" in cal:
                dates = cal["Earnings Date"]
                if not isinstance(dates, list):
                    dates = [dates]
                for d in dates:
                    results.append({
                        "date": str(d),
                        "days_away": (pd.Timestamp(d) - pd.Timestamp.now()).days,
                    })
        set_cached(cache_key, results)
        return results
    except Exception:
        logger.debug("No earnings data for %s", ticker)
        return []

def get_news(ticker: str) -> list[dict]:
    cache_key = f"news_{ticker}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached
    try:
        t = yf.Ticker(ticker)
        news = t.news or []
        results = []
        for item in news[:10]:
            results.append({
                "title": item.get("title", ""),
                "publisher": item.get("publisher", ""),
                "link": item.get("link", ""),
                "published": item.get("providerPublishTime", 0),
            })
        set_cached(cache_key, results)
        return results
    except Exception:
        logger.debug("No news for %s", ticker)
        return []

def bulk_download(tickers: list[str], period: str = "6mo") -> dict[str, pd.DataFrame]:
    cache_key = f"bulk_{'_'.join(sorted(tickers[:20]))}_{period}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached
    try:
        data = yf.download(tickers, period=period, group_by="ticker", threads=True, progress=False)
        result = {}
        if len(tickers) == 1:
            result[tickers[0]] = data
        else:
            for ticker in tickers:
                try:
                    df = data[ticker].dropna(how="all")
                    if not df.empty:
                        result[ticker] = df
                except (KeyError, AttributeError):
                    continue
        set_cached(cache_key, result)
        return result
    except Exception:
        logger.exception("Bulk download failed")
        return {}
