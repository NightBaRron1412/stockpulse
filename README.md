<div align="center">
  <img src="stockpulse-ui/public/favicon.svg" alt="StockPulse" width="80" />
  <h1>StockPulse</h1>
  <p><strong>Local stock trading intelligence platform</strong></p>
  <p>
    <img src="https://img.shields.io/badge/python-3.12+-blue?style=flat-square" alt="Python" />
    <img src="https://img.shields.io/badge/next.js-16-black?style=flat-square" alt="Next.js" />
    <img src="https://img.shields.io/badge/tests-102%20passing-brightgreen?style=flat-square" alt="Tests" />
    <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License" />
    <img src="https://img.shields.io/badge/data-free%20only-orange?style=flat-square" alt="Free Data" />
  </p>
  <p>Scans the S&P 500 daily, generates buy/sell/hold recommendations with confidence scores, sends Telegram alerts, and includes a premium Dark Glass web dashboard.</p>
  <p><strong>Zero subscriptions. Free data only. Self-hosted.</strong></p>
</div>

---

## Dashboard

<p align="center">
  <img src="stockpulse-ui/public/screenshots/dashboard.png" alt="Dashboard" width="100%" />
</p>

## Watchlist

<p align="center">
  <img src="stockpulse-ui/public/screenshots/watchlist.png" alt="Watchlist" width="100%" />
</p>

## Signal Analysis

<p align="center">
  <img src="stockpulse-ui/public/screenshots/signals.png" alt="Signal Analysis" width="100%" />
</p>

---

## Features

**Scanning & Signals**
- Daily S&P 500 scanning with 11 professionally calibrated signals
- 5-tier classification: BUY / WATCHLIST / HOLD / CAUTION / SELL
- Confirmation buckets: signals must agree across trend, participation, and catalyst
- Auto-discovery of new opportunities, stale tickers removed after 5 days

**Risk Management**
- Sector caps (25%), position limits (8%), correlation clustering
- Drawdown breakers (-8% half size, -12% pause)
- Earnings blackout (3-day no-entry window)
- ATR-based position sizing and stop levels

**Portfolio & Allocation**
- Real-time P&L tracking with milestone alerts
- Allocation advisor: BUY = full position, WATCHLIST = 33% starter with strict qualifiers
- AI-generated allocation rationale (Claude Opus)

**Web Dashboard**
- Dark Glass themed UI with 7 pages + allocation advisor
- TradingView chart integration with signal overlay
- Markdown report viewer, sortable tables, collapsible sections
- Responsive with PWA support

**Alerts & Validation**
- Telegram alerts for signals, portfolio milestones, discoveries
- Statistical validation: paired t-test, Wilcoxon, bootstrap CI, BUY vs WATCHLIST separation
- Signal performance tracking: 5/10/20-day returns vs SPY benchmark
- Flipback detection for BUY signals that revert

**LLM Integration**
- Claude Sonnet for scanning (news sentiment, SEC filing classification, thesis)
- Claude Opus for allocation advice
- Rules-based fallback when LLM unavailable

## Quick Start

```bash
git clone https://github.com/NightBaRron1412/stockpulse.git
cd stockpulse

make setup                    # Create venv, install deps
# Edit .env — set FINNHUB_API_KEY (free at https://finnhub.io)
make check                    # Validate setup
make run                      # Run first scan
```

## Web Dashboard

```bash
make api                      # Start API (port 18000)
cd stockpulse-ui && npm i && npm run dev -- -H 0.0.0.0 -p 3003
```

Or install as systemd services for auto-start:

```bash
make install-service          # Scanner
systemctl --user start stockpulse-api stockpulse-ui
```

## Commands

| Command | Description |
|---------|-------------|
| `make setup` | Create venv, install deps, copy config |
| `make check` | Validate API keys and connections |
| `make run` | One-shot S&P 500 scan |
| `make test` | Run 102 tests |
| `make api` | Start FastAPI backend |
| `make backtest` | Run 6-month backtest |
| `make install-service` | Install as systemd service |
| `make enter TICKER=GOOGL` | Record position with risk checks |

## Architecture

```
Scanner (systemd)          FastAPI (port 18000)        Next.js (port 3003)
    |                           |                           |
    |-- 9:35 AM scan       <-- REST API -->            Dark Glass UI
    |-- 30min intraday         |                       7 pages + allocator
    |-- 4:30 PM EOD            |-- /api/dashboard      TradingView charts
    |-- 2h SEC scan            |-- /api/watchlist      Signal breakdown
    |-- 30min portfolio        |-- /api/portfolio      Report viewer
    |-- 5 PM validation        |-- /api/signals        Notification bell
    |-- Sun weekly digest      |-- /api/allocate       Settings editor
    |                          |-- /api/validation
    v                          v
  Telegram              outputs/reports/
  alerts.log            outputs/json/
```

## Data Sources

| Source | Data | Cost |
|--------|------|------|
| [Finnhub](https://finnhub.io) | Quotes, news, earnings | Free |
| [Yahoo Finance](https://finance.yahoo.com) | Historical OHLCV | Free |
| [SEC EDGAR](https://www.sec.gov/edgar) | 8-K, 10-K, Form 4 | Free |
| Claude API | AI analysis | Optional |

## Configuration

All configurable from the web UI Settings page or via YAML files:

- `stockpulse/config/strategies.yaml` — signal weights, thresholds, risk, allocation rules
- `stockpulse/config/watchlists.yaml` — user tickers + auto-discovered
- `stockpulse/config/portfolio.yaml` — positions (gitignored)
- `.env` — API keys, alert toggles

## Safety

- Paper mode by default
- Research only — not financial advice
- Risk limits enforced (8% position, 25% sector, drawdown breakers)
- BUY = full position, WATCHLIST = 33% starter with strict qualifiers

## License

MIT License. See [LICENSE](LICENSE).
