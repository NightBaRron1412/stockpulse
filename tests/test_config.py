import os
from unittest.mock import patch

def test_settings_loads_defaults():
    with patch.dict(os.environ, {}, clear=False):
        from stockpulse.config import settings
        import importlib
        importlib.reload(settings)
        cfg = settings.get_config()
        assert cfg["cache_ttl_minutes"] == 15
        assert cfg["llm_enabled"] is True
        assert cfg["llm_model"] == "Claude-Sonnet-4.6"
        assert cfg["trading_enabled"] is False
        assert cfg["alerts_telegram"] is False
        assert cfg["alerts_discord"] is False

def test_settings_loads_watchlists():
    from stockpulse.config.settings import load_watchlists
    wl = load_watchlists()
    assert "user" in wl
    assert isinstance(wl["user"], list)
    assert len(wl["user"]) > 0

def test_settings_loads_strategies():
    from stockpulse.config.settings import load_strategies
    strat = load_strategies()
    assert "signals" in strat
    assert "thresholds" in strat
    assert strat["thresholds"]["buy"] == 40
    assert strat["thresholds"]["sell"] == -40
