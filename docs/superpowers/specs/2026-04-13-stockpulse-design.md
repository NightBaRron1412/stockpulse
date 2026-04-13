# StockPulse — Local Stock Research & Alert System

**Date:** 2026-04-13
**Author:** Amir Shetaia
**Status:** Design

## Overview

StockPulse is a fully local, self-hosted, zero-subscription stock trading research and alert system. It continuously scans market conditions, technical indicators, earnings events, SEC filings, and news, then produces actionable buy/sell/hold watchlist ideas and sends alerts when conditions change.

**Stocks only. Free only. Local only.**

## Architecture: Lumibot-Centric Pipeline

- **Lumibot** — strategy execution engine and backtesting
- **yfinance** — free market data (price, volume, fundamentals, earnings dates, news)
- **EdgarTools** — SEC filings, insider trades, filing monitoring
- **pandas-ta** — technical indicator calculations
- **APScheduler** — job scheduling for scans and reports
- **Anthropic SDK** — LLM summarization via AMD Claude API
- **notify-send** — desktop alerts

### Why This Approach

Lumibot handles strategy lifecycle and backtesting natively. yfinance is the most reliable free data source. EdgarTools gives direct SEC/EDGAR access. Custom modules handle scanning, signals, alerts, and reports around Lumibot's core. OpenBB is avoided as backbone because its free providers are unreliable; yfinance direct is more stable.

## Project Structure

```
stockpulse/
├── pyproject.toml
├── .env.example
├── .env
├── README.md
├── run.py                      # Main entrypoint — scheduler
├── config/
│   ├── settings.py             # Loads .env, all config constants
│   ├── watchlists.yaml         # User watchlists + discovered
│   └── strategies.yaml         # Strategy thresholds/params
├── data/
│   ├── provider.py             # Unified data interface (yfinance)
│   ├── universe.py             # S&P500 list + user watchlist merge
│   └── cache.py                # Local disk cache (parquet, TTL-based)
├── scanners/
│   ├── market_scanner.py       # Broad scan across universe
│   ├── technical_scanner.py    # Price action, MAs, RSI, MACD, etc.
│   └── catalyst_scanner.py     # Earnings proximity, SEC filings
├── signals/
│   ├── engine.py               # Signal aggregator
│   ├── technical.py            # Technical signal generators
│   ├── fundamental.py          # Earnings, SEC, analyst signals
│   └── composite.py            # Combines signals → scored output
├── research/
│   ├── recommendation.py       # Buy/sell/hold engine
│   └── scoring.py              # Confidence scoring pipeline
├── sec/
│   ├── filings.py              # EdgarTools wrapper
│   └── insider.py              # Insider transaction monitor
├── alerts/
│   ├── dispatcher.py           # Routes alerts to channels
│   ├── telegram_alert.py       # Telegram bot (optional)
│   ├── discord_alert.py        # Discord webhook (optional)
│   └── log_alert.py            # Always-on file logger
├── reports/
│   ├── daily.py                # Morning/EOD markdown reports
│   └── intraday.py             # Intraday condition reports
├── strategies/
│   ├── base_strategy.py        # Lumibot strategy base
│   └── momentum_catalyst.py    # Default: technicals + catalysts
├── backtests/
│   ├── runner.py               # Lumibot backtest runner
│   └── results/                # Output dir for backtest reports
├── llm/
│   ├── summarizer.py           # AMD Claude API summarizer
│   └── fallback.py             # Rules-based summary engine
├── scheduler/
│   └── jobs.py                 # APScheduler job definitions
├── outputs/                    # Generated reports, JSON, logs
│   ├── reports/
│   ├── json/
│   └── logs/
└── tests/
    ├── test_signals.py
    ├── test_scanner.py
    └── test_recommendation.py
```

## Data Sources

| Source | Data | Library | Cost |
|--------|------|---------|------|
| Yahoo Finance | Price, volume, fundamentals, earnings dates, news headlines | `yfinance` | Free |
| SEC EDGAR | 10-K, 10-Q, 8-K, insider forms (Form 4), all filings | `edgartools` | Free |
| Wikipedia/Slickcharts | S&P 500 constituent list | `pandas` + requests | Free |
| AMD Claude API | Summarization of filings, news, thesis generation | `anthropic` SDK | Internal (free) |

### Explicitly NOT Using

- OpenBB providers requiring API keys (Alpha Vantage, Polygon, FMP, etc.)
- Real-time streaming / WebSocket data
- Level 2 / order book data
- Paid analyst ratings APIs
- Any service requiring a subscription or credit card

### Data Limitations (Honest Labels)

