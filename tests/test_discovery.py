"""Tests for watchlist auto-discovery and cleanup."""
from unittest.mock import patch, MagicMock, call


def test_discovery_adds_watchlist_tickers():
    """Tickers crossing WATCHLIST threshold should be discovered."""
    from stockpulse.scanners.market_scanner import _update_discovered

    ranked = [
        {"ticker": "NEW1", "action": "WATCHLIST", "composite_score": 35, "confidence": 35, "thesis": "test",
         "technical_summary": "", "catalyst_summary": "", "invalidation": ""},
    ]
    mock_wl = {"user": ["AAPL"], "discovered": [], "priority": []}

    with patch("stockpulse.scanners.market_scanner.load_watchlists", return_value=mock_wl), \
         patch("stockpulse.scanners.market_scanner.save_watchlists") as mock_save, \
         patch("stockpulse.scanners.market_scanner.load_strategies", return_value={"thresholds": {"watchlist": 32}, "risk": {"earnings_blackout_days": 3}}), \
         patch("stockpulse.scanners.market_scanner.dispatch_alert"), \
         patch("stockpulse.scanners.market_scanner._cleanup_discovered"):
        _update_discovered(ranked)
        mock_save.assert_called_once()
        saved = mock_save.call_args[0][0]
        assert "NEW1" in saved["discovered"]


def test_discovery_skips_user_tickers():
    """User tickers should not be added to discovered."""
    from stockpulse.scanners.market_scanner import _update_discovered

    ranked = [
        {"ticker": "AAPL", "action": "WATCHLIST", "composite_score": 35, "confidence": 35, "thesis": "test",
         "technical_summary": "", "catalyst_summary": "", "invalidation": ""},
    ]
    mock_wl = {"user": ["AAPL"], "discovered": [], "priority": []}

    with patch("stockpulse.scanners.market_scanner.load_watchlists", return_value=mock_wl), \
         patch("stockpulse.scanners.market_scanner.save_watchlists") as mock_save, \
         patch("stockpulse.scanners.market_scanner.load_strategies", return_value={"thresholds": {"watchlist": 32}, "risk": {"earnings_blackout_days": 3}}), \
         patch("stockpulse.scanners.market_scanner.dispatch_alert"), \
         patch("stockpulse.scanners.market_scanner._cleanup_discovered"):
        _update_discovered(ranked)
        # Should not save because AAPL is already in user list
        mock_save.assert_not_called()


def test_discovery_skips_already_discovered():
    """Tickers already in discovered list should not be re-added or trigger re-save."""
    from stockpulse.scanners.market_scanner import _update_discovered

    ranked = [
        {"ticker": "NVDA", "action": "BUY", "composite_score": 70, "confidence": 65, "thesis": "momentum",
         "technical_summary": "", "catalyst_summary": "", "invalidation": ""},
    ]
    mock_wl = {"user": [], "discovered": ["NVDA"], "priority": []}

    with patch("stockpulse.scanners.market_scanner.load_watchlists", return_value=mock_wl), \
         patch("stockpulse.scanners.market_scanner.save_watchlists") as mock_save, \
         patch("stockpulse.scanners.market_scanner.load_strategies", return_value={"thresholds": {"watchlist": 32}, "risk": {}}), \
         patch("stockpulse.scanners.market_scanner.dispatch_alert"), \
         patch("stockpulse.scanners.market_scanner._cleanup_discovered"):
        _update_discovered(ranked)
        # NVDA is already discovered — save_watchlists must NOT be called for new discoveries
        mock_save.assert_not_called()


def test_discovery_below_threshold_not_added():
    """Tickers with HOLD action and score below threshold should not be discovered."""
    from stockpulse.scanners.market_scanner import _update_discovered

    ranked = [
        {"ticker": "WEAK", "action": "HOLD", "composite_score": 10, "confidence": 10, "thesis": "flat",
         "technical_summary": "", "catalyst_summary": "", "invalidation": ""},
    ]
    mock_wl = {"user": [], "discovered": [], "priority": []}

    with patch("stockpulse.scanners.market_scanner.load_watchlists", return_value=mock_wl), \
         patch("stockpulse.scanners.market_scanner.save_watchlists") as mock_save, \
         patch("stockpulse.scanners.market_scanner.load_strategies", return_value={"thresholds": {"watchlist": 32}, "risk": {}}), \
         patch("stockpulse.scanners.market_scanner.dispatch_alert"), \
         patch("stockpulse.scanners.market_scanner._cleanup_discovered"):
        _update_discovered(ranked)
        mock_save.assert_not_called()


def test_discovery_dispatches_alert_for_new_ticker():
    """A newly discovered ticker should trigger a dispatch_alert call."""
    from stockpulse.scanners.market_scanner import _update_discovered

    ranked = [
        {"ticker": "FRESH", "action": "BUY", "composite_score": 60, "confidence": 55, "thesis": "breakout",
         "technical_summary": "TA summary", "catalyst_summary": "news", "invalidation": "stop < 50"},
    ]
    mock_wl = {"user": [], "discovered": [], "priority": []}

    with patch("stockpulse.scanners.market_scanner.load_watchlists", return_value=mock_wl), \
         patch("stockpulse.scanners.market_scanner.save_watchlists"), \
         patch("stockpulse.scanners.market_scanner.load_strategies", return_value={"thresholds": {"watchlist": 32}, "risk": {}}), \
         patch("stockpulse.scanners.market_scanner.dispatch_alert") as mock_dispatch, \
         patch("stockpulse.scanners.market_scanner._cleanup_discovered"):
        _update_discovered(ranked)
        mock_dispatch.assert_called_once()
        alert_arg = mock_dispatch.call_args[0][0]
        assert alert_arg["ticker"] == "FRESH"
        assert alert_arg["type"] == "discovery"


def test_discovery_multiple_new_tickers():
    """Multiple qualifying tickers should all be discovered and each get an alert."""
    from stockpulse.scanners.market_scanner import _update_discovered

    ranked = [
        {"ticker": "T1", "action": "WATCHLIST", "composite_score": 40, "confidence": 38, "thesis": "ok",
         "technical_summary": "", "catalyst_summary": "", "invalidation": ""},
        {"ticker": "T2", "action": "BUY", "composite_score": 65, "confidence": 60, "thesis": "strong",
         "technical_summary": "", "catalyst_summary": "", "invalidation": ""},
    ]
    mock_wl = {"user": [], "discovered": [], "priority": []}

    with patch("stockpulse.scanners.market_scanner.load_watchlists", return_value=mock_wl), \
         patch("stockpulse.scanners.market_scanner.save_watchlists") as mock_save, \
         patch("stockpulse.scanners.market_scanner.load_strategies", return_value={"thresholds": {"watchlist": 32}, "risk": {}}), \
         patch("stockpulse.scanners.market_scanner.dispatch_alert") as mock_dispatch, \
         patch("stockpulse.scanners.market_scanner._cleanup_discovered"):
        _update_discovered(ranked)
        mock_save.assert_called_once()
        saved = mock_save.call_args[0][0]
        assert "T1" in saved["discovered"]
        assert "T2" in saved["discovered"]
        assert mock_dispatch.call_count == 2
