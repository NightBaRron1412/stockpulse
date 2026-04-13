# StockPulse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fully local, zero-subscription stock trading research and alert system that scans S&P 500 + user watchlist, generates buy/sell/hold recommendations with confidence scores, sends alerts via Telegram/Discord, produces daily markdown/JSON reports, and supports backtesting.

**Architecture:** Lumibot-centric pipeline. yfinance for free market data. EdgarTools for SEC filings. pandas-ta for technicals. APScheduler for scheduling. AMD Claude API (Sonnet 4.6) for LLM summarization with rules-based fallback. Modular design with clear boundaries between data, signals, research, alerts, and reports.

**Tech Stack:** Python 3.12, uv, Lumibot, yfinance, edgartools, pandas-ta, anthropic SDK, APScheduler, PyYAML, Jinja2, python-dotenv

**Spec:** `docs/superpowers/specs/2026-04-13-stockpulse-design.md`

**Note on cache serialization:** The disk cache uses pickle for serializing pandas DataFrames. This is safe because the cache only stores data we generate ourselves — it never deserializes untrusted external input. JSON cannot efficiently serialize DataFrames with DatetimeIndex.

---

## Phase 1: Project Scaffolding & Config

### Task 1: Initialize Project and Dependencies

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `stockpulse/__init__.py`

- [ ] **Step 1: Create project directory structure**

```bash
cd /home/ashetaia/personal/stockpulse
mkdir -p stockpulse/{config,data,scanners,signals,research,sec,alerts,reports,strategies,backtests/results,llm,scheduler}
mkdir -p outputs/{reports,json,logs}
mkdir -p tests
touch stockpulse/__init__.py
touch stockpulse/{config,data,scanners,signals,research,sec,alerts,reports,strategies,backtests,llm,scheduler}/__init__.py
touch tests/__init__.py
```

- [ ] **Step 2: Create pyproject.toml**

```toml
[project]
name = "stockpulse"
version = "0.1.0"
description = "Local stock research and alert system"
requires-python = ">=3.12"
dependencies = [
    "lumibot>=3.0",
    "yfinance>=0.2",
    "edgartools>=3.0",
    "pandas>=2.0",
    "pandas-ta>=0.3",
    "anthropic>=0.40",
    "apscheduler>=3.10,<4.0",
    "pyyaml>=6.0",
    "python-dotenv>=1.0",
    "jinja2>=3.1",
    "requests>=2.31",
    "pytz>=2024.1",
    "python-telegram-bot>=21.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-mock>=3.14"]

[build-system]
requires = ["setuptools>=75.0"]
build-backend = "setuptools.backends._legacy:_Backend"
```

- [ ] **Step 3: Create .env.example**

```env
# Data
YAHOO_RATE_LIMIT=2000
CACHE_TTL_MINUTES=15

# LLM (AMD Claude API)
LLM_ENABLED=true
LLM_BASE_URL=https://llm-api.amd.com/Anthropic
LLM_API_KEY=
LLM_MODEL=Claude-Sonnet-4.6

# Alerts
ALERTS_TELEGRAM=false
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
ALERTS_DISCORD=false
DISCORD_WEBHOOK_URL=

# Trading (PAPER MODE BY DEFAULT)
TRADING_ENABLED=false
TRADING_MODE=paper

# SEC
SEC_USER_AGENT=stockpulse amir.shetaia@amd.com
```

- [ ] **Step 4: Create .gitignore**

```
__pycache__/
*.pyc
.env
.venv/
outputs/
backtests/results/
*.egg-info/
.cache/
```

- [ ] **Step 5: Install dependencies**

```bash
cd /home/ashetaia/personal/stockpulse
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

- [ ] **Step 6: Verify installation**

```bash
source .venv/bin/activate
python -c "import yfinance; import pandas_ta; import edgartools; import anthropic; import apscheduler; print('All imports OK')"
```
Expected: `All imports OK`

- [ ] **Step 7: Initialize git and commit**

```bash
cd /home/ashetaia/personal/stockpulse
git init
cp .env.example .env
git add pyproject.toml .env.example .gitignore stockpulse/ tests/
git commit -m "feat: initialize stockpulse project scaffolding"
```

---

### Task 2: Configuration System

**Files:**
- Create: `stockpulse/config/settings.py`
- Create: `stockpulse/config/watchlists.yaml`
- Create: `stockpulse/config/strategies.yaml`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write test for settings loading**

```python
# tests/test_config.py
import os
from unittest.mock import patch


def test_settings_loads_defaults():
    """Settings should have sensible defaults even without .env."""
    with patch.dict(os.environ, {}, clear=False):
        # Re-import to pick up patched env
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/ashetaia/personal/stockpulse
source .venv/bin/activate
python -m pytest tests/test_config.py -v
```
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create strategies.yaml**

```yaml
# stockpulse/config/strategies.yaml
signals:
  rsi:
    period: 14
    oversold: 30
    overbought: 70
    weight: 0.15
  macd:
    fast: 12
    slow: 26
    signal: 9
    weight: 0.15
  moving_averages:
    periods: [20, 50, 200]
    weight: 0.15
  volume:
    spike_threshold: 2.0
    lookback: 20
    weight: 0.10
  breakout:
    lookback_days: 252
    weight: 0.10
  gap:
    threshold_pct: 2.0
    weight: 0.05
  adx:
    period: 14
    trend_threshold: 25
    weight: 0.10
  earnings:
    proximity_days: 14
    weight: 0.05
  sec_filing:
    lookback_days: 30
    weight: 0.10
  news_sentiment:
    weight: 0.05

thresholds:
  buy: 40
  sell: -40
  exit: 10
  confidence_min: 30

scheduling:
  morning_scan: "09:00"
  intraday_interval_minutes: 30
  eod_recap: "16:30"
  sec_scan_interval_hours: 2
  timezone: "US/Eastern"

backtesting:
  max_positions: 10
  position_size: "equal_weight"
  initial_cash: 100000
```

- [ ] **Step 4: Create watchlists.yaml**

```yaml
# stockpulse/config/watchlists.yaml
user:
  - AAPL
  - MSFT
  - NVDA
  - AMD
  - GOOGL
  - AMZN
  - TSLA
  - META

discovered: []

priority: []
```

- [ ] **Step 5: Create settings.py**

```python
# stockpulse/config/settings.py
"""Central configuration loader. Reads .env and YAML config files."""

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent.parent  # stockpulse project root
_CONFIG_DIR = Path(__file__).resolve().parent

load_dotenv(_ROOT / ".env")


def get_config() -> dict:
    """Return flat config dict from environment with defaults."""
    return {
        "yahoo_rate_limit": int(os.getenv("YAHOO_RATE_LIMIT", "2000")),
        "cache_ttl_minutes": int(os.getenv("CACHE_TTL_MINUTES", "15")),
        "llm_enabled": os.getenv("LLM_ENABLED", "true").lower() == "true",
        "llm_base_url": os.getenv(
            "LLM_BASE_URL",
            os.getenv("ANTHROPIC_BASE_URL", "https://llm-api.amd.com/Anthropic"),
        ),
        "llm_api_key": os.getenv("LLM_API_KEY") or os.getenv("ANTHROPIC_API_KEY", ""),
        "llm_model": os.getenv("LLM_MODEL", "Claude-Sonnet-4.6"),
        "alerts_telegram": os.getenv("ALERTS_TELEGRAM", "false").lower() == "true",
        "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
        "alerts_discord": os.getenv("ALERTS_DISCORD", "false").lower() == "true",
        "discord_webhook_url": os.getenv("DISCORD_WEBHOOK_URL", ""),
        "trading_enabled": os.getenv("TRADING_ENABLED", "false").lower() == "true",
        "trading_mode": os.getenv("TRADING_MODE", "paper"),
        "sec_user_agent": os.getenv(
            "SEC_USER_AGENT", "stockpulse user@example.com"
        ),
        "project_root": str(_ROOT),
        "outputs_dir": str(_ROOT / "outputs"),
    }


def load_watchlists() -> dict:
    """Load watchlists from YAML config."""
    path = _CONFIG_DIR / "watchlists.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def save_watchlists(data: dict) -> None:
    """Write watchlists back to YAML."""
    path = _CONFIG_DIR / "watchlists.yaml"
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False)


def load_strategies() -> dict:
    """Load strategy parameters from YAML config."""
    path = _CONFIG_DIR / "strategies.yaml"
    with open(path) as f:
        return yaml.safe_load(f)
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
python -m pytest tests/test_config.py -v
```
Expected: 3 passed

- [ ] **Step 7: Commit**

```bash
git add stockpulse/config/ tests/test_config.py
git commit -m "feat: add configuration system with settings, watchlists, strategies"
```

---

## Phase 2: Data Layer (tasks can run in parallel)

### Task 3: Stock Universe Provider

**Files:**
- Create: `stockpulse/data/universe.py`
- Create: `tests/test_universe.py`

- [ ] **Step 1: Write test for universe**

```python
# tests/test_universe.py
from stockpulse.data.universe import get_sp500_tickers, get_full_universe


def test_get_sp500_tickers_returns_list():
    tickers = get_sp500_tickers()
    assert isinstance(tickers, list)
    assert len(tickers) > 400  # S&P 500 should have ~500
    assert "AAPL" in tickers
    assert "MSFT" in tickers


def test_get_full_universe_includes_user_watchlist():
    universe = get_full_universe()
    assert "AMD" in universe  # From user watchlist
    # Should be deduplicated
    assert len(universe) == len(set(universe))
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_universe.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement universe.py**

```python
# stockpulse/data/universe.py
"""Stock universe management — S&P 500 + user watchlist."""

import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

from stockpulse.config.settings import load_watchlists

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "outputs" / ".cache"
_SP500_CACHE = _CACHE_DIR / "sp500.csv"
_CACHE_MAX_AGE = timedelta(days=7)


def get_sp500_tickers() -> list[str]:
    """Fetch S&P 500 tickers from Wikipedia, cached locally for 7 days."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if _SP500_CACHE.exists():
        age = datetime.now() - datetime.fromtimestamp(_SP500_CACHE.stat().st_mtime)
        if age < _CACHE_MAX_AGE:
            df = pd.read_csv(_SP500_CACHE)
            return df["Symbol"].tolist()

    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        tables = pd.read_html(url)
        df = tables[0]
        # Clean up tickers (BRK.B -> BRK-B for yfinance)
        tickers = df["Symbol"].str.replace(".", "-", regex=False).tolist()
        # Cache it
        pd.DataFrame({"Symbol": tickers}).to_csv(_SP500_CACHE, index=False)
        logger.info("Fetched %d S&P 500 tickers from Wikipedia", len(tickers))
        return tickers
    except Exception:
        logger.exception("Failed to fetch S&P 500 list from Wikipedia")
        if _SP500_CACHE.exists():
            df = pd.read_csv(_SP500_CACHE)
            return df["Symbol"].tolist()
        return []


def get_user_watchlist() -> list[str]:
    """Return user-defined watchlist tickers."""
    wl = load_watchlists()
    return wl.get("user", [])


def get_full_universe() -> list[str]:
    """Return deduplicated S&P 500 + user watchlist."""
    sp500 = get_sp500_tickers()
    user = get_user_watchlist()
    combined = list(dict.fromkeys(sp500 + user))  # preserves order, deduplicates
    return combined
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_universe.py -v
```
Expected: 2 passed (requires internet for first run)

