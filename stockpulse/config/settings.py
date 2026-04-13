"""Central configuration loader. Reads .env and YAML config files."""
import os
from pathlib import Path
import yaml
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_DIR = Path(__file__).resolve().parent

load_dotenv(_ROOT / ".env")

def get_config() -> dict:
    return {
        "yahoo_rate_limit": int(os.getenv("YAHOO_RATE_LIMIT", "2000")),
        "cache_ttl_minutes": int(os.getenv("CACHE_TTL_MINUTES", "15")),
        "llm_enabled": os.getenv("LLM_ENABLED", "true").lower() == "true",
        "llm_base_url": os.getenv("LLM_BASE_URL", os.getenv("ANTHROPIC_BASE_URL", "https://llm-api.amd.com/Anthropic")),
        "llm_api_key": os.getenv("LLM_API_KEY") or os.getenv("ANTHROPIC_API_KEY", ""),
        "llm_model": os.getenv("LLM_MODEL", "Claude-Sonnet-4.6"),
        "alerts_telegram": os.getenv("ALERTS_TELEGRAM", "false").lower() == "true",
        "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
        "alerts_discord": os.getenv("ALERTS_DISCORD", "false").lower() == "true",
        "discord_webhook_url": os.getenv("DISCORD_WEBHOOK_URL", ""),
        "trading_enabled": os.getenv("TRADING_ENABLED", "false").lower() == "true",
        "trading_mode": os.getenv("TRADING_MODE", "paper"),
        "finnhub_api_key": os.getenv("FINNHUB_API_KEY", ""),
        "sec_user_agent": os.getenv("SEC_USER_AGENT", "stockpulse user@example.com"),
        "project_root": str(_ROOT),
        "outputs_dir": str(_ROOT / "outputs"),
    }

def load_watchlists() -> dict:
    path = _CONFIG_DIR / "watchlists.yaml"
    with open(path) as f:
        return yaml.safe_load(f)

def save_watchlists(data: dict) -> None:
    path = _CONFIG_DIR / "watchlists.yaml"
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False)

def load_strategies() -> dict:
    path = _CONFIG_DIR / "strategies.yaml"
    with open(path) as f:
        return yaml.safe_load(f)
