"""Setup validation — checks that all dependencies and API keys are configured."""

import sys
import os


def main():
    print("StockPulse Setup Validation")
    print("=" * 40)

    errors = []
    warnings = []

    # Python version
    v = sys.version_info
    ok = v >= (3, 12)
    print(f"\nPython {v.major}.{v.minor}.{v.micro}: {'OK' if ok else 'NEED 3.12+'}")
    if not ok:
        errors.append("Python 3.12+ required")

    # Core dependencies
    print("\nDependencies:")
    deps = [
        ("yfinance", "yfinance"), ("finnhub", "finnhub-python"),
        ("pandas", "pandas"), ("pandas_ta", "pandas-ta"),
        ("anthropic", "anthropic"), ("apscheduler", "apscheduler"),
        ("yaml", "pyyaml"), ("dotenv", "python-dotenv"),
        ("scipy", "scipy"), ("jinja2", "jinja2"),
    ]
    for module, package in deps:
        try:
            __import__(module)
            print(f"  {package}: OK")
        except ImportError:
            print(f"  {package}: MISSING")
            errors.append(f"Missing: pip install {package}")

    # .env file
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    env_exists = os.path.exists(env_path)
    print(f"\n.env file: {'OK' if env_exists else 'MISSING — run: cp .env.example .env'}")
    if not env_exists:
        errors.append("No .env file")

    # Load config
    try:
        from stockpulse.config.settings import get_config
        cfg = get_config()
    except Exception as e:
        errors.append(f"Config load failed: {e}")
        cfg = {}

    # Finnhub API key
    print("\nAPI Keys:")
    fh_key = cfg.get("finnhub_api_key", "") or os.getenv("FINNHUB_API_KEY", "")
    if fh_key:
        try:
            import finnhub
            client = finnhub.Client(api_key=fh_key)
            q = client.quote("AAPL")
            if q.get("c", 0) > 0:
                print(f"  Finnhub: OK (AAPL=${q['c']:.2f})")
            else:
                print("  Finnhub: KEY SET but no data returned")
                warnings.append("Finnhub key may be invalid")
        except Exception as e:
            print(f"  Finnhub: FAILED ({e})")
            errors.append("Finnhub API key not working")
    else:
        print("  Finnhub: NOT SET (required)")
        errors.append("FINNHUB_API_KEY not set — get free key at https://finnhub.io")

    # LLM
    llm_enabled = cfg.get("llm_enabled", False)
    llm_key = cfg.get("llm_api_key", "")
    if llm_enabled and llm_key:
        print(f"  LLM ({cfg.get('llm_model', '?')}): KEY SET (will test on first use)")
    elif llm_enabled:
        print("  LLM: ENABLED but no API key — will use rules-based fallback")
        warnings.append("LLM enabled but no API key")
    else:
        print("  LLM: DISABLED (using rules-based summaries)")

    # Telegram
    if cfg.get("alerts_telegram"):
        if cfg.get("telegram_bot_token") and cfg.get("telegram_chat_id"):
            print("  Telegram: CONFIGURED")
        else:
            print("  Telegram: ENABLED but missing token/chat_id")
            warnings.append("Telegram enabled but not fully configured")
    else:
        print("  Telegram: OFF")

    # Discord
    if cfg.get("alerts_discord"):
        if cfg.get("discord_webhook_url"):
            print("  Discord: CONFIGURED")
        else:
            print("  Discord: ENABLED but missing webhook URL")
            warnings.append("Discord enabled but not configured")
    else:
        print("  Discord: OFF")

    # SEC
    sec_agent = cfg.get("sec_user_agent", "")
    if "example" in sec_agent or not sec_agent:
        print(f"  SEC EDGAR: DEFAULT (update SEC_USER_AGENT in .env with your email)")
        warnings.append("SEC_USER_AGENT should be updated with your email")
    else:
        print(f"  SEC EDGAR: OK ({sec_agent})")

    # Output dirs
    print("\nDirectories:")
    for d in ["outputs/reports", "outputs/json", "outputs/logs"]:
        path = os.path.join(os.path.dirname(__file__), "..", "..", d)
        exists = os.path.isdir(path)
        if not exists:
            os.makedirs(path, exist_ok=True)
        print(f"  {d}: {'OK' if exists else 'CREATED'}")

    # Summary
    print(f"\n{'=' * 40}")
    if errors:
        print(f"ERRORS ({len(errors)}):")
        for e in errors:
            print(f"  - {e}")
    if warnings:
        print(f"WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  - {w}")
    if not errors:
        print("Setup is valid! Run 'make run' or 'python run.py scan'")
    else:
        print("\nFix the errors above before running StockPulse.")

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