- [ ] **Step 5: Commit**

```bash
git add stockpulse/data/universe.py tests/test_universe.py
git commit -m "feat: add S&P 500 + user watchlist universe provider"
```

---

### Task 4: Market Data Provider and Cache

**Files:**
- Create: `stockpulse/data/provider.py`
- Create: `stockpulse/data/cache.py`
- Create: `tests/test_provider.py`

- [ ] **Step 1: Write test for data provider**

```python
# tests/test_provider.py
import pandas as pd
from stockpulse.data.provider import get_price_history, get_current_quote, get_earnings_dates


def test_get_price_history_returns_dataframe():
    df = get_price_history("AAPL", period="1mo")
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 10
    assert "Close" in df.columns
    assert "Volume" in df.columns


def test_get_current_quote_returns_dict():
    quote = get_current_quote("AAPL")
    assert isinstance(quote, dict)
    assert "price" in quote
    assert quote["price"] > 0


def test_get_earnings_dates_returns_list():
    result = get_earnings_dates("AAPL")
    # May be empty but should be a list
    assert isinstance(result, list)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_provider.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement cache.py**

Uses pickle for DataFrame serialization. This is safe because the cache only stores data we generate — never untrusted external input. JSON cannot efficiently handle pandas DataFrames with DatetimeIndex.

```python
# stockpulse/data/cache.py
"""Simple TTL-based disk cache for API responses.

Security note: Uses pickle for DataFrame serialization. This cache only stores
data generated by our own code (yfinance responses, computed signals). It never
deserializes untrusted external input. JSON is not viable because pandas
DataFrames with DatetimeIndex cannot be round-tripped through JSON efficiently.
"""

import hashlib
import logging
import pickle
from datetime import datetime, timedelta
from pathlib import Path

from stockpulse.config.settings import get_config

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "outputs" / ".cache" / "data"


def _cache_path(key: str) -> Path:
    hashed = hashlib.md5(key.encode()).hexdigest()
    return _CACHE_DIR / f"{hashed}.pkl"


def get_cached(key: str):
    """Return cached value if exists and not expired, else None."""
    path = _cache_path(key)
    if not path.exists():
        return None

    try:
        with open(path, "rb") as f:
            entry = pickle.load(f)  # noqa: S301 — internal cache only, see module docstring
        ttl = timedelta(minutes=get_config()["cache_ttl_minutes"])
        if datetime.now() - entry["time"] < ttl:
            return entry["data"]
    except Exception:
        logger.debug("Cache miss (corrupt) for %s", key)
    return None


def set_cached(key: str, data) -> None:
    """Store value in cache."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(key)
    with open(path, "wb") as f:
        pickle.dump({"time": datetime.now(), "data": data}, f)
```

- [ ] **Step 4: Implement provider.py**

```python
# stockpulse/data/provider.py
"""Unified market data provider using yfinance."""

import logging

import pandas as pd
import yfinance as yf

from stockpulse.data.cache import get_cached, set_cached

logger = logging.getLogger(__name__)


def get_price_history(
    ticker: str, period: str = "6mo", interval: str = "1d"
) -> pd.DataFrame:
    """Fetch OHLCV price history for a ticker."""
    cache_key = f"price_{ticker}_{period}_{interval}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        t = yf.Ticker(ticker)
        df = t.history(period=period, interval=interval)
        if df.empty:
            logger.warning("No price data for %s", ticker)
            return pd.DataFrame()
        set_cached(cache_key, df)
        return df
    except Exception:
        logger.exception("Failed to fetch price data for %s", ticker)
        return pd.DataFrame()


def get_current_quote(ticker: str) -> dict:
    """Get current price and key quote data."""
    cache_key = f"quote_{ticker}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        t = yf.Ticker(ticker)
        info = t.fast_info
        quote = {
            "price": float(info.last_price) if hasattr(info, "last_price") else 0.0,
            "previous_close": float(info.previous_close) if hasattr(info, "previous_close") else 0.0,
            "market_cap": float(info.market_cap) if hasattr(info, "market_cap") else 0.0,
            "fifty_day_average": float(info.fifty_day_average) if hasattr(info, "fifty_day_average") else 0.0,
            "two_hundred_day_average": float(info.two_hundred_day_average) if hasattr(info, "two_hundred_day_average") else 0.0,
        }
        set_cached(cache_key, quote)
        return quote
    except Exception:
        logger.exception("Failed to fetch quote for %s", ticker)
        return {"price": 0.0, "previous_close": 0.0, "market_cap": 0.0}


def get_earnings_dates(ticker: str) -> list[dict]:
    """Get upcoming earnings dates for a ticker."""
    cache_key = f"earnings_{ticker}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        t = yf.Ticker(ticker)
        cal = t.calendar
        if cal is None or (isinstance(cal, pd.DataFrame) and cal.empty):
            return []

        results = []
        if isinstance(cal, dict):
            if "Earnings Date" in cal:
                dates = cal["Earnings Date"]
                if not isinstance(dates, list):
                    dates = [dates]
                for d in dates:
                    results.append({
                        "date": str(d),
                        "days_away": (pd.Timestamp(d) - pd.Timestamp.now()).days,
                    })
        set_cached(cache_key, results)
        return results
    except Exception:
        logger.debug("No earnings data for %s", ticker)
        return []


def get_news(ticker: str) -> list[dict]:
    """Get recent news headlines for a ticker."""
    cache_key = f"news_{ticker}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        t = yf.Ticker(ticker)
        news = t.news or []
        results = []
        for item in news[:10]:
            results.append({
                "title": item.get("title", ""),
                "publisher": item.get("publisher", ""),
                "link": item.get("link", ""),
                "published": item.get("providerPublishTime", 0),
            })
        set_cached(cache_key, results)
        return results
    except Exception:
        logger.debug("No news for %s", ticker)
        return []


def bulk_download(tickers: list[str], period: str = "6mo") -> dict[str, pd.DataFrame]:
    """Download price data for multiple tickers efficiently."""
    cache_key = f"bulk_{'_'.join(sorted(tickers[:20]))}_{period}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        data = yf.download(
            tickers, period=period, group_by="ticker", threads=True, progress=False
        )
        result = {}
        if len(tickers) == 1:
            result[tickers[0]] = data
        else:
            for ticker in tickers:
                try:
                    df = data[ticker].dropna(how="all")
                    if not df.empty:
                        result[ticker] = df
                except (KeyError, AttributeError):
                    continue
        set_cached(cache_key, result)
        return result
    except Exception:
        logger.exception("Bulk download failed")
        return {}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_provider.py -v
```
Expected: 3 passed (requires internet)

- [ ] **Step 6: Commit**

```bash
git add stockpulse/data/ tests/test_provider.py
git commit -m "feat: add market data provider with yfinance and TTL cache"
```

---

## Phase 3: Signal Engine (tasks can run in parallel after Phase 2)

### Task 5: Technical Signal Generators

**Files:**
- Create: `stockpulse/signals/technical.py`
- Create: `tests/test_signals.py`

- [ ] **Step 1: Write tests for technical signals**

```python
# tests/test_signals.py
import pandas as pd
import numpy as np
from stockpulse.signals.technical import (
    calc_rsi_signal,
    calc_macd_signal,
    calc_ma_signal,
    calc_volume_signal,
    calc_breakout_signal,
    calc_gap_signal,
    calc_adx_signal,
)


def _make_price_df(n=100, base=100.0, trend=0.1):
    """Create synthetic price data for testing."""
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    close = base + np.cumsum(np.random.randn(n) * 2 + trend)
    close = np.maximum(close, 1.0)  # no negative prices
    return pd.DataFrame({
        "Open": close * 0.99,
        "High": close * 1.02,
        "Low": close * 0.98,
        "Close": close,
        "Volume": np.random.randint(1_000_000, 10_000_000, n),
    }, index=dates)


def test_rsi_signal_returns_bounded_score():
    df = _make_price_df()
    score = calc_rsi_signal(df)
    assert -100 <= score <= 100


def test_macd_signal_returns_bounded_score():
    df = _make_price_df()
    score = calc_macd_signal(df)
    assert -100 <= score <= 100


def test_ma_signal_returns_bounded_score():
    df = _make_price_df()
    score = calc_ma_signal(df)
    assert -100 <= score <= 100


def test_volume_signal_returns_bounded_score():
    df = _make_price_df()
    score = calc_volume_signal(df)
    assert -100 <= score <= 100


def test_breakout_signal_returns_bounded_score():
    df = _make_price_df(n=260)  # need 252 days
    score = calc_breakout_signal(df)
    assert -100 <= score <= 100


def test_gap_signal_returns_bounded_score():
    df = _make_price_df()
    score = calc_gap_signal(df)
    assert -100 <= score <= 100


def test_adx_signal_returns_bounded_score():
    df = _make_price_df()
    score = calc_adx_signal(df)
    assert -100 <= score <= 100
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_signals.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement technical.py**

```python
# stockpulse/signals/technical.py
"""Technical indicator signal generators.

