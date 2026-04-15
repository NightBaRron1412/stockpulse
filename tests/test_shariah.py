"""Tests for stockpulse.filters.shariah — Shariah compliance screening."""
import sys
from unittest.mock import patch, MagicMock

from stockpulse.filters.shariah import (
    _check_industry,
    _check_financial_ratios,
    is_compliant_fast,
    screen_ticker,
)
from stockpulse.portfolio.advisor import _is_etf


# ── _check_industry ───────────────────────────────────────────────

def test_check_industry_excludes_banks():
    assert _check_industry({"industry": "Regional Banks", "sector": ""}) is False


def test_check_industry_excludes_insurance():
    assert _check_industry({"industry": "Life & Health Insurance", "sector": ""}) is False


def test_check_industry_excludes_tobacco():
    assert _check_industry({"industry": "Tobacco", "sector": ""}) is False


def test_check_industry_excludes_alcohol():
    assert _check_industry({"industry": "Brewers", "sector": ""}) is False
    assert _check_industry({"industry": "Distillers & Vintners", "sector": ""}) is False


def test_check_industry_excludes_gambling():
    assert _check_industry({"industry": "Casinos & Gaming", "sector": ""}) is False


def test_check_industry_excludes_weapons():
    assert _check_industry({"industry": "Aerospace & Defense", "sector": ""}) is False


def test_check_industry_excludes_via_keyword_in_sector():
    """Keyword match on sector field catches generic banking sector."""
    assert _check_industry({"industry": "", "sector": "Commercial Banking Services"}) is False


def test_check_industry_excludes_keyword_mortgage():
    assert _check_industry({"industry": "Mortgage Finance", "sector": ""}) is False


def test_check_industry_allows_tech():
    assert _check_industry({"industry": "Semiconductors", "sector": "Technology"}) is True


def test_check_industry_allows_healthcare():
    assert _check_industry({"industry": "Biotechnology", "sector": "Healthcare"}) is True


def test_check_industry_allows_manufacturing():
    assert _check_industry({"industry": "Industrial Machinery", "sector": "Industrials"}) is True


def test_check_industry_allows_empty():
    """Missing or empty industry/sector should pass (no exclusion matched)."""
    assert _check_industry({}) is True
    assert _check_industry({"industry": "", "sector": ""}) is True


# ── _check_financial_ratios ───────────────────────────────────────

def test_check_financial_ratios_fails_high_debt():
    """Debt/marketCap >= 33% fails."""
    info = {"marketCap": 1_000_000, "totalDebt": 400_000}
    assert _check_financial_ratios(info) is False


def test_check_financial_ratios_fails_boundary_33_percent():
    """Exactly 33% should fail (>= 0.33)."""
    info = {"marketCap": 1_000_000, "totalDebt": 330_000}
    assert _check_financial_ratios(info) is False


def test_check_financial_ratios_passes_clean_balance_sheet():
    """Low debt, low cash, low receivables passes."""
    info = {
        "marketCap": 1_000_000,
        "totalDebt": 100_000,
        "totalCash": 100_000,
        "netReceivables": 100_000,
    }
    assert _check_financial_ratios(info) is True


def test_check_financial_ratios_fails_high_cash():
    """Cash/marketCap >= 33% fails."""
    info = {"marketCap": 1_000_000, "totalCash": 400_000, "totalDebt": 0}
    assert _check_financial_ratios(info) is False


def test_check_financial_ratios_fails_high_receivables():
    """Receivables/marketCap >= 49% fails (relaxed threshold)."""
    info = {"marketCap": 1_000_000, "netReceivables": 500_000, "totalDebt": 0, "totalCash": 0}
    assert _check_financial_ratios(info) is False


def test_check_financial_ratios_allows_receivables_below_49():
    """Receivables at 40% should pass (below relaxed 49% threshold)."""
    info = {"marketCap": 1_000_000, "netReceivables": 400_000, "totalDebt": 0, "totalCash": 0}
    assert _check_financial_ratios(info) is True


def test_check_financial_ratios_zero_market_cap():
    """Zero or missing market cap returns True (can't screen)."""
    assert _check_financial_ratios({"marketCap": 0}) is True
    assert _check_financial_ratios({}) is True


# ── is_compliant_fast ─────────────────────────────────────────────

def test_is_compliant_fast_excludes_banks():
    assert is_compliant_fast("JPM") is False
    assert is_compliant_fast("BAC") is False
    assert is_compliant_fast("WFC") is False


def test_is_compliant_fast_excludes_tobacco():
    assert is_compliant_fast("PM") is False
    assert is_compliant_fast("MO") is False


def test_is_compliant_fast_excludes_gambling():
    assert is_compliant_fast("DKNG") is False
    assert is_compliant_fast("MGM") is False


def test_is_compliant_fast_includes_tech():
    assert is_compliant_fast("AAPL") is True
    assert is_compliant_fast("MSFT") is True
    assert is_compliant_fast("NVDA") is True