- **Price data:** 15-min delayed intraday from Yahoo. Daily bars are accurate. Sufficient for swing/position analysis, not scalping.
- **News sentiment:** Based on Yahoo Finance news titles only — keyword-based, not deep NLP. Labeled as "low-confidence" in outputs.
- **Analyst ratings:** Not available from free sources. Omitted rather than faked.
- **Earnings estimates:** Yahoo provides some consensus data; coverage is inconsistent. Labeled when unavailable.

## Stock Universe

Default scan universe: **S&P 500 + user-defined watchlist** (merged, deduplicated).

- S&P 500 list fetched from Wikipedia, cached locally, refreshed weekly.
- User watchlist defined in `config/watchlists.yaml`.
- Discovered opportunities added to a separate "discovered" watchlist section.

## Signal Engine

Each signal produces a score from -100 (strong sell) to +100 (strong buy).

| Signal | Calculation | Default Weight |
|--------|-------------|----------------|
| RSI (14) | <30 bullish, >70 bearish, linear scale between | 15% |
| MACD | Signal line crossover direction + histogram momentum | 15% |
| Moving Averages | Price vs 20/50/200 SMA; golden/death cross detection | 15% |
| Volume Spike | Current volume vs 20-day avg; >2x = significant event | 10% |
| Breakout | 52-week high/low breaks, horizontal support/resistance | 10% |
| Gap | Gap up/down >2% from prior close | 5% |
| Trend Strength (ADX) | ADX >25 = trending; +DI/-DI for direction | 10% |
| Earnings Proximity | Within 14 days = catalyst flag; direction from prior reactions | 5% |
| SEC Filing Catalyst | Recent 8-K, insider buys (Form 4), large transactions | 10% |
| News Sentiment | Keyword-based positive/negative from Yahoo news titles | 5% |

All weights and thresholds configurable in `config/strategies.yaml`.

### Composite Score

Weighted sum of all signal scores → single composite score per ticker.

| Composite Score | Classification |
|----------------|----------------|
| > +40 | **BUY** |
| +15 to +40 | **HOLD** (bullish lean) |
| -15 to +15 | **HOLD** (neutral) |
| -40 to -15 | **HOLD** (bearish lean) |
| < -40 | **SELL** |

Confidence = abs(composite_score), capped at 100.

## Recommendation Output

```json
{
  "ticker": "AAPL",
  "timestamp": "2026-04-13T09:30:00",
  "action": "BUY",
  "confidence": 72,
  "thesis": "Bullish MACD crossover with volume confirmation above 50-day SMA",
  "technical_summary": "RSI: 45, MACD: bullish crossover, above 20/50 SMA, below 200 SMA",
  "catalyst_summary": "Earnings in 8 days. Recent 8-K filing. No insider sells.",
  "invalidation": "Close below 50-day SMA ($182.50) or RSI > 75",
  "signals": {
    "rsi": {"value": 45, "score": 15, "weight": 0.15},
    "macd": {"value": "bullish_crossover", "score": 60, "weight": 0.15},
    ...
  }
}
```

## Watchlists

### config/watchlists.yaml

```yaml
user:
  - AAPL
  - MSFT
  - NVDA
  - AMD
  - GOOGL
  - AMZN
  - TSLA
  - META

discovered: []  # Auto-populated by scanner

priority:  # Auto-ranked by composite score
  - ticker: NVDA
    score: 78
    action: BUY
```

- User list is manually edited.
- Discovered list is appended by the scanner when a ticker crosses a configurable threshold.
- Priority list is rebuilt each scan cycle, sorted by composite score descending.

## Scheduling

| Job | Schedule (ET) | Configurable |
|-----|--------------|-------------|
| Morning full scan | 9:00 AM, Mon-Fri | Yes |
| Intraday check | Every 30 min, 9:30 AM-4:00 PM, Mon-Fri | Yes |
| EOD recap | 4:30 PM, Mon-Fri | Yes |
| SEC filing scan | Every 2 hours, Mon-Fri | Yes |
| Watchlist refresh | 8:00 AM daily | Yes |

Uses APScheduler with cron triggers. Market-hours awareness via `exchange_calendars` or simple weekday + time checks.

All schedules defined in `config/strategies.yaml` and registered in `scheduler/jobs.py`.

## Alerts

### Always Active
- **File log:** All alerts written to `outputs/logs/alerts.log`
- **Markdown report:** Daily reports in `outputs/reports/YYYY-MM-DD-{morning|eod}.md`
- **JSON output:** Structured data in `outputs/json/YYYY-MM-DD-scan.json`