Each function takes a price DataFrame (OHLCV) and returns a score from -100 to +100.
Positive = bullish, negative = bearish.
"""

import pandas as pd
import pandas_ta as ta

from stockpulse.config.settings import load_strategies


def _clamp(value: float, lo: float = -100.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _get_signal_config(name: str) -> dict:
    strat = load_strategies()
    return strat.get("signals", {}).get(name, {})


def calc_rsi_signal(df: pd.DataFrame) -> float:
    """RSI signal: <30 bullish, >70 bearish, linear interpolation between."""
    cfg = _get_signal_config("rsi")
    period = cfg.get("period", 14)
    oversold = cfg.get("oversold", 30)
    overbought = cfg.get("overbought", 70)

    rsi = ta.rsi(df["Close"], length=period)
    if rsi is None or rsi.dropna().empty:
        return 0.0

    current_rsi = float(rsi.iloc[-1])
    midpoint = (oversold + overbought) / 2
    half_range = (overbought - oversold) / 2

    # Linear scale: oversold -> +100, overbought -> -100
    score = -((current_rsi - midpoint) / half_range) * 100
    return _clamp(score)


def calc_macd_signal(df: pd.DataFrame) -> float:
    """MACD signal: bullish crossover positive, histogram momentum."""
    cfg = _get_signal_config("macd")
    fast = cfg.get("fast", 12)
    slow = cfg.get("slow", 26)
    signal = cfg.get("signal", 9)

    macd_df = ta.macd(df["Close"], fast=fast, slow=slow, signal=signal)
    if macd_df is None or macd_df.dropna().empty:
        return 0.0

    hist_col = f"MACDh_{fast}_{slow}_{signal}"

    if hist_col not in macd_df.columns:
        return 0.0

    hist = macd_df[hist_col].dropna()
    if len(hist) < 2:
        return 0.0

    current_hist = float(hist.iloc[-1])
    prev_hist = float(hist.iloc[-2])

    # Histogram direction and magnitude
    # Normalize by typical histogram range (use std of last 50 bars)
    std = float(hist.tail(50).std()) or 1.0
    score = (current_hist / std) * 40  # scale so 1 std ~ 40 points

    # Bonus for crossover
    if prev_hist < 0 and current_hist > 0:
        score += 30  # bullish crossover
    elif prev_hist > 0 and current_hist < 0:
        score -= 30  # bearish crossover

    return _clamp(score)


def calc_ma_signal(df: pd.DataFrame) -> float:
    """Moving average signal: price vs 20/50/200 SMA + cross detection."""
    cfg = _get_signal_config("moving_averages")
    periods = cfg.get("periods", [20, 50, 200])

    close = df["Close"]
    current_price = float(close.iloc[-1])

    score = 0.0
    smas = {}
    for p in periods:
        sma = ta.sma(close, length=p)
        if sma is not None and not sma.dropna().empty:
            smas[p] = float(sma.iloc[-1])

    # Price above/below each SMA
    for p, sma_val in smas.items():
        if current_price > sma_val:
            score += 20  # above SMA is bullish
        else:
            score -= 20  # below SMA is bearish

    # Golden cross / death cross (50 vs 200)
    if 50 in smas and 200 in smas:
        sma50 = ta.sma(close, length=50)
        sma200 = ta.sma(close, length=200)
        if sma50 is not None and sma200 is not None and len(sma50.dropna()) > 1 and len(sma200.dropna()) > 1:
            curr_50 = float(sma50.iloc[-1])
            prev_50 = float(sma50.iloc[-2])
            curr_200 = float(sma200.iloc[-1])
            prev_200 = float(sma200.iloc[-2])
            if prev_50 <= prev_200 and curr_50 > curr_200:
                score += 30  # golden cross
            elif prev_50 >= prev_200 and curr_50 < curr_200:
                score -= 30  # death cross

    return _clamp(score)


def calc_volume_signal(df: pd.DataFrame) -> float:
    """Volume spike signal: current volume vs 20-day average."""
    cfg = _get_signal_config("volume")
    lookback = cfg.get("lookback", 20)
    spike_threshold = cfg.get("spike_threshold", 2.0)

    if len(df) < lookback + 1:
        return 0.0

    current_vol = float(df["Volume"].iloc[-1])
    avg_vol = float(df["Volume"].iloc[-lookback - 1 : -1].mean())

    if avg_vol == 0:
        return 0.0

    ratio = current_vol / avg_vol

    if ratio < 1.0:
        return 0.0  # below-average volume is neutral, not bearish

    # Price direction determines if volume spike is bullish or bearish
    price_change = float(df["Close"].iloc[-1]) - float(df["Close"].iloc[-2])

    if ratio >= spike_threshold:
        magnitude = min((ratio - 1.0) * 30, 100.0)
        return _clamp(magnitude if price_change > 0 else -magnitude)

    return 0.0


def calc_breakout_signal(df: pd.DataFrame) -> float:
    """Breakout signal: 52-week high/low breaks."""
    cfg = _get_signal_config("breakout")
    lookback = cfg.get("lookback_days", 252)

    if len(df) < lookback:
        lookback = len(df) - 1
    if lookback < 20:
        return 0.0

    current_price = float(df["Close"].iloc[-1])
    high_52w = float(df["High"].iloc[-lookback:].max())
    low_52w = float(df["Low"].iloc[-lookback:].min())
    price_range = high_52w - low_52w

    if price_range == 0:
        return 0.0

    # Where price sits in the 52-week range: 0.0 = low, 1.0 = high
    position = (current_price - low_52w) / price_range

    # Near 52-week high (>95%) = breakout bullish
    if position > 0.95:
        return _clamp(80.0)
    # Near 52-week low (<5%) = breakdown bearish
    elif position < 0.05:
        return _clamp(-80.0)
    else:
        # Linear scale from midpoint
        return _clamp((position - 0.5) * 100)


def calc_gap_signal(df: pd.DataFrame) -> float:
    """Gap signal: gap up/down >threshold from prior close."""
    cfg = _get_signal_config("gap")
    threshold_pct = cfg.get("threshold_pct", 2.0)

    if len(df) < 2:
        return 0.0

    current_open = float(df["Open"].iloc[-1])
    prev_close = float(df["Close"].iloc[-2])

    if prev_close == 0:
        return 0.0

    gap_pct = ((current_open - prev_close) / prev_close) * 100

    if abs(gap_pct) < threshold_pct:
        return 0.0

    # Cap at ~5x threshold for max score
    score = (gap_pct / threshold_pct) * 30
    return _clamp(score)


def calc_adx_signal(df: pd.DataFrame) -> float:
    """Trend strength signal: ADX >25 = trending, direction from +DI/-DI."""
    cfg = _get_signal_config("adx")
    period = cfg.get("period", 14)
    trend_threshold = cfg.get("trend_threshold", 25)

    adx_df = ta.adx(df["High"], df["Low"], df["Close"], length=period)
    if adx_df is None or adx_df.dropna().empty:
        return 0.0

    adx_col = f"ADX_{period}"
    dmp_col = f"DMP_{period}"
    dmn_col = f"DMN_{period}"

    if adx_col not in adx_df.columns:
        return 0.0

    adx_val = float(adx_df[adx_col].iloc[-1])

    if adx_val < trend_threshold:
        return 0.0  # no trend = neutral

    plus_di = float(adx_df[dmp_col].iloc[-1]) if dmp_col in adx_df.columns else 0
    minus_di = float(adx_df[dmn_col].iloc[-1]) if dmn_col in adx_df.columns else 0

    # Direction from DI
    direction = 1.0 if plus_di > minus_di else -1.0
    # Strength from ADX magnitude (25-50 range -> 30-80 score)
    strength = min((adx_val - trend_threshold) * 2, 80.0)

    return _clamp(direction * strength)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_signals.py -v
```
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add stockpulse/signals/technical.py tests/test_signals.py
git commit -m "feat: add technical signal generators (RSI, MACD, MA, volume, breakout, gap, ADX)"
```

---

### Task 6: SEC/Fundamental Signal Generators

**Files:**
- Create: `stockpulse/sec/filings.py`
- Create: `stockpulse/sec/insider.py`
- Create: `stockpulse/signals/fundamental.py`
- Create: `tests/test_fundamental.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_fundamental.py
from stockpulse.signals.fundamental import (
    calc_earnings_signal,
    calc_sec_filing_signal,
    calc_news_sentiment_signal,
)


def test_earnings_signal_returns_bounded_score():
    score = calc_earnings_signal("AAPL")
    assert -100 <= score <= 100


def test_sec_filing_signal_returns_bounded_score():
    score = calc_sec_filing_signal("AAPL")
    assert -100 <= score <= 100


def test_news_sentiment_signal_returns_bounded_score():
    score = calc_news_sentiment_signal("AAPL")
    assert -100 <= score <= 100
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_fundamental.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement sec/filings.py**

```python
# stockpulse/sec/filings.py
"""EdgarTools wrapper for SEC filing data."""

import logging
import os
from datetime import datetime, timedelta

from stockpulse.config.settings import get_config
from stockpulse.data.cache import get_cached, set_cached

logger = logging.getLogger(__name__)


def get_recent_filings(ticker: str, lookback_days: int = 30) -> list[dict]:
    """Get recent SEC filings for a ticker using EdgarTools."""
    cache_key = f"sec_filings_{ticker}_{lookback_days}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        from edgar import Company

        cfg = get_config()
        os.environ.setdefault("EDGAR_IDENTITY", cfg["sec_user_agent"])

        company = Company(ticker)
        filings = company.get_filings()

        results = []
        cutoff = datetime.now() - timedelta(days=lookback_days)

        for filing in filings[:50]:  # check last 50 filings
            try:
                filed_date = filing.filing_date
                if hasattr(filed_date, 'date'):
                    filed_date = filed_date.date()
                if isinstance(filed_date, str):
                    filed_date = datetime.strptime(filed_date, "%Y-%m-%d").date()

                if filed_date >= cutoff.date():
                    results.append({
                        "form": filing.form,
                        "date": str(filed_date),
                        "description": getattr(filing, "description", ""),
                        "url": getattr(filing, "filing_url", ""),
                    })
            except Exception:
                continue

        set_cached(cache_key, results)
        return results
    except Exception:
        logger.debug("Failed to fetch SEC filings for %s", ticker)
        return []
```

- [ ] **Step 4: Implement sec/insider.py**

```python
# stockpulse/sec/insider.py
"""Insider transaction monitoring via EdgarTools."""

import logging
import os
from datetime import datetime, timedelta

from stockpulse.data.cache import get_cached, set_cached
from stockpulse.config.settings import get_config

logger = logging.getLogger(__name__)


def get_insider_transactions(ticker: str, lookback_days: int = 30) -> list[dict]:
    """Get recent insider transactions (Form 4) for a ticker."""
    cache_key = f"insider_{ticker}_{lookback_days}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        from edgar import Company
        os.environ.setdefault("EDGAR_IDENTITY", get_config()["sec_user_agent"])

        company = Company(ticker)
        filings = company.get_filings(form="4")

        results = []
        cutoff = datetime.now() - timedelta(days=lookback_days)

        for filing in filings[:20]:
            try:
                filed_date = filing.filing_date
                if hasattr(filed_date, 'date'):
                    filed_date = filed_date.date()
                if isinstance(filed_date, str):
                    filed_date = datetime.strptime(filed_date, "%Y-%m-%d").date()

                if filed_date >= cutoff.date():
                    results.append({
                        "form": "4",
                        "date": str(filed_date),
                        "filer": getattr(filing, "filer", "Unknown"),
                        "description": getattr(filing, "description", ""),
                    })
            except Exception:
                continue

        set_cached(cache_key, results)
        return results
    except Exception:
        logger.debug("Failed to fetch insider data for %s", ticker)
        return []


def summarize_insider_activity(ticker: str) -> dict:
    """Summarize insider buying/selling activity."""
    transactions = get_insider_transactions(ticker)
    return {
        "total_filings": len(transactions),
        "recent_form4s": transactions[:5],
        "has_activity": len(transactions) > 0,
    }
```

- [ ] **Step 5: Implement signals/fundamental.py**

```python
# stockpulse/signals/fundamental.py
"""Fundamental/catalyst signal generators.