def test_is_compliant_fast_includes_amd():
    assert is_compliant_fast("AMD") is True


def test_is_compliant_fast_unknown_ticker_defaults_true():
    """Unknown ticker not in any list or cache should default to compliant."""
    with patch("stockpulse.filters.shariah._SHARIAH_CACHE") as mock_cache:
        mock_cache.exists.return_value = False
        assert is_compliant_fast("ZZZZ_UNKNOWN") is True


def test_is_compliant_fast_uses_cache_excluded():
    """Ticker found in cache excluded list returns False."""
    cache_data = '{"excluded": ["BADSTOCK"], "compliant": ["GOODSTOCK"]}'
    mock_path = MagicMock()
    mock_path.exists.return_value = True
    mock_path.read_text.return_value = cache_data

    with patch("stockpulse.filters.shariah._SHARIAH_CACHE", mock_path):
        assert is_compliant_fast("BADSTOCK") is False


def test_is_compliant_fast_uses_cache_compliant():
    """Ticker found in cache compliant list returns True."""
    cache_data = '{"excluded": ["BADSTOCK"], "compliant": ["GOODSTOCK"]}'
    mock_path = MagicMock()
    mock_path.exists.return_value = True
    mock_path.read_text.return_value = cache_data

    with patch("stockpulse.filters.shariah._SHARIAH_CACHE", mock_path):
        assert is_compliant_fast("GOODSTOCK") is True


# ── screen_ticker ─────────────────────────────────────────────────

def _make_mock_yf(info: dict) -> MagicMock:
    """Create a mock yfinance module with a Ticker that returns the given info."""
    mock_yf = MagicMock()
    mock_ticker_obj = MagicMock()
    mock_ticker_obj.info = info
    mock_yf.Ticker.return_value = mock_ticker_obj
    return mock_yf


def test_screen_ticker_returns_false_for_bank():
    """Bank industry causes screen_ticker to return False."""
    mock_yf = _make_mock_yf({"industry": "Regional Banks", "sector": "Financial Services",
                             "marketCap": 500_000_000_000, "totalDebt": 0})

    with patch.dict(sys.modules, {"yfinance": mock_yf}):
        assert screen_ticker("FAKEBANK") is False


def test_screen_ticker_returns_false_for_high_debt():
    """Clean industry but high debt ratio causes failure."""
    mock_yf = _make_mock_yf({"industry": "Software", "sector": "Technology",
                             "marketCap": 1_000_000, "totalDebt": 500_000})

    with patch.dict(sys.modules, {"yfinance": mock_yf}):
        assert screen_ticker("DEBTY") is False


def test_screen_ticker_returns_true_for_clean_stock():
    """Clean industry and clean financials passes."""
    mock_yf = _make_mock_yf({"industry": "Semiconductors", "sector": "Technology",
                             "marketCap": 1_000_000_000, "totalDebt": 100_000_000,
                             "totalCash": 50_000_000, "netReceivables": 50_000_000})

    with patch.dict(sys.modules, {"yfinance": mock_yf}):
        assert screen_ticker("CLEANSTOCK") is True


def test_screen_ticker_hardcoded_exclude_skips_api():
    """Hardcoded excludes return False without any yfinance call."""
    mock_yf = MagicMock()
    with patch.dict(sys.modules, {"yfinance": mock_yf}):
        result = screen_ticker("JPM")
        assert result is False
        mock_yf.Ticker.assert_not_called()


def test_screen_ticker_hardcoded_include_skips_api():
    """Hardcoded includes return True without any yfinance call."""
    mock_yf = MagicMock()
    with patch.dict(sys.modules, {"yfinance": mock_yf}):
        result = screen_ticker("AAPL")
        assert result is True
        mock_yf.Ticker.assert_not_called()


def test_screen_ticker_yfinance_exception_defaults_compliant():
    """If yfinance throws, screen_ticker defaults to True."""
    mock_yf = MagicMock()
    mock_yf.Ticker.side_effect = Exception("API down")
    with patch.dict(sys.modules, {"yfinance": mock_yf}):
        assert screen_ticker("UNKNOWNTICKER") is True


# ── _is_etf (from advisor) ────────────────────────────────────────

def test_is_etf_known_etfs():
    assert _is_etf("SPY") is True
    assert _is_etf("QQQ") is True
    assert _is_etf("HLAL") is True
    assert _is_etf("SPUS") is True


def test_is_etf_not_etf():
    assert _is_etf("AAPL") is False
    assert _is_etf("NVDA") is False
    assert _is_etf("MSFT") is False


def test_is_etf_case_insensitive():
    """_is_etf uppercases the input, so lowercase should work."""
    assert _is_etf("spy") is True
    assert _is_etf("qqq") is True
    assert _is_etf("aapl") is False
