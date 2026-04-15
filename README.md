# StockPulse

Local, self-hosted stock trading intelligence platform. Scans the S&P 500 daily, generates buy/sell/hold recommendations with confidence scores, sends alerts via Telegram, and includes a premium web dashboard.

**Zero subscriptions. Free data only. Runs on your machine.**

## Features

- **Daily S&P 500 scanning** with 11 professionally calibrated signals
- **5-tier classification**: BUY / WATCHLIST / HOLD / CAUTION / SELL
- **Confirmation buckets**: signals must agree across trend, participation, and catalyst categories
- **Risk management**: sector caps, correlation clustering, drawdown breakers, earnings blackout
- **Portfolio tracking**: real-time P&L, milestone alerts, invalidation monitoring
- **Allocation advisor**: AI-powered fund distribution with BUY full positions and WATCHLIST starter positions (33%)
- **Web dashboard**: Dark Glass themed UI with 7 pages, TradingView charts, signal analysis, report viewer
- **Telegram alerts**: get notified when signals trigger, portfolio milestones crossed, new discoveries
- **LLM-powered analysis**: Claude Opus/Sonnet for thesis generation, news classification, SEC filing parsing, allocation rationale
- **Backtesting**: Lumibot-powered strategy backtesting with full tearsheet
- **Statistical validation**: paired t-test, Wilcoxon, bootstrap CI, BUY vs WATCHLIST separation
- **Auto-discovery**: finds new opportunities from the full S&P 500, removes stale ones after 5 days
- **Signal performance tracking**: logs every BUY/WATCHLIST with SPY benchmark, checks 5/10/20-day returns
- **On-demand ticker analysis**: analyze any stock with full signal breakdown and TradingView chart

## Quick Start

```bash
# Clone the repo
git clone https://github.com/NightBaRron1412/stockpulse.git
cd stockpulse

# One-command setup
make setup

# Set your Finnhub API key (free at https://finnhub.io)
# Edit .env and add your key

# Validate everything is working
make check

# Run your first scan
make run
```

## Web Dashboard

```bash
# Start the API backend + web UI
make api    # Terminal 1: FastAPI on port 18000
cd stockpulse-ui && npm run dev -- -H 0.0.0.0 -p 3003  # Terminal 2: Next.js

# Or install as systemd services (auto-start on boot)
make install-service  # Scanner
# API and UI services created separately (see docs)
```

Open `http://localhost:3003` for the dashboard.

**Pages:** Dashboard, Watchlist, Portfolio, Signals, Validation, Reports, Settings, Allocation Advisor

## Commands

| Command | What it does |
|---------|-------------|
| `make setup` | Create venv, install deps, copy config |
| `make check` | Validate API keys and connections |
| `make run` | One-shot scan of S&P 500 + watchlist |
| `make start` | Start the scheduler (continuous scanning) |
| `make stop` | Stop the scheduler |
| `make test` | Run the test suite (102 tests) |
| `make backtest` | Run a 6-month backtest |
| `make api` | Start the FastAPI backend on port 18000 |
| `make status` | Check if the scheduler is running |
| `make install-service` | Install scanner as systemd service |
| `make clean` | Reset all outputs and start fresh |
| `make enter TICKER=GOOGL` | Record a new position with risk checks |

## Configuration

### Required