Each function returns a score from -100 to +100.
"""

import logging

from stockpulse.data.provider import get_earnings_dates, get_news
from stockpulse.sec.filings import get_recent_filings
from stockpulse.sec.insider import get_insider_transactions
from stockpulse.config.settings import load_strategies

logger = logging.getLogger(__name__)

_POSITIVE_KEYWORDS = [
    "beat", "surge", "jump", "soar", "upgrade", "strong", "growth",
    "profit", "record", "exceeded", "outperform", "buy", "bullish",
    "positive", "gain", "rally", "breakout", "momentum", "dividend",
    "innovation", "partnership", "expansion", "approval",
]

_NEGATIVE_KEYWORDS = [
    "miss", "decline", "drop", "fall", "downgrade", "weak", "loss",
    "layoff", "cut", "warning", "concern", "risk", "sell", "bearish",
    "negative", "crash", "lawsuit", "investigation", "recall", "debt",
    "bankruptcy", "fraud", "resign", "delay",
]


def _clamp(value: float, lo: float = -100.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def calc_earnings_signal(ticker: str) -> float:
    """Earnings proximity signal: within N days = catalyst flag."""
    cfg = load_strategies().get("signals", {}).get("earnings", {})
    proximity_days = cfg.get("proximity_days", 14)

    dates = get_earnings_dates(ticker)
    if not dates:
        return 0.0

    for d in dates:
        days_away = d.get("days_away", 999)
        if 0 <= days_away <= proximity_days:
            intensity = 1.0 - (days_away / proximity_days)
            return _clamp(intensity * 40)

    return 0.0


def calc_sec_filing_signal(ticker: str) -> float:
    """SEC filing catalyst signal: recent 8-K = event, insider buys = bullish."""
    cfg = load_strategies().get("signals", {}).get("sec_filing", {})
    lookback_days = cfg.get("lookback_days", 30)

    score = 0.0

    filings = get_recent_filings(ticker, lookback_days)
    for filing in filings:
        form = filing.get("form", "")
        if form == "8-K":
            score += 15
        elif form in ("10-K", "10-Q"):
            score += 5

    insiders = get_insider_transactions(ticker, lookback_days)
    if insiders:
        score += min(len(insiders) * 5, 20)

    return _clamp(score)


def calc_news_sentiment_signal(ticker: str) -> float:
    """News sentiment signal: keyword-based analysis of Yahoo news titles.

    NOTE: This is a low-confidence signal based on title keywords only.
    """
    news = get_news(ticker)
    if not news:
        return 0.0

    positive_count = 0
    negative_count = 0

    for item in news:
        title = item.get("title", "").lower()
        for kw in _POSITIVE_KEYWORDS:
            if kw in title:
                positive_count += 1
        for kw in _NEGATIVE_KEYWORDS:
            if kw in title:
                negative_count += 1

    if positive_count + negative_count == 0:
        return 0.0

    net = positive_count - negative_count
    total = positive_count + negative_count
    ratio = net / total

    return _clamp(ratio * 60)
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
python -m pytest tests/test_fundamental.py -v
```
Expected: 3 passed (requires internet for EDGAR/Yahoo)

- [ ] **Step 7: Commit**

```bash
git add stockpulse/sec/ stockpulse/signals/fundamental.py tests/test_fundamental.py
git commit -m "feat: add SEC filings, insider monitoring, and fundamental signals"
```

---

### Task 7: Signal Engine and Composite Scoring

**Files:**
- Create: `stockpulse/signals/engine.py`
- Create: `stockpulse/signals/composite.py`
- Create: `tests/test_engine.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_engine.py
import pandas as pd
import numpy as np
from stockpulse.signals.engine import compute_all_signals
from stockpulse.signals.composite import compute_composite_score, classify_action


def _make_price_df(n=100, base=100.0, trend=0.1):
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    close = base + np.cumsum(np.random.randn(n) * 2 + trend)
    close = np.maximum(close, 1.0)
    return pd.DataFrame({
        "Open": close * 0.99,
        "High": close * 1.02,
        "Low": close * 0.98,
        "Close": close,
        "Volume": np.random.randint(1_000_000, 10_000_000, n),
    }, index=dates)


def test_compute_all_signals_returns_dict():
    df = _make_price_df(n=260)
    signals = compute_all_signals("TEST", df)
    assert isinstance(signals, dict)
    assert "rsi" in signals
    assert "macd" in signals
    assert "moving_averages" in signals
    assert all("score" in v for v in signals.values())


def test_composite_score_bounded():
    signals = {
        "rsi": {"score": 50, "weight": 0.15, "value": 35},
        "macd": {"score": 30, "weight": 0.15, "value": "bullish"},
        "moving_averages": {"score": 20, "weight": 0.15, "value": "above_50_200"},
        "volume": {"score": 0, "weight": 0.10, "value": 1.2},
        "breakout": {"score": 10, "weight": 0.10, "value": 0.7},
        "gap": {"score": 0, "weight": 0.05, "value": 0.5},
        "adx": {"score": 40, "weight": 0.10, "value": 30},
        "earnings": {"score": 20, "weight": 0.05, "value": 8},
        "sec_filing": {"score": 15, "weight": 0.10, "value": 2},
        "news_sentiment": {"score": 10, "weight": 0.05, "value": 0.3},
    }
    score = compute_composite_score(signals)
    assert -100 <= score <= 100


def test_classify_action():
    assert classify_action(50) == "BUY"
    assert classify_action(20) == "HOLD"
    assert classify_action(0) == "HOLD"
    assert classify_action(-50) == "SELL"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_engine.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement composite.py**

```python
# stockpulse/signals/composite.py
"""Composite score calculation and action classification."""

from stockpulse.config.settings import load_strategies


def compute_composite_score(signals: dict) -> float:
    """Weighted sum of all signal scores -> single composite score."""
    total = 0.0
    total_weight = 0.0

    for name, sig in signals.items():
        score = sig.get("score", 0.0)
        weight = sig.get("weight", 0.0)
        total += score * weight
        total_weight += weight

    if total_weight == 0:
        return 0.0

    return max(-100.0, min(100.0, total / total_weight))


def classify_action(composite_score: float) -> str:
    """Classify composite score into BUY/HOLD/SELL."""
    thresholds = load_strategies().get("thresholds", {})
    buy_threshold = thresholds.get("buy", 40)
    sell_threshold = thresholds.get("sell", -40)

    if composite_score > buy_threshold:
        return "BUY"
    elif composite_score < sell_threshold:
        return "SELL"
    else:
        return "HOLD"


def compute_confidence(composite_score: float) -> int:
    """Confidence = abs(composite_score), capped at 100."""
    return min(int(abs(composite_score)), 100)
```

- [ ] **Step 4: Implement engine.py**

```python
# stockpulse/signals/engine.py
"""Signal aggregator -- computes all signals for a ticker."""

import logging

import pandas as pd

from stockpulse.config.settings import load_strategies
from stockpulse.signals.technical import (
    calc_rsi_signal,
    calc_macd_signal,
    calc_ma_signal,
    calc_volume_signal,
    calc_breakout_signal,
    calc_gap_signal,
    calc_adx_signal,
)
from stockpulse.signals.fundamental import (
    calc_earnings_signal,
    calc_sec_filing_signal,
    calc_news_sentiment_signal,
)

logger = logging.getLogger(__name__)


def compute_all_signals(ticker: str, df: pd.DataFrame) -> dict:
    """Compute all signals for a ticker given its price DataFrame.

    Returns dict of {signal_name: {"score": float, "weight": float, "value": any}}.
    """
    strat = load_strategies()
    signal_cfg = strat.get("signals", {})

    signals = {}

    technical_calculators = {
        "rsi": calc_rsi_signal,
        "macd": calc_macd_signal,
        "moving_averages": calc_ma_signal,
        "volume": calc_volume_signal,
        "breakout": calc_breakout_signal,
        "gap": calc_gap_signal,
        "adx": calc_adx_signal,
    }

    for name, calc_fn in technical_calculators.items():
        try:
            score = calc_fn(df)
            weight = signal_cfg.get(name, {}).get("weight", 0.0)
            signals[name] = {"score": score, "weight": weight, "value": score}
        except Exception:
            logger.debug("Signal %s failed for %s", name, ticker)
            signals[name] = {"score": 0.0, "weight": 0.0, "value": None}

    fundamental_calculators = {
        "earnings": calc_earnings_signal,
        "sec_filing": calc_sec_filing_signal,
        "news_sentiment": calc_news_sentiment_signal,
    }

    for name, calc_fn in fundamental_calculators.items():
        try:
            score = calc_fn(ticker)
            weight = signal_cfg.get(name, {}).get("weight", 0.0)
            signals[name] = {"score": score, "weight": weight, "value": score}
        except Exception:
            logger.debug("Signal %s failed for %s", name, ticker)
            signals[name] = {"score": 0.0, "weight": 0.0, "value": None}

    return signals
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_engine.py -v
```
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add stockpulse/signals/ tests/test_engine.py
git commit -m "feat: add signal engine with composite scoring and action classification"
```

---

## Phase 4: Research & Recommendations

### Task 8: Recommendation Engine

**Files:**
- Create: `stockpulse/research/scoring.py`
- Create: `stockpulse/research/recommendation.py`
- Create: `tests/test_recommendation.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_recommendation.py
import pandas as pd
import numpy as np
from stockpulse.research.recommendation import generate_recommendation


def _make_price_df(n=260, base=100.0, trend=0.1):
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    close = base + np.cumsum(np.random.randn(n) * 2 + trend)
    close = np.maximum(close, 1.0)
    return pd.DataFrame({
        "Open": close * 0.99,
        "High": close * 1.02,
        "Low": close * 0.98,
        "Close": close,
        "Volume": np.random.randint(1_000_000, 10_000_000, n),
    }, index=dates)


def test_generate_recommendation_returns_valid_structure():
    df = _make_price_df()
    rec = generate_recommendation("TEST", df)
    assert rec["ticker"] == "TEST"
    assert rec["action"] in ("BUY", "HOLD", "SELL")
    assert 0 <= rec["confidence"] <= 100
    assert isinstance(rec["thesis"], str)
    assert isinstance(rec["technical_summary"], str)
    assert isinstance(rec["catalyst_summary"], str)
    assert isinstance(rec["invalidation"], str)
    assert isinstance(rec["signals"], dict)
    assert "timestamp" in rec
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_recommendation.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement scoring.py**

```python
# stockpulse/research/scoring.py
"""Confidence scoring and invalidation generation."""

import pandas as pd
import pandas_ta as ta


def compute_invalidation(ticker: str, action: str, df: pd.DataFrame) -> str:
    """Generate invalidation conditions based on action and technicals."""
    if df.empty:
        return "Insufficient data for invalidation levels"

    sma50 = ta.sma(df["Close"], length=50)
    sma200 = ta.sma(df["Close"], length=200)

    sma50_val = float(sma50.iloc[-1]) if sma50 is not None and not sma50.dropna().empty else None
    sma200_val = float(sma200.iloc[-1]) if sma200 is not None and not sma200.dropna().empty else None

    rsi = ta.rsi(df["Close"], length=14)

    parts = []
    if action == "BUY":
        if sma50_val:
            parts.append(f"Close below 50-day SMA (${sma50_val:.2f})")
        parts.append("RSI > 75")
    elif action == "SELL":
        if sma50_val:
            parts.append(f"Close above 50-day SMA (${sma50_val:.2f})")
        parts.append("RSI < 25")
    else:
        parts.append("No specific invalidation for HOLD")

    return " or ".join(parts) if parts else "Monitor for significant change"
```

- [ ] **Step 4: Implement recommendation.py**

```python
# stockpulse/research/recommendation.py
"""Buy/sell/hold recommendation engine."""

from datetime import datetime

import pandas as pd

from stockpulse.signals.engine import compute_all_signals
from stockpulse.signals.composite import (
    compute_composite_score,
    classify_action,
    compute_confidence,
)
from stockpulse.research.scoring import compute_invalidation


def _build_technical_summary(signals: dict) -> str:
    """Create human-readable technical summary from signal data."""
    parts = []

    rsi = signals.get("rsi", {})
    if rsi.get("value") is not None:
        parts.append(f"RSI: {rsi['value']:.0f}")

    macd = signals.get("macd", {})
    if macd.get("score", 0) > 20:
        parts.append("MACD: bullish")
    elif macd.get("score", 0) < -20:
        parts.append("MACD: bearish")
    else:
        parts.append("MACD: neutral")

    ma = signals.get("moving_averages", {})
    if ma.get("score", 0) > 0:
        parts.append("Above key SMAs")
    elif ma.get("score", 0) < 0:
        parts.append("Below key SMAs")

    vol = signals.get("volume", {})
    if abs(vol.get("score", 0)) > 30:
        parts.append("Volume spike detected")

    adx = signals.get("adx", {})
    if adx.get("score", 0) > 20:
        parts.append("Strong uptrend (ADX)")
    elif adx.get("score", 0) < -20:
        parts.append("Strong downtrend (ADX)")

    return ". ".join(parts) if parts else "Insufficient technical data"


def _build_catalyst_summary(signals: dict) -> str:
    """Create human-readable catalyst summary."""
    parts = []

    earnings = signals.get("earnings", {})
    if earnings.get("score", 0) > 0:
        parts.append("Earnings approaching")

    sec = signals.get("sec_filing", {})
    if sec.get("score", 0) > 10:
        parts.append("Recent SEC filing activity")

    news = signals.get("news_sentiment", {})
    if news.get("score", 0) > 10:
        parts.append("Positive news sentiment")
    elif news.get("score", 0) < -10:
        parts.append("Negative news sentiment")

    return ". ".join(parts) if parts else "No significant catalysts detected"


def _build_thesis(action: str, signals: dict, composite: float) -> str:
    """Generate a thesis string from action and signals."""
    strongest = max(signals.items(), key=lambda x: abs(x[1].get("score", 0)))
    name, data = strongest

    direction = "Bullish" if composite > 0 else "Bearish"
    return f"{direction} signal driven primarily by {name} (score: {data['score']:.0f}). Composite: {composite:.1f}"


def generate_recommendation(ticker: str, df: pd.DataFrame) -> dict:
    """Generate a full recommendation for a ticker."""
    signals = compute_all_signals(ticker, df)
    composite = compute_composite_score(signals)
    action = classify_action(composite)
    confidence = compute_confidence(composite)
    invalidation = compute_invalidation(ticker, action, df)

    return {
        "ticker": ticker,
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "confidence": confidence,
        "composite_score": round(composite, 2),
        "thesis": _build_thesis(action, signals, composite),
        "technical_summary": _build_technical_summary(signals),
        "catalyst_summary": _build_catalyst_summary(signals),
        "invalidation": invalidation,
        "signals": signals,
    }


def rank_recommendations(recommendations: list[dict]) -> list[dict]:
    """Sort recommendations by absolute composite score descending."""
    return sorted(recommendations, key=lambda r: abs(r["composite_score"]), reverse=True)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_recommendation.py -v
```
Expected: 1 passed

- [ ] **Step 6: Commit**

```bash
git add stockpulse/research/ tests/test_recommendation.py
git commit -m "feat: add recommendation engine with scoring, thesis, and invalidation"
```

---

## Phase 5: Scanners

### Task 9: Market and Catalyst Scanners

**Files:**
- Create: `stockpulse/scanners/market_scanner.py`
- Create: `stockpulse/scanners/technical_scanner.py`
- Create: `stockpulse/scanners/catalyst_scanner.py`
- Create: `tests/test_scanner.py`

- [ ] **Step 1: Write test**

```python
# tests/test_scanner.py
from stockpulse.scanners.market_scanner import run_full_scan


def test_full_scan_returns_recommendations():
    # Use a tiny universe for testing
    results = run_full_scan(tickers=["AAPL", "MSFT"])
    assert isinstance(results, list)
    assert len(results) > 0
    assert all("ticker" in r for r in results)
    assert all("action" in r for r in results)
    assert all("confidence" in r for r in results)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_scanner.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement technical_scanner.py**

```python
# stockpulse/scanners/technical_scanner.py
"""Technical scanner -- scans a list of tickers for technical signals."""

import logging

import pandas as pd

from stockpulse.data.provider import get_price_history
from stockpulse.signals.engine import compute_all_signals
from stockpulse.signals.composite import compute_composite_score

logger = logging.getLogger(__name__)


def scan_technical(tickers: list[str]) -> list[dict]:
    """Compute technical signals for each ticker.

    Returns list of {ticker, composite_score, signals} sorted by |score|.
    """
    results = []
    for ticker in tickers:
        try:
            df = get_price_history(ticker, period="1y")
            if df.empty or len(df) < 50:
                continue
            signals = compute_all_signals(ticker, df)
            composite = compute_composite_score(signals)
            results.append({
                "ticker": ticker,
                "composite_score": composite,
                "signals": signals,
                "df": df,
            })
        except Exception:
            logger.debug("Technical scan failed for %s", ticker)

    results.sort(key=lambda r: abs(r["composite_score"]), reverse=True)
    return results
```

- [ ] **Step 4: Implement catalyst_scanner.py**

```python
# stockpulse/scanners/catalyst_scanner.py
"""Catalyst scanner -- scans for SEC filings, earnings, insider activity."""

import logging

from stockpulse.sec.filings import get_recent_filings
from stockpulse.sec.insider import get_insider_transactions
from stockpulse.data.provider import get_earnings_dates

logger = logging.getLogger(__name__)


def scan_catalysts(tickers: list[str]) -> dict[str, dict]:
    """Scan tickers for fundamental catalysts.

    Returns dict of {ticker: {filings, insiders, earnings}}.
    """
    results = {}
    for ticker in tickers:
        try:
            catalysts = {
                "filings": get_recent_filings(ticker, lookback_days=30),
                "insiders": get_insider_transactions(ticker, lookback_days=30),
                "earnings": get_earnings_dates(ticker),
            }
            if any(catalysts.values()):
                results[ticker] = catalysts
        except Exception:
            logger.debug("Catalyst scan failed for %s", ticker)

    return results
```

- [ ] **Step 5: Implement market_scanner.py**

```python
# stockpulse/scanners/market_scanner.py
"""Market scanner -- orchestrates full scan across universe."""

import logging
from datetime import datetime

from stockpulse.data.universe import get_full_universe
from stockpulse.data.provider import get_price_history
from stockpulse.research.recommendation import generate_recommendation, rank_recommendations
from stockpulse.config.settings import load_strategies

logger = logging.getLogger(__name__)


def run_full_scan(tickers: list[str] | None = None) -> list[dict]:
    """Run a full scan of the universe and generate ranked recommendations."""
    if tickers is None:
        tickers = get_full_universe()

    logger.info("Starting full scan of %d tickers at %s", len(tickers), datetime.now())

    recommendations = []

    for i, ticker in enumerate(tickers):
        try:
            df = get_price_history(ticker, period="1y")
            if df.empty or len(df) < 50:
                logger.debug("Skipping %s: insufficient data (%d rows)", ticker, len(df))
                continue

            rec = generate_recommendation(ticker, df)
            recommendations.append(rec)

            if (i + 1) % 50 == 0:
                logger.info("Scanned %d/%d tickers", i + 1, len(tickers))

        except Exception:
            logger.debug("Scan failed for %s", ticker)

    ranked = rank_recommendations(recommendations)
    logger.info(
        "Scan complete: %d tickers scanned, %d recommendations generated",
        len(tickers),
        len(ranked),
    )
    return ranked


def run_watchlist_scan(tickers: list[str]) -> list[dict]:
    """Quick scan of watchlist tickers only (for intraday checks)."""
    return run_full_scan(tickers=tickers)
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
python -m pytest tests/test_scanner.py -v -x
```
Expected: 1 passed (requires internet)

- [ ] **Step 7: Commit**

```bash
git add stockpulse/scanners/ tests/test_scanner.py
git commit -m "feat: add market, technical, and catalyst scanners"
```

---

## Phase 6: Alerts & Reports (tasks can run in parallel)

### Task 10: Alert System

**Files:**
- Create: `stockpulse/alerts/log_alert.py`
- Create: `stockpulse/alerts/telegram_alert.py`
- Create: `stockpulse/alerts/discord_alert.py`
- Create: `stockpulse/alerts/dispatcher.py`

- [ ] **Step 1: Implement log_alert.py**

```python
# stockpulse/alerts/log_alert.py
"""Always-on file logger for alerts."""

import json
import logging
from datetime import datetime
from pathlib import Path

from stockpulse.config.settings import get_config

logger = logging.getLogger(__name__)


def _log_path() -> Path:
    cfg = get_config()
    path = Path(cfg["outputs_dir"]) / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path / "alerts.log"


def send_log_alert(alert: dict) -> bool:
    """Write alert to log file. Always succeeds."""
    try:
        entry = {
            "timestamp": datetime.now().isoformat(),
            **alert,
        }
        with open(_log_path(), "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
        return True
    except Exception:
        logger.exception("Failed to write alert log")
        return False
```

- [ ] **Step 2: Implement telegram_alert.py**

```python
# stockpulse/alerts/telegram_alert.py
"""Telegram alert sender (optional)."""

import asyncio
import logging

from stockpulse.config.settings import get_config

logger = logging.getLogger(__name__)


def _format_message(alert: dict) -> str:
    """Format alert dict into Telegram message."""
    ticker = alert.get("ticker", "???")
    action = alert.get("action", "???")
    confidence = alert.get("confidence", 0)
    thesis = alert.get("thesis", "")

    emoji = {"BUY": "\u2705", "SELL": "\ud83d\udd34", "HOLD": "\u26a0\ufe0f"}.get(action, "\u2139\ufe0f")

    return (
        f"{emoji} *{ticker}* -- {action} (confidence: {confidence}%)\n\n"
        f"{thesis}\n\n"
        f"_{alert.get('type', 'signal')}_"
    )


async def _send_async(token: str, chat_id: str, text: str) -> bool:
    """Send message via python-telegram-bot."""
    try:
        from telegram import Bot
        bot = Bot(token=token)
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
        return True
    except Exception:
        logger.exception("Telegram send failed")
        return False


def send_telegram_alert(alert: dict) -> bool:
    """Send alert to Telegram. Returns True if sent successfully."""
    cfg = get_config()
    if not cfg["alerts_telegram"]:
        return False

    token = cfg["telegram_bot_token"]
    chat_id = cfg["telegram_chat_id"]

    if not token or not chat_id:
        logger.warning("Telegram enabled but token/chat_id not configured")
        return False

    text = _format_message(alert)
    try:
        return asyncio.run(_send_async(token, chat_id, text))
    except Exception:
        logger.exception("Telegram alert failed")
        return False
```

- [ ] **Step 3: Implement discord_alert.py**

```python
# stockpulse/alerts/discord_alert.py
"""Discord webhook alert sender (optional)."""

import logging

import requests

from stockpulse.config.settings import get_config

logger = logging.getLogger(__name__)


def _format_embed(alert: dict) -> dict:
    """Format alert dict into Discord embed."""
    ticker = alert.get("ticker", "???")
    action = alert.get("action", "???")
    confidence = alert.get("confidence", 0)

    color = {"BUY": 0x00FF00, "SELL": 0xFF0000, "HOLD": 0xFFFF00}.get(action, 0x808080)

    return {
        "embeds": [
            {
                "title": f"{ticker} -- {action}",
                "description": alert.get("thesis", ""),
                "color": color,
                "fields": [
                    {"name": "Confidence", "value": f"{confidence}%", "inline": True},
                    {"name": "Type", "value": alert.get("type", "signal"), "inline": True},
                    {
                        "name": "Technical",
                        "value": alert.get("technical_summary", "N/A")[:200],
                        "inline": False,
                    },
                    {
                        "name": "Catalysts",
                        "value": alert.get("catalyst_summary", "N/A")[:200],
                        "inline": False,
                    },
                    {
                        "name": "Invalidation",
                        "value": alert.get("invalidation", "N/A")[:200],
                        "inline": False,
                    },
                ],
            }
        ]
    }


def send_discord_alert(alert: dict) -> bool:
    """Send alert to Discord via webhook. Returns True if sent successfully."""
    cfg = get_config()
    if not cfg["alerts_discord"]:
        return False

    url = cfg["discord_webhook_url"]
    if not url:
        logger.warning("Discord enabled but webhook URL not configured")
        return False

    try:
        payload = _format_embed(alert)
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception:
        logger.exception("Discord alert failed")
        return False
```

- [ ] **Step 4: Implement dispatcher.py**

```python
# stockpulse/alerts/dispatcher.py
"""Alert dispatcher -- routes alerts to all configured channels."""

import logging

from stockpulse.alerts.log_alert import send_log_alert
from stockpulse.alerts.telegram_alert import send_telegram_alert
from stockpulse.alerts.discord_alert import send_discord_alert
from stockpulse.config.settings import load_strategies

logger = logging.getLogger(__name__)


def dispatch_alert(alert: dict) -> dict[str, bool]:
    """Send alert to all configured channels."""
    thresholds = load_strategies().get("thresholds", {})
    confidence_min = thresholds.get("confidence_min", 30)

    if alert.get("confidence", 0) < confidence_min:
        logger.debug(
            "Alert for %s suppressed: confidence %d < %d",
            alert.get("ticker"),
            alert.get("confidence", 0),
            confidence_min,
        )
        return {"suppressed": True}

    results = {}
    results["log"] = send_log_alert(alert)
    results["telegram"] = send_telegram_alert(alert)
    results["discord"] = send_discord_alert(alert)

    sent = [k for k, v in results.items() if v and k != "suppressed"]
    logger.info("Alert dispatched for %s via: %s", alert.get("ticker"), sent)

    return results


def dispatch_recommendations(recommendations: list[dict]) -> None:
    """Dispatch alerts for all actionable recommendations (BUY/SELL only)."""
    for rec in recommendations:
        if rec.get("action") in ("BUY", "SELL"):
            alert = {"type": "recommendation", **rec}
            dispatch_alert(alert)
```

- [ ] **Step 5: Commit**

```bash
git add stockpulse/alerts/
git commit -m "feat: add alert system with log, Telegram, and Discord dispatchers"
```

---

### Task 11: Report Generator

**Files:**
- Create: `stockpulse/reports/daily.py`
- Create: `stockpulse/reports/intraday.py`

- [ ] **Step 1: Implement daily.py**

```python
# stockpulse/reports/daily.py
"""Daily markdown and JSON report generators."""

import json
import logging
from datetime import datetime
from pathlib import Path

from stockpulse.config.settings import get_config

logger = logging.getLogger(__name__)


def _ensure_dirs():
    cfg = get_config()
    reports_dir = Path(cfg["outputs_dir"]) / "reports"
    json_dir = Path(cfg["outputs_dir"]) / "json"
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)
    return reports_dir, json_dir


def generate_morning_report(recommendations: list[dict]) -> str:
    """Generate morning scan markdown report. Returns path to the written file."""
    reports_dir, json_dir = _ensure_dirs()
    date_str = datetime.now().strftime("%Y-%m-%d")
    report_path = reports_dir / f"{date_str}-morning.md"
    json_path = json_dir / f"{date_str}-morning.json"

    buys = [r for r in recommendations if r["action"] == "BUY"]
    sells = [r for r in recommendations if r["action"] == "SELL"]
    holds = [r for r in recommendations if r["action"] == "HOLD"]

    lines = [
        f"# StockPulse Morning Scan -- {date_str}",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S ET')}",
        f"**Tickers scanned:** {len(recommendations)}",
        f"**BUY signals:** {len(buys)} | **SELL signals:** {len(sells)} | **HOLD:** {len(holds)}",
        "",
        "---",
        "",
        "## Top 10 Opportunities",
        "",
        "| Ticker | Action | Confidence | Composite | Thesis |",
        "|--------|--------|------------|-----------|--------|",
    ]

    top10 = sorted(recommendations, key=lambda r: abs(r["composite_score"]), reverse=True)[:10]
    for r in top10:
        thesis_short = r["thesis"][:80] + "..." if len(r["thesis"]) > 80 else r["thesis"]
        lines.append(
            f"| {r['ticker']} | {r['action']} | {r['confidence']}% | "
            f"{r['composite_score']:.1f} | {thesis_short} |"
        )
    lines.append("")

    if buys:
        lines.append("## BUY Signals")
        lines.append("")
        for r in sorted(buys, key=lambda x: x["confidence"], reverse=True):
            lines.append(f"### {r['ticker']} -- BUY (confidence: {r['confidence']}%)")
            lines.append(f"- **Thesis:** {r['thesis']}")
            lines.append(f"- **Technical:** {r['technical_summary']}")
            lines.append(f"- **Catalysts:** {r['catalyst_summary']}")
            lines.append(f"- **Invalidation:** {r['invalidation']}")
            lines.append("")

    if sells:
        lines.append("## SELL Signals")
        lines.append("")
        for r in sorted(sells, key=lambda x: x["confidence"], reverse=True):
            lines.append(f"### {r['ticker']} -- SELL (confidence: {r['confidence']}%)")
            lines.append(f"- **Thesis:** {r['thesis']}")
            lines.append(f"- **Technical:** {r['technical_summary']}")
            lines.append(f"- **Invalidation:** {r['invalidation']}")
            lines.append("")

    lines.append("---")
    lines.append("*Generated by StockPulse -- research only, not financial advice.*")

    report_path.write_text("\n".join(lines))
    logger.info("Morning report written to %s", report_path)

    json_data = {
        "type": "morning_scan",
        "date": date_str,
        "timestamp": datetime.now().isoformat(),
        "total_scanned": len(recommendations),
        "buy_count": len(buys),
        "sell_count": len(sells),
        "hold_count": len(holds),
        "recommendations": [
            {k: v for k, v in r.items() if k != "signals"}
            for r in recommendations
        ],
    }
    json_path.write_text(json.dumps(json_data, indent=2, default=str))

    return str(report_path)


def generate_eod_report(recommendations: list[dict]) -> str:
    """Generate end-of-day recap report."""
    reports_dir, json_dir = _ensure_dirs()
    date_str = datetime.now().strftime("%Y-%m-%d")
    report_path = reports_dir / f"{date_str}-eod.md"
    json_path = json_dir / f"{date_str}-eod.json"

    lines = [
        f"# StockPulse EOD Recap -- {date_str}",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S ET')}",
        f"**Tickers in report:** {len(recommendations)}",
        "",
        "---",
        "",
        "## Summary",
        "",
        "| Ticker | Action | Confidence | Score |",
        "|--------|--------|------------|-------|",
    ]

    for r in sorted(recommendations, key=lambda x: abs(x["composite_score"]), reverse=True)[:20]:
        lines.append(
            f"| {r['ticker']} | {r['action']} | {r['confidence']}% | {r['composite_score']:.1f} |"
        )

    lines.append("")
    lines.append("---")
    lines.append("*Generated by StockPulse -- research only, not financial advice.*")

    report_path.write_text("\n".join(lines))

    json_data = {
        "type": "eod_recap",
        "date": date_str,
        "timestamp": datetime.now().isoformat(),
        "recommendations": [
            {k: v for k, v in r.items() if k != "signals"}
            for r in recommendations
        ],
    }
    json_path.write_text(json.dumps(json_data, indent=2, default=str))

    return str(report_path)
```

- [ ] **Step 2: Implement intraday.py**

```python
# stockpulse/reports/intraday.py
"""Intraday condition change reports."""

import logging
from datetime import datetime
from pathlib import Path

from stockpulse.config.settings import get_config

logger = logging.getLogger(__name__)

# In-memory state for tracking changes between scans
_previous_actions: dict[str, str] = {}


def detect_changes(recommendations: list[dict]) -> list[dict]:
    """Compare current recommendations to previous scan and detect changes."""
    global _previous_actions
    changes = []

    for rec in recommendations:
        ticker = rec["ticker"]
        current_action = rec["action"]
        prev_action = _previous_actions.get(ticker)

        if prev_action is not None and prev_action != current_action:
            changes.append({
                "ticker": ticker,
                "previous_action": prev_action,
                "new_action": current_action,
                "confidence": rec["confidence"],
                "thesis": rec["thesis"],
                "type": "action_change",
            })

        _previous_actions[ticker] = current_action

    return changes


def generate_intraday_report(changes: list[dict]) -> str | None:
    """Generate intraday change report if there are changes."""
    if not changes:
        return None

    cfg = get_config()
    reports_dir = Path(cfg["outputs_dir"]) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    report_path = reports_dir / f"{timestamp}-intraday.md"

    lines = [
        f"# StockPulse Intraday Update -- {timestamp}",
        "",
        f"**{len(changes)} condition change(s) detected**",
        "",
    ]

    for c in changes:
        lines.append(
            f"- **{c['ticker']}**: {c['previous_action']} -> {c['new_action']} "
            f"(confidence: {c['confidence']}%) -- {c['thesis']}"
        )

    lines.append("")
    lines.append("---")

    report_path.write_text("\n".join(lines))
    logger.info("Intraday report: %d changes written to %s", len(changes), report_path)
    return str(report_path)
```

- [ ] **Step 3: Commit**

```bash
git add stockpulse/reports/
git commit -m "feat: add daily and intraday report generators (markdown + JSON)"
```

---

## Phase 7: LLM Integration

### Task 12: LLM Summarizer and Fallback

**Files:**
- Create: `stockpulse/llm/summarizer.py`
- Create: `stockpulse/llm/fallback.py`

- [ ] **Step 1: Implement fallback.py**

```python
# stockpulse/llm/fallback.py
"""Rules-based fallback summary engine -- used when LLM is unavailable."""


def fallback_thesis(action: str, signals: dict, composite: float) -> str:
    """Generate a rules-based thesis from signal data."""
    strongest_name = ""
    strongest_score = 0
    for name, data in signals.items():
        if abs(data.get("score", 0)) > abs(strongest_score):
            strongest_name = name
            strongest_score = data.get("score", 0)

    direction = "Bullish" if composite > 0 else "Bearish"

    parts = [f"{direction} outlook with composite score {composite:.1f}."]
    parts.append(f"Strongest signal: {strongest_name} ({strongest_score:.0f}).")

    if signals.get("earnings", {}).get("score", 0) > 0:
        parts.append("Earnings approaching -- catalyst potential.")
    if signals.get("sec_filing", {}).get("score", 0) > 0:
        parts.append("Recent SEC filing activity noted.")
    if abs(signals.get("volume", {}).get("score", 0)) > 30:
        parts.append("Unusual volume detected.")

    return " ".join(parts)


def fallback_catalyst_summary(ticker: str, signals: dict) -> str:
    """Generate rules-based catalyst summary."""
    parts = []

    if signals.get("earnings", {}).get("score", 0) > 0:
        parts.append("Earnings event approaching")
    if signals.get("sec_filing", {}).get("score", 0) > 10:
        parts.append("Recent SEC filing activity (8-K or Form 4)")
    if signals.get("news_sentiment", {}).get("score", 0) > 10:
        parts.append("Positive news sentiment detected")
    elif signals.get("news_sentiment", {}).get("score", 0) < -10:
        parts.append("Negative news sentiment detected")

    return ". ".join(parts) if parts else "No significant catalysts detected"
```

- [ ] **Step 2: Implement summarizer.py**

```python
# stockpulse/llm/summarizer.py
"""LLM summarizer using AMD Claude API via Anthropic SDK."""

import logging

from stockpulse.config.settings import get_config
from stockpulse.llm.fallback import fallback_thesis, fallback_catalyst_summary

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    """Lazy-init Anthropic client."""
    global _client
    if _client is None:
        cfg = get_config()
        if not cfg["llm_enabled"]:
            return None
        try:
            import anthropic
            _client = anthropic.Anthropic(
                api_key=cfg["llm_api_key"],
                base_url=cfg["llm_base_url"],
            )
        except Exception:
            logger.warning("Failed to initialize Anthropic client")
            return None
    return _client


def _call_llm(prompt: str, max_tokens: int = 300) -> str | None:
    """Make a single LLM call. Returns response text or None on failure."""
    client = _get_client()
    if client is None:
        return None

    cfg = get_config()
    try:
        response = client.messages.create(
            model=cfg["llm_model"],
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    except Exception:
        logger.debug("LLM call failed, falling back to rules-based")
        return None


def generate_thesis(
    ticker: str, action: str, signals: dict, composite: float
) -> str:
    """Generate a natural language thesis using LLM, with fallback."""
    signal_summary = "\n".join(
        f"- {name}: score={d['score']:.0f}, weight={d['weight']}"
        for name, d in signals.items()
    )

    prompt = (
        f"You are a stock analyst. Generate a concise 2-sentence thesis for "
        f"a {action} recommendation on {ticker}.\n\n"
        f"Composite score: {composite:.1f}\n"
        f"Signals:\n{signal_summary}\n\n"
        f"Be specific about which signals drive the recommendation. "
        f"Do not use disclaimers."
    )

    result = _call_llm(prompt, max_tokens=150)
    if result:
        return result.strip()

    return fallback_thesis(action, signals, composite)


def generate_catalyst_narrative(ticker: str, signals: dict) -> str:
    """Generate catalyst summary using LLM, with fallback."""
    prompt = (
        f"Summarize the catalyst picture for {ticker} in 1-2 sentences.\n\n"
        f"Earnings signal score: {signals.get('earnings', {}).get('score', 0)}\n"
        f"SEC filing signal score: {signals.get('sec_filing', {}).get('score', 0)}\n"
        f"News sentiment score: {signals.get('news_sentiment', {}).get('score', 0)}\n\n"
        f"Only mention catalysts that are present (non-zero scores). Be factual."
    )

    result = _call_llm(prompt, max_tokens=100)
    if result:
        return result.strip()

    return fallback_catalyst_summary(ticker, signals)


def summarize_filing(filing_text: str, ticker: str) -> str:
    """Summarize an SEC filing excerpt using LLM."""
    prompt = (
        f"Summarize this SEC filing excerpt for {ticker} in 3 bullet points. "
        f"Focus on: revenue impact, risk factors, material events.\n\n"
        f"{filing_text[:3000]}"
    )

    result = _call_llm(prompt, max_tokens=200)
    return result.strip() if result else "Filing summary unavailable (LLM offline)"
```

- [ ] **Step 3: Commit**

```bash
git add stockpulse/llm/
git commit -m "feat: add LLM summarizer (AMD Claude API) with rules-based fallback"
```

---

## Phase 8: Scheduler and Entrypoint

### Task 13: Scheduler and Main Runner

**Files:**
- Create: `stockpulse/scheduler/jobs.py`
- Create: `run.py`

- [ ] **Step 1: Implement scheduler/jobs.py**

```python
# stockpulse/scheduler/jobs.py
"""APScheduler job definitions for StockPulse."""

import logging

from stockpulse.config.settings import load_watchlists
from stockpulse.scanners.market_scanner import run_full_scan, run_watchlist_scan
from stockpulse.reports.daily import generate_morning_report, generate_eod_report
from stockpulse.reports.intraday import detect_changes, generate_intraday_report
from stockpulse.alerts.dispatcher import dispatch_recommendations, dispatch_alert

logger = logging.getLogger(__name__)


def morning_scan_job():
    """Run full morning scan, generate report, dispatch alerts."""
    logger.info("=== MORNING SCAN START ===")
    try:
        recommendations = run_full_scan()
        report_path = generate_morning_report(recommendations)
        dispatch_recommendations(recommendations)

        buys = sum(1 for r in recommendations if r["action"] == "BUY")
        sells = sum(1 for r in recommendations if r["action"] == "SELL")
        logger.info(
            "Morning scan complete: %d tickers, %d BUY, %d SELL. Report: %s",
            len(recommendations), buys, sells, report_path,
        )

        dispatch_alert({
            "ticker": "SUMMARY",
            "action": "INFO",
            "confidence": 100,
            "thesis": f"Morning scan complete: {buys} BUY, {sells} SELL signals from {len(recommendations)} tickers",
            "type": "summary",
            "technical_summary": f"Report at {report_path}",
            "catalyst_summary": "",
            "invalidation": "",
        })
    except Exception:
        logger.exception("Morning scan failed")


def intraday_check_job():
    """Quick intraday check on watchlist + active recommendations."""
    logger.info("--- Intraday check ---")
    try:
        wl = load_watchlists()
        tickers = wl.get("user", []) + [
            item["ticker"] if isinstance(item, dict) else item
            for item in wl.get("priority", [])
        ]
        tickers = list(set(tickers))

        if not tickers:
            return

        recommendations = run_watchlist_scan(tickers)
        changes = detect_changes(recommendations)

        if changes:
            generate_intraday_report(changes)
            for change in changes:
                dispatch_alert(change)
            logger.info("Intraday: %d changes detected", len(changes))
        else:
            logger.info("Intraday: no changes detected")
    except Exception:
        logger.exception("Intraday check failed")


def eod_recap_job():
    """End-of-day recap scan and report."""
    logger.info("=== EOD RECAP START ===")
    try:
        wl = load_watchlists()
        tickers = wl.get("user", [])
        recommendations = run_watchlist_scan(tickers) if tickers else run_full_scan()
        report_path = generate_eod_report(recommendations)
        logger.info("EOD recap complete. Report: %s", report_path)
    except Exception:
        logger.exception("EOD recap failed")


def sec_scan_job():
    """Periodic SEC filing scan."""
    logger.info("--- SEC filing scan ---")
    try:
        from stockpulse.scanners.catalyst_scanner import scan_catalysts
        wl = load_watchlists()
        tickers = wl.get("user", [])
        catalysts = scan_catalysts(tickers)

        for ticker, data in catalysts.items():
            if data.get("filings"):
                dispatch_alert({
                    "ticker": ticker,
                    "action": "INFO",
                    "confidence": 50,
                    "thesis": f"New SEC filing(s) detected: {len(data['filings'])} recent filings",
                    "type": "sec_filing",
                    "technical_summary": "",
                    "catalyst_summary": str(data["filings"][:3]),
                    "invalidation": "",
                })
    except Exception:
        logger.exception("SEC scan failed")
```

- [ ] **Step 2: Implement run.py**

```python
# run.py
"""StockPulse main entrypoint -- starts the scheduler and runs scans."""

import argparse
import logging
import sys
from pathlib import Path

# Ensure stockpulse is importable
sys.path.insert(0, str(Path(__file__).parent))


def setup_logging(level: str = "INFO"):
    log_dir = Path(__file__).parent / "outputs" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / "stockpulse.log"),
        ],
    )


def run_once():
    """Run a single full scan immediately (no scheduler)."""
    from stockpulse.scanners.market_scanner import run_full_scan
    from stockpulse.reports.daily import generate_morning_report
    from stockpulse.alerts.dispatcher import dispatch_recommendations

    logging.info("Running one-shot full scan...")
    recommendations = run_full_scan()
    report_path = generate_morning_report(recommendations)
    dispatch_recommendations(recommendations)

    buys = [r for r in recommendations if r["action"] == "BUY"]
    sells = [r for r in recommendations if r["action"] == "SELL"]

    print(f"\nScan complete: {len(recommendations)} tickers")
    print(f"BUY signals: {len(buys)}")
    print(f"SELL signals: {len(sells)}")
    print(f"Report: {report_path}")

    if buys:
        print("\nTop BUY signals:")
        for r in sorted(buys, key=lambda x: x["confidence"], reverse=True)[:5]:
            print(f"  {r['ticker']:6s} confidence={r['confidence']}% score={r['composite_score']:.1f}")


def run_scheduler():
    """Start the APScheduler with all configured jobs."""
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger
    from stockpulse.config.settings import load_strategies
    from stockpulse.scheduler.jobs import (
        morning_scan_job,
        intraday_check_job,
        eod_recap_job,
        sec_scan_job,
    )

    strat = load_strategies()
    sched_cfg = strat.get("scheduling", {})
    tz = sched_cfg.get("timezone", "US/Eastern")

    scheduler = BlockingScheduler(timezone=tz)

    morning_time = sched_cfg.get("morning_scan", "09:00")
    h, m = morning_time.split(":")
    scheduler.add_job(
        morning_scan_job,
        CronTrigger(hour=int(h), minute=int(m), day_of_week="mon-fri", timezone=tz),
        id="morning_scan",
        name="Morning Full Scan",
    )

    interval_min = sched_cfg.get("intraday_interval_minutes", 30)
    scheduler.add_job(
        intraday_check_job,
        CronTrigger(
            minute=f"*/{interval_min}",
            hour="9-16",
            day_of_week="mon-fri",
            timezone=tz,
        ),
        id="intraday_check",
        name="Intraday Check",
    )

    eod_time = sched_cfg.get("eod_recap", "16:30")
    h, m = eod_time.split(":")
    scheduler.add_job(
        eod_recap_job,
        CronTrigger(hour=int(h), minute=int(m), day_of_week="mon-fri", timezone=tz),
        id="eod_recap",
        name="EOD Recap",
    )

    sec_interval = sched_cfg.get("sec_scan_interval_hours", 2)
    scheduler.add_job(
        sec_scan_job,
        CronTrigger(
            hour=f"*/{sec_interval}",
            day_of_week="mon-fri",
            timezone=tz,
        ),
        id="sec_scan",
        name="SEC Filing Scan",
    )

    logging.info("StockPulse scheduler started with %d jobs:", len(scheduler.get_jobs()))
    for job in scheduler.get_jobs():
        logging.info("  - %s: %s", job.name, job.trigger)

    print("StockPulse scheduler is running. Press Ctrl+C to stop.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Scheduler stopped.")


def main():
    parser = argparse.ArgumentParser(description="StockPulse -- Stock Research & Alert System")
    parser.add_argument(
        "mode",
        choices=["scan", "schedule", "backtest"],
        help="scan: one-shot scan | schedule: start scheduler | backtest: run backtest",
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    parser.add_argument("--start", help="Backtest start date (YYYY-MM-DD)")
    parser.add_argument("--end", help="Backtest end date (YYYY-MM-DD)")
    args = parser.parse_args()

    setup_logging(args.log_level)

    if args.mode == "scan":
        run_once()
    elif args.mode == "schedule":
        run_scheduler()
    elif args.mode == "backtest":
        from stockpulse.backtests.runner import run_backtest
        run_backtest(start_date=args.start, end_date=args.end)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Commit**

```bash
git add stockpulse/scheduler/ run.py
git commit -m "feat: add scheduler and main entrypoint (scan/schedule/backtest modes)"
```

---

## Phase 9: Backtesting

### Task 14: Lumibot Strategy and Backtest Runner

**Files:**
- Create: `stockpulse/strategies/base_strategy.py`
- Create: `stockpulse/strategies/momentum_catalyst.py`
- Create: `stockpulse/backtests/runner.py`

- [ ] **Step 1: Implement base_strategy.py**

```python
# stockpulse/strategies/base_strategy.py
"""Base strategy interface for StockPulse strategies."""

from lumibot.strategies import Strategy


class StockPulseStrategy(Strategy):
    """Base class for StockPulse strategies using Lumibot."""

    parameters = {
        "buy_threshold": 40,
        "exit_threshold": 10,
        "max_positions": 10,
        "position_size": "equal_weight",
    }

    def initialize(self):
        self.sleeptime = "1D"
        self.set_market("NYSE")

    def get_position_size(self):
        """Calculate position size based on config."""
        cash = self.get_cash()
        max_pos = self.parameters.get("max_positions", 10)
        current_positions = len(self.get_positions())
        available_slots = max_pos - current_positions
        if available_slots <= 0:
            return 0
        return cash / available_slots
```

- [ ] **Step 2: Implement momentum_catalyst.py**

```python
# stockpulse/strategies/momentum_catalyst.py
"""Momentum + Catalyst strategy -- default StockPulse strategy.

