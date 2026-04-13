import os
from unittest.mock import patch

def test_settings_loads_defaults():
    """Config returns correct types and sensible defaults."""
    from stockpulse.config import settings
    import importlib
    importlib.reload(settings)
    cfg = settings.get_config()
    assert isinstance(cfg["cache_ttl_minutes"], int)
    assert isinstance(cfg["llm_enabled"], bool)
    assert isinstance(cfg["llm_model"], str)
    assert isinstance(cfg["trading_enabled"], bool)
    assert isinstance(cfg["alerts_telegram"], bool)
    assert isinstance(cfg["alerts_discord"], bool)
    assert "outputs_dir" in cfg
    assert "project_root" in cfg

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
