import os
import pytest
import pandas as pd
from stockpulse.data.provider import get_price_history, get_current_quote, get_earnings_dates


def test_get_price_history_returns_dataframe():
    """Price history uses yfinance — no API key needed."""
    df = get_price_history("AAPL", period="1mo")
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 10
    assert "Close" in df.columns
    assert "Volume" in df.columns


@pytest.mark.skipif(not os.getenv("FINNHUB_API_KEY"), reason="FINNHUB_API_KEY not set")
def test_get_current_quote_returns_dict():
    """Quotes use Finnhub — needs API key."""
    quote = get_current_quote("AAPL")
    assert isinstance(quote, dict)
    assert "price" in quote
    assert quote["price"] > 0


@pytest.mark.skipif(not os.getenv("FINNHUB_API_KEY"), reason="FINNHUB_API_KEY not set")
def test_get_earnings_dates_returns_list():
    """Earnings use Finnhub — needs API key."""
    result = get_earnings_dates("AAPL")
    assert isinstance(result, list)
