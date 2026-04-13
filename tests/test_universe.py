from stockpulse.data.universe import get_sp500_tickers, get_full_universe

def test_get_sp500_tickers_returns_list():
    tickers = get_sp500_tickers()
    assert isinstance(tickers, list)
    assert len(tickers) > 400
    assert "AAPL" in tickers
    assert "MSFT" in tickers

def test_get_full_universe_includes_user_watchlist():
    universe = get_full_universe()
    assert "AMD" in universe
    assert len(universe) == len(set(universe))
