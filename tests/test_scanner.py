from stockpulse.scanners.market_scanner import run_full_scan


def test_full_scan_returns_recommendations():
    """Scanner uses yfinance for OHLCV — no API key needed."""
    results = run_full_scan(tickers=["AAPL", "MSFT"])
    assert isinstance(results, list)
    assert len(results) > 0
    assert all("ticker" in r for r in results)
    assert all("action" in r for r in results)
    assert all("confidence" in r for r in results)
