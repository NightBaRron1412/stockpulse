import os
import pytest
from stockpulse.scanners.market_scanner import run_full_scan

# Skip if no Finnhub API key — scanner requires live price data
pytestmark = pytest.mark.skipif(
    not os.getenv("FINNHUB_API_KEY"),
    reason="FINNHUB_API_KEY not set"
)

def test_full_scan_returns_recommendations():
    results = run_full_scan(tickers=["AAPL", "MSFT"])
    assert isinstance(results, list)
    assert len(results) > 0
    assert all("ticker" in r for r in results)
    assert all("action" in r for r in results)
    assert all("confidence" in r for r in results)