Entry: composite signal score > buy_threshold
Exit: score drops below exit_threshold
"""

import logging

from stockpulse.strategies.base_strategy import StockPulseStrategy
from stockpulse.data.provider import get_price_history
from stockpulse.signals.engine import compute_all_signals
from stockpulse.signals.composite import compute_composite_score

logger = logging.getLogger(__name__)


class MomentumCatalystStrategy(StockPulseStrategy):
    """Buy on strong composite signals, sell when signal weakens."""

    parameters = {
        "buy_threshold": 40,
        "exit_threshold": 10,
        "max_positions": 10,
        "universe": ["AAPL", "MSFT", "NVDA", "AMD", "GOOGL", "AMZN", "TSLA", "META"],
    }

    def on_trading_iteration(self):
        universe = self.parameters.get("universe", [])
        buy_threshold = self.parameters.get("buy_threshold", 40)
        exit_threshold = self.parameters.get("exit_threshold", 10)

        # Check existing positions for exit
        for position in self.get_positions():
            ticker = position.asset.symbol
            try:
                df = get_price_history(ticker, period="6mo")
                if df.empty:
                    continue
                signals = compute_all_signals(ticker, df)
                composite = compute_composite_score(signals)

                if composite < exit_threshold:
                    self.sell_all(ticker)
                    logger.info("EXIT %s: composite %.1f < %.1f", ticker, composite, exit_threshold)
            except Exception:
                logger.debug("Exit check failed for %s", ticker)

        # Scan for new entries
        current_holdings = {p.asset.symbol for p in self.get_positions()}
        max_pos = self.parameters.get("max_positions", 10)

        if len(current_holdings) >= max_pos:
            return

        for ticker in universe:
            if ticker in current_holdings:
                continue
            if len(current_holdings) >= max_pos:
                break

            try:
                df = get_price_history(ticker, period="6mo")
                if df.empty or len(df) < 50:
                    continue
                signals = compute_all_signals(ticker, df)
                composite = compute_composite_score(signals)

                if composite > buy_threshold:
                    pos_size = self.get_position_size()
                    if pos_size > 0:
                        price = self.get_last_price(ticker)
                        if price and price > 0:
                            qty = int(pos_size / price)
                            if qty > 0:
                                order = self.create_order(ticker, qty, "buy")
                                self.submit_order(order)
                                current_holdings.add(ticker)
                                logger.info("ENTRY %s: composite %.1f, qty %d", ticker, composite, qty)
            except Exception:
                logger.debug("Entry scan failed for %s", ticker)
```

- [ ] **Step 3: Implement backtests/runner.py**

```python
# stockpulse/backtests/runner.py
"""Lumibot backtest runner for StockPulse strategies."""

import logging
import sys
from datetime import datetime
from pathlib import Path

from stockpulse.config.settings import load_strategies, load_watchlists

logger = logging.getLogger(__name__)

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / "backtests" / "results"


def run_backtest(
    start_date: str | None = None,
    end_date: str | None = None,
    strategy_name: str = "momentum_catalyst",
):
    """Run a backtest for the specified strategy."""
    from lumibot.backtesting import YahooDataBacktesting

    start = datetime.strptime(start_date or "2024-01-01", "%Y-%m-%d")
    end = datetime.strptime(end_date or "2025-12-31", "%Y-%m-%d")

    strat_cfg = load_strategies()
    bt_cfg = strat_cfg.get("backtesting", {})
    wl = load_watchlists()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    if strategy_name == "momentum_catalyst":
        from stockpulse.strategies.momentum_catalyst import MomentumCatalystStrategy

        MomentumCatalystStrategy.parameters.update({
            "buy_threshold": strat_cfg.get("thresholds", {}).get("buy", 40),
            "exit_threshold": strat_cfg.get("thresholds", {}).get("exit", 10),
            "max_positions": bt_cfg.get("max_positions", 10),
            "universe": wl.get("user", ["AAPL", "MSFT", "NVDA", "AMD"]),
        })

        print(f"Running backtest: {strategy_name}")
        print(f"  Period: {start.date()} to {end.date()}")
        print(f"  Initial cash: ${bt_cfg.get('initial_cash', 100000):,.0f}")
        print(f"  Universe: {MomentumCatalystStrategy.parameters['universe']}")

        results = MomentumCatalystStrategy.backtest(
            YahooDataBacktesting,
            start,
            end,
            budget=bt_cfg.get("initial_cash", 100000),
            name="StockPulse Momentum+Catalyst",
        )

        print("\nBacktest complete. Check Lumibot's output for detailed results.")
        return results
    else:
        print(f"Unknown strategy: {strategy_name}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="StockPulse Backtest Runner")
    parser.add_argument("--start", default="2024-01-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default="2025-12-31", help="End date YYYY-MM-DD")
    parser.add_argument("--strategy", default="momentum_catalyst", help="Strategy name")
    args = parser.parse_args()

    run_backtest(args.start, args.end, args.strategy)
```

- [ ] **Step 4: Commit**

```bash
git add stockpulse/strategies/ stockpulse/backtests/
git commit -m "feat: add Lumibot strategy and backtest runner"
```

---

## Phase 10: Documentation & Final Integration

### Task 15: README and Final Wiring

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create README.md**

````markdown
# StockPulse

Local, self-hosted stock research and alert system. Zero subscriptions. Free data only.

## What It Does

- Scans S&P 500 + your custom watchlist on a schedule
- Generates buy/sell/hold recommendations with confidence scores
- Sends alerts via Telegram, Discord, and local logs
- Produces daily markdown and JSON reports
- Supports backtesting with Lumibot
- Uses AMD Claude API for LLM-powered summaries (with rules-based fallback)

## Quick Start

```bash
# 1. Setup
cd ~/personal/stockpulse
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# 2. Configure
cp .env.example .env
# Edit .env with your API keys (Telegram/Discord are optional)

# 3. Run a single scan
python run.py scan

# 4. Start the scheduler (runs morning/intraday/EOD scans)
python run.py schedule

# 5. Run a backtest
python run.py backtest --start 2024-01-01 --end 2025-12-31
```

## Configuration

### Watchlists
Edit `stockpulse/config/watchlists.yaml` to add/remove tickers.

### Strategy Parameters
Edit `stockpulse/config/strategies.yaml` to adjust:
- Signal weights and thresholds
- Buy/sell/hold score thresholds
- Scan schedules
- Backtest parameters

### Alerts
Set in `.env`:
- `ALERTS_TELEGRAM=true` + `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`
- `ALERTS_DISCORD=true` + `DISCORD_WEBHOOK_URL`

### LLM
Uses AMD Claude API by default. Set `LLM_ENABLED=false` to use rules-based fallback.

## Data Sources

| Source | Data | Cost |
|--------|------|------|
| Yahoo Finance | Price, volume, fundamentals, earnings, news | Free |
| SEC EDGAR | 10-K, 10-Q, 8-K, insider trades (Form 4) | Free |
| AMD Claude API | Summarization, thesis generation | Internal |

### Limitations
- Price data: 15-min delayed intraday. Daily bars are accurate.
- News sentiment: keyword-based on Yahoo titles -- low confidence.
- Analyst ratings: not available from free sources.
- No real-time streaming.

## Output

Reports are written to `outputs/`:
- `outputs/reports/` -- daily markdown reports
- `outputs/json/` -- structured JSON data
- `outputs/logs/` -- alert logs and system logs

## Safety

- Paper mode by default (`TRADING_ENABLED=false`)
- Recommendations are research ideas, not financial advice
- Low-confidence signals (< 30%) are suppressed
- No real trades unless explicitly enabled
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with setup and usage instructions"
```

---

### Task 16: End-to-End Smoke Test

**Files:**
- No new files -- runs existing code

- [ ] **Step 1: Run the full test suite**

```bash
cd /home/ashetaia/personal/stockpulse
source .venv/bin/activate
python -m pytest tests/ -v
```
Expected: All tests pass

- [ ] **Step 2: Run a one-shot scan with a small universe**

```bash
python -c "
from stockpulse.scanners.market_scanner import run_full_scan
from stockpulse.reports.daily import generate_morning_report
recs = run_full_scan(tickers=['AAPL', 'MSFT', 'NVDA'])
path = generate_morning_report(recs)
print(f'Report: {path}')
for r in recs:
    print(f'{r[\"ticker\"]:6s} {r[\"action\"]:4s} conf={r[\"confidence\"]:3d}% score={r[\"composite_score\"]:6.1f}')
"
```
Expected: 3 tickers scanned, report generated, results printed

- [ ] **Step 3: Run the entrypoint**

```bash
python run.py scan
```
Expected: Full scan runs, report generated, BUY/SELL counts printed

- [ ] **Step 4: Verify outputs exist**

```bash
ls -la outputs/reports/
ls -la outputs/json/
ls -la outputs/logs/
```
Expected: Morning report markdown, JSON file, and log file present

- [ ] **Step 5: Commit any final fixes**

```bash
git add -A
git commit -m "fix: address smoke test issues"
```