| Variable | Description |
|----------|-------------|
| `FINNHUB_API_KEY` | Free API key from [finnhub.io](https://finnhub.io). 60 requests/min. |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_ENABLED` | `true` | AI-powered summaries (needs API key) |
| `LLM_API_KEY` | -- | Anthropic API key for Claude |
| `ALERTS_TELEGRAM` | `false` | Enable Telegram alerts |
| `ALERTS_DISCORD` | `false` | Enable Discord alerts |
| `TRADING_ENABLED` | `false` | Paper mode by default |

See `.env.example` for all options with descriptions.

### Watchlist

Edit `stockpulse/config/watchlists.yaml` to add/remove tickers. The scanner auto-discovers new tickers from S&P 500 scans and removes stale ones after 5 days.

### Strategy Tuning

Edit `stockpulse/config/strategies.yaml` to adjust signal weights, thresholds, scheduling, risk limits, and allocation rules. All editable from the web UI Settings page.

## How It Works

```
9:35 AM   Full S&P 500 scan (503+ tickers, ~35 min)
          |-- 11 signals: RSI, MACD, MA, Volume, Breakout, Gap, ADX,
          |               Relative Strength, SEC Filings, News, PEAD
          |-- Weighted composite score -> BUY/WATCHLIST/HOLD/CAUTION/SELL
          |-- Confirmation: 2 of 3 buckets (trend, participation, catalyst)
          |-- Risk check: sector caps, clustering, drawdown, earnings blackout
          |-- Auto-discover new tickers crossing WATCHLIST threshold
          |-- Track BUY/WATCHLIST signals for performance validation
          +-- Alerts -> Telegram + markdown report + web dashboard

9:30-4:00 Intraday checks every 30 min (watchlist + discovered tickers)
          |-- Detect action changes (HOLD -> WATCHLIST, WATCHLIST -> BUY)
          |-- Track signal upgrades/downgrades + flipback detection
          +-- Portfolio P&L monitoring + milestone alerts

Every 2h  SEC filing scan (8-K event classification, Form 4 insider trades)
4:30 PM   EOD recap report
5:00 PM   Signal performance checkpoint (5/10/20-day returns vs SPY)
Sunday    Weekly digest with AI outlook
```

## Allocation Advisor

Enter an investment amount and get a signal-based allocation plan:

- **BUY signals**: full position sizing (8% max per position)
- **WATCHLIST starters**: 33% of BUY size, strict qualifiers required (trend confirms, RS >= 60, no blackout, no cluster breach)
- **Cash reserve**: valid output when no qualified names exist
- Max 3 WATCHLIST starters, 25% sleeve cap, 1 per cluster
- AI-generated rationale (Claude Opus)

Access from Portfolio page or directly at `/allocate`.

## Data Sources

| Source | Data | Cost |
|--------|------|------|
| [Finnhub](https://finnhub.io) | Quotes, news, earnings | Free (API key) |
| [Yahoo Finance](https://finance.yahoo.com) | Historical OHLCV | Free |
| [SEC EDGAR](https://www.sec.gov/edgar) | 8-K, 10-K, Form 4, insider trades | Free |
| Claude API | AI summaries, news classification, allocation rationale | Optional |

### Limitations

- Finnhub free tier: 60 calls/min (full scan takes ~35 min)
- No real-time streaming
- No analyst ratings (paywalled)
- Insider role-weighting limited by EdgarTools metadata

## Running as Services

```bash
# Scanner (scans, alerts, Telegram)
make install-service
systemctl --user start stockpulse

# API (FastAPI backend on port 18000)
systemctl --user start stockpulse-api

# Web UI (Next.js on port 3003)
systemctl --user start stockpulse-ui

# Check all services
systemctl --user status stockpulse stockpulse-api stockpulse-ui

# View logs
journalctl --user -u stockpulse -f
journalctl --user -u stockpulse-api -f
```

All services auto-start on boot and restart on crashes.

## Testing

```bash
make test  # 102 tests covering signals, API, allocation, discovery, LLM, intraday
```

## Backtesting

```bash
# Default: last 6 months
make backtest

# Custom date range
python run.py backtest --start 2024-01-01 --end 2025-12-31
```

Results include: total return, Sharpe/Sortino ratios, max drawdown, trade log, and comparison to SPY. Viewable from Settings page in the web UI.

## Safety

- **Paper mode by default** -- no real trades unless explicitly enabled
- **Research only** -- recommendations are ideas, not financial advice
- **Low-confidence signals suppressed** -- only high-conviction alerts reach you
- **Risk limits enforced** -- 8% per position, 25% per sector, drawdown breakers
- **Allocation rules** -- BUY = full size, WATCHLIST = 33% starter with strict qualifiers

## License

MIT License. See [LICENSE](LICENSE).