### Optional (Config-Driven)
- **Telegram:** Bot token + chat ID in `.env`. Sends real-time alerts. Uses `python-telegram-bot` library.
- **Discord:** Webhook URL in `.env`. Sends real-time alerts via Discord webhook (no bot needed, just a channel webhook URL). Uses `requests` (no extra dependency).

### Alert Triggers
- Composite score crosses buy/sell threshold
- Price hits invalidation level for an active recommendation
- New SEC filing on a watched ticker
- Insider transaction on a watched ticker
- Earnings within N days for a watched ticker
- Volume spike > 3x average on a watched ticker

## Backtesting

Uses Lumibot's `YahooDataBacktesting` datasource.

### Default Strategy: MomentumCatalystStrategy

- Entry: composite signal score > configurable buy threshold (default +40)
- Exit: score drops below exit threshold (default +10) or invalidation condition hit
- Position sizing: equal-weight across open positions (configurable)
- Max positions: 10 (configurable)

### Output
- Total return, annualized return
- Sharpe ratio, Sortino ratio
- Max drawdown
- Win rate, profit factor
- Trade log (entry/exit dates, P&L per trade)
- Saved to `backtests/results/` as JSON + markdown summary

### CLI Usage
```bash
python -m stockpulse.backtests.runner --start 2024-01-01 --end 2026-01-01
```

## LLM Integration — AMD Claude API

### Provider
- **API:** AMD internal Claude API at `https://llm-api.amd.com/Anthropic`
- **SDK:** `anthropic` Python package
- **Model:** `Claude-Sonnet-4.6` (default, configurable)
- **Auth:** `ANTHROPIC_API_KEY` from environment

### Use Cases
1. **SEC Filing Summary:** Extracts key risk factors, revenue trends, and material events from 10-K/10-Q/8-K filings
2. **Thesis Generation:** Produces natural language buy/sell/hold thesis from signal data
3. **News Summary:** Condenses news headlines into sentiment assessment
4. **Catalyst Narrative:** Combines earnings, filings, and insider data into readable catalyst summary

### Fallback
If the API is unreachable (VPN down, key expired, network error):
- Rules-based template engine generates summaries from structured signal data
- Templates produce readable but formulaic output
- System continues operating with degraded summary quality
- Degradation is logged and noted in reports

### Config (.env)
```
LLM_ENABLED=true
LLM_BASE_URL=https://llm-api.amd.com/Anthropic
LLM_API_KEY=  # defaults to ANTHROPIC_API_KEY env var
LLM_MODEL=Claude-Sonnet-4.6
```

## Daily Output Cycle

### Morning (9:00 AM ET)
- Full scan of S&P 500 + user watchlist
- Ranked recommendations with buy/sell/hold labels
- Top 10 opportunities highlighted
- SEC filings since last scan
- Earnings calendar for next 14 days
- Markdown report + JSON output + desktop notification

### Intraday (Every 30 min, 9:30-4:00 ET)
- Quick scan of watchlist + active recommendations only
- Alert on threshold crossings or invalidation hits
- Desktop notification for actionable changes only

### End of Day (4:30 PM ET)
- Recap of day's signals and movements
- Updated recommendations with closing data
- Performance of active recommendations
- New discoveries added to watchlist
- Markdown report + JSON output

## Configuration

### .env.example
```env
# Data
YAHOO_RATE_LIMIT=2000        # Max Yahoo API calls per hour
CACHE_TTL_MINUTES=15          # Data cache TTL

# LLM
LLM_ENABLED=true
LLM_BASE_URL=https://llm-api.amd.com/Anthropic
LLM_API_KEY=                  # Defaults to ANTHROPIC_API_KEY
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

### config/strategies.yaml
```yaml
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
  confidence_min: 30    # Don't alert below this

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

## Safety & Decision Policy

- **No real trades by default.** `TRADING_ENABLED=false`, `TRADING_MODE=paper`.
- Recommendations are research ideas, not guaranteed outcomes.
- Low-confidence situations (< 30) are labeled honestly and do not trigger alerts.
- The system does not auto-trade unless explicitly enabled and configured with a broker.

## Dependencies

```
lumibot>=3.0
yfinance>=0.2
edgartools>=2.0
pandas>=2.0
pandas-ta>=0.3
anthropic>=0.40
apscheduler>=3.10
pyyaml>=6.0
python-dotenv>=1.0
jinja2>=3.1
requests>=2.31
pytz>=2024.1
```

## Success Criteria

One command (`python run.py`) produces:
1. A scheduled scan running on cron
2. A ranked watchlist with composite scores
3. Buy/sell/hold recommendations with thesis and invalidation
4. Desktop alerts for triggered conditions
5. Markdown + JSON reports in `outputs/`
6. Backtest capability via `python -m stockpulse.backtests.runner`
