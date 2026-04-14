# StockPulse

Local, self-hosted stock research and alert system. Scans the S&P 500 daily, generates buy/sell/hold recommendations with confidence scores, and alerts you via Telegram or Discord.

**Zero subscriptions. Free data only. Runs on your machine.**

## Features

- **Daily S&P 500 scanning** with 11 professionally calibrated signals
- **5-tier classification**: BUY / WATCHLIST / HOLD / CAUTION / SELL
- **Confirmation buckets**: signals must agree across trend, participation, and catalyst categories
- **Risk management**: sector caps, correlation clustering, drawdown breakers, earnings blackout
- **Portfolio tracking**: real-time P&L, milestone alerts, invalidation monitoring
- **Telegram/Discord alerts**: get notified when signals trigger
- **LLM-powered analysis**: AI-generated thesis, news classification, SEC filing parsing
- **Backtesting**: Lumibot-powered strategy backtesting with full tearsheet
- **Statistical validation**: paired t-test, Wilcoxon, bootstrap CI, Wilson intervals
- **Auto-discovery**: finds new opportunities from the full S&P 500

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

## Commands

| Command | What it does |
|---------|-------------|
| `make setup` | Create venv, install deps, copy config |
| `make check` | Validate API keys and connections |
| `make run` | One-shot scan of S&P 500 + watchlist |
| `make start` | Start the scheduler (continuous scanning) |
| `make stop` | Stop the scheduler |
| `make test` | Run the test suite |
| `make backtest` | Run a 6-month backtest |
| `make status` | Check if the scheduler is running |
| `make install-service` | Install as systemd service (auto-start on boot) |
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
| `LLM_API_KEY` | — | Anthropic API key for Claude |
| `ALERTS_TELEGRAM` | `false` | Enable Telegram alerts |
| `ALERTS_DISCORD` | `false` | Enable Discord alerts |
| `TRADING_ENABLED` | `false` | Paper mode by default |

See `.env.example` for all options with descriptions.

### Watchlist

Edit `stockpulse/config/watchlists.yaml` to add/remove tickers:

```yaml
user:
  - AAPL
  - NVDA
  - GOOGL
  # add your tickers here
```

### Strategy Tuning

Edit `stockpulse/config/strategies.yaml` to adjust signal weights, thresholds, and scheduling.

## How It Works

```
9:35 AM   Full S&P 500 scan (503+ tickers, ~35 min)
          ├─ 11 signals: RSI, MACD, MA, Volume, Breakout, Gap, ADX,
          │              Relative Strength, SEC Filings, News, PEAD
          ├─ Weighted composite score → BUY/WATCHLIST/HOLD/CAUTION/SELL
          ├─ Confirmation: 2 of 3 buckets (trend, participation, catalyst)
          ├─ Risk check: sector caps, clustering, drawdown, earnings blackout
          ├─ Auto-discover new tickers crossing WATCHLIST threshold
          └─ Alerts → Telegram/Discord + markdown report

9:30-4:00 Intraday checks every 30 min (watchlist + discovered tickers)
          ├─ Detect action changes (HOLD → WATCHLIST, etc.)
          └─ Portfolio P&L monitoring + milestone alerts

Every 2h  SEC filing scan (8-K, Form 4 on watchlist tickers)
4:30 PM   EOD recap report
5:00 PM   Signal performance checkpoint (tracks 5/10/20-day returns vs SPY)
Sunday    Weekly digest with AI outlook
```

## Data Sources

| Source | Data | Cost |
|--------|------|------|
| [Finnhub](https://finnhub.io) | Quotes, news, earnings | Free (API key) |
| [Yahoo Finance](https://finance.yahoo.com) | Historical OHLCV | Free |
| [SEC EDGAR](https://www.sec.gov/edgar) | 8-K, 10-K, Form 4, insider trades | Free |
| Claude API | AI summaries, news classification | Optional |

### Limitations

- Finnhub free tier: 60 calls/min (full scan takes ~35 min)
- No real-time streaming
- No analyst ratings (paywalled)
- Insider role-weighting limited by EdgarTools metadata

## Running as a Service

```bash
# Install as a systemd user service
make install-service

# Start it
systemctl --user start stockpulse

# Check status
make status

# View live logs
journalctl --user -u stockpulse -f

# Stop
make stop
```

The service auto-starts on boot and restarts on crashes.

## Backtesting

```bash
# Default: last 6 months
make backtest

# Custom date range
python run.py backtest --start 2024-01-01 --end 2025-12-31
```

Results include: total return, Sharpe/Sortino ratios, max drawdown, trade log, and comparison to SPY.

## Safety

- **Paper mode by default** — no real trades unless explicitly enabled
- **Research only** — recommendations are ideas, not financial advice
- **Low-confidence signals suppressed** — only high-conviction alerts reach you
- **Risk limits enforced** — 8% per position, 25% per sector, drawdown breakers

## License

MIT License. See [LICENSE](LICENSE).
