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
# Edit .env -- set FINNHUB_API_KEY (free at https://finnhub.io)
# Telegram/Discord alerts are optional

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
Edit `stockpulse/config/strategies.yaml` to adjust signal weights, thresholds, schedules, backtest params.

### Alerts
Set in `.env`:
- `ALERTS_TELEGRAM=true` + `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`
- `ALERTS_DISCORD=true` + `DISCORD_WEBHOOK_URL`

### LLM
Uses AMD Claude API by default. Set `LLM_ENABLED=false` to use rules-based fallback.

## Data Sources

| Source | Data | Cost |
|--------|------|------|
| Finnhub | Price, volume, quotes, earnings, news | Free (API key required) |
| SEC EDGAR | 10-K, 10-Q, 8-K, insider trades (Form 4) | Free |
| AMD Claude API | Summarization, thesis generation | Internal |

### Limitations
- Finnhub free tier: 60 API calls/min. Full S&P 500 scan takes ~9 minutes.
- News sentiment: keyword-based on Finnhub headlines -- low confidence.
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
