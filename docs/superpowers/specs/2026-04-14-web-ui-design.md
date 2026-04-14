# StockPulse Web UI — Design Spec

**Date:** 2026-04-14
**Status:** Design

## Overview

Premium web dashboard for the StockPulse trading intelligence system. Dark Glass aesthetic, top navigation, 7 pages, real-time scan status, markdown report rendering, on-demand ticker analysis, and live activity feed.

## Stack

- **Frontend:** Next.js 15 (App Router) + TypeScript + Tailwind CSS + shadcn/ui
- **Backend:** FastAPI (Python) wrapping existing StockPulse modules
- **Markdown:** react-markdown + remark-gfm with custom Dark Glass components
- **Charts:** Recharts (lightweight, composable)
- **Location:** `stockpulse-ui/` for Next.js, `stockpulse/api/` for FastAPI server

## Visual Design — Dark Glass

- **Background:** `#0f172a` base, subtle gradient to `#1e293b`
- **Cards:** `rgba(30, 41, 59, 0.5)` with `backdrop-filter: blur(12px)`, `border: 1px solid rgba(51, 65, 85, 0.5)`
- **Action colors:**
  - BUY: `#4ade80` bg `rgba(34, 197, 94, 0.15)` border `rgba(34, 197, 94, 0.2)`
  - WATCHLIST: `#60a5fa` bg `rgba(59, 130, 246, 0.15)` border `rgba(59, 130, 246, 0.2)`
  - HOLD: `#94a3b8` neutral
  - CAUTION: `#fb923c` bg `rgba(251, 146, 56, 0.15)` border `rgba(251, 146, 56, 0.2)`
  - SELL: `#f87171` bg `rgba(239, 68, 68, 0.15)` border `rgba(239, 68, 68, 0.2)`
  - HIGH CONVICTION: Gold glow `#fbbf24`
- **Typography:** Inter for UI text, JetBrains Mono for numbers/scores/data
- **Spacing:** 4px base grid, generous padding on cards (20-24px)
- **Transitions:** 150ms ease for hovers, 200ms for page transitions

## Layout — Top Navigation

```
┌─────────────────────────────────────────────────────────────────────┐
│  [Logo] StockPulse   Dashboard  Watchlist  Portfolio  Signals       │
│                      Validation  Reports  Settings    [Bell] [Scan] │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│                         Page Content                                │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

- **Logo:** "StockPulse" with gradient text or small icon
- **Tabs:** 7 pages, active tab has blue underline
- **Bell icon:** Notification count badge, opens dropdown with recent alerts
- **Scan indicator:** Green dot = idle, pulsing blue = scanning, shows "Scanning 150/506..." when active

## Pages

### 1. Dashboard

The landing page. At-a-glance view of everything important.

**Sections:**

**Top stats row (4 cards):**
- Portfolio P&L: `+$154.69 (+2.17%)` with sparkline
- Active signals: `42 WATCHLIST` / `0 BUY` / `1 CAUTION`
- Model status: `Collecting (40 signals tracked)` with phase badge
- Next scan: Countdown timer to next scheduled job

**Top signals table (main area):**
- Top 10 ranked tickers from latest scan
- Columns: Rank, Ticker, Action (colored badge), Score (bar), Confidence, Thesis (truncated), Buckets (2/3 dots)
- Click row to navigate to Signals page for that ticker

**Activity feed (right panel or below):**
- Timeline of all system events: scan starts/completions, action changes, portfolio milestones, SEC alerts, discoveries
- Each entry: timestamp, icon, description
- Auto-refreshes every 30 seconds

**Portfolio mini-view:**
- Compact position list: ticker, P&L %, P&L $, current price
- Total P&L prominently displayed

### 2. Watchlist

Full table of all tracked tickers (user + discovered).

**Features:**
- Sortable columns: Ticker, Action, Score, Confidence, RS, MACD, Volume, Sector
- Filter by action: BUY / WATCHLIST / HOLD / CAUTION / SELL / All
- Search/filter by ticker name
- "User" vs "Discovered" toggle or badge
- Click any row to expand inline detail panel showing all 11 signals
- Add/remove tickers (+ button, X on discovered tickers)
- Bulk actions: remove all stale discovered

**Columns:**
| Ticker | Action | Score | Conf | RS | Buckets | Sector | Source |
|--------|--------|-------|------|----|---------|--------|--------|

### 3. Portfolio

Position management and P&L tracking.

**Top stats:**
- Total invested, total current, total P&L ($ and %), drawdown gauge

**Positions table:**
| Ticker | Shares | Entry | Current | P&L % | P&L $ | Stop | Status |
|--------|--------|-------|---------|-------|-------|------|--------|

- Status column shows signal action for held tickers (HOLD, CAUTION, etc.)
- Expandable rows show entry date, thesis at entry, invalidation levels

**Sector exposure:**
- Donut chart showing sector allocation
- Cluster visualization (which tickers are correlated)

**Risk panel:**
- Drawdown status bar (-8% yellow, -12% red)
- Max positions used (4/8)
- Sector concentration bars

### 4. Signals

Deep analysis view for individual tickers.

**Search bar at top:** Type any ticker (even not on watchlist), runs analysis on demand

**Ticker detail view:**
- Header: Ticker, price, change, action badge, composite score (large)
- Thesis text (full, LLM-generated)
- Invalidation levels with price markers

**Signal breakdown:**
- Bar chart or radar chart showing all 11 signals (score x weight = contribution)
- Each signal expandable: raw value, score, weight, weighted contribution
- Color-coded: green = bullish contribution, red = bearish

**Confirmation buckets:**
- 3 visual buckets (Trend, Participation, Catalyst) with check/cross
- Each bucket shows its constituent signals and average score

**Risk check panel:**
- Would this position be allowed? Sector/cluster/concentration check
- Suggested position size (ATR-based)

### 5. Validation

Statistical validation dashboard.

**Phase indicator:**
- Large badge: PILOT / MEANINGFUL / SERIOUS / VALIDATED
- Progress bar: 40/100 BUY signals needed for next phase

**Stats table:**
| Period | Signals | Avg Return | Excess vs SPY | Hit Rate | Rel Hit Rate |
|--------|---------|-----------|---------------|----------|-------------|

**Statistical tests panel:**
- Paired t-test result with p-value and significance indicator
- Wilcoxon signed-rank
- Binomial hit rate with Wilson 95% CI visualized as a range bar
- Bootstrap 95% CI for mean excess return
- BUY vs WATCHLIST separation

**Verdict box:**
- "MODEL IS WORKING" (green) or "NEEDS CALIBRATION" (orange) or "COLLECTING DATA" (blue)
- Checklist of criteria: mean excess > 0.75%, hit rate >= 55%, etc.

**Recent signals table:**
| Date | Ticker | Action | Entry | Score | 5d | 10d | 20d |
|------|--------|--------|-------|-------|-----|------|------|

### 6. Reports

Chronological report browser with markdown rendering.

**Left panel:** List of all reports
- Grouped by date
- Filter by type: Morning, EOD, Intraday, Weekly Digest
- Badge showing report type
- Click to select

**Right panel:** Rendered markdown
- Full GitHub-flavored markdown rendering styled in Dark Glass theme
- Tables with alternating dark rows
- Code blocks with syntax highlighting
- P&L numbers color-coded (green/red)
- Headings styled with subtle gradient underlines

### 7. Settings

Configuration and controls.

**Watchlist management:**
- Add/remove user tickers
- View discovered tickers with option to promote to user or remove

**Strategy parameters:**
- Read-only view of current signal weights, thresholds
- Displayed as a visual config summary (not raw YAML)

**Alert status:**
- Telegram: connected/disconnected, last alert sent
- Discord: connected/disconnected
- Log file: last entry

**Manual controls:**
- "Run Full Scan Now" button with progress indicator
- "Run Ticker Analysis" quick input

**System status:**
- Service uptime
- Scheduler jobs with next run times
- Cache size and last cleanup

## Top Bar Components

**Notification bell:**
- Dropdown showing last 20 alerts from alerts.log
- Grouped by type (recommendation, portfolio, discovery, SEC)
- Unread count badge
- "Mark all read" action

**Scan status indicator:**
- Idle: Green dot + "Last scan: 10:10 AM"
- Running: Pulsing blue dot + "Scanning 150/506..."
- Error: Red dot + "Scan failed"

## API Endpoints (FastAPI)

### Read endpoints
```
GET  /api/dashboard           → {portfolio, top_signals, activity, scan_status, stats}
GET  /api/watchlist            → [{ticker, action, score, confidence, signals, sector, source}]
GET  /api/watchlist/{ticker}   → {full recommendation dict with all signals}
GET  /api/portfolio            → {positions, totals, sector_exposure, risk_status}
GET  /api/validation           → {stats, validation tests, recent signals, verdict}
GET  /api/reports              → [{filename, date, type, title}]
GET  /api/reports/{filename}   → {content: "rendered markdown string"}
GET  /api/alerts/recent        → [{timestamp, ticker, action, thesis, type}]
GET  /api/scan/status          → {running, progress, last_completed, next_scheduled}
GET  /api/quote/{ticker}       → {price, change, change_pct, high, low, open}
GET  /api/history/{ticker}     → {dates, prices, volumes} for chart rendering
GET  /api/config               → {signals, thresholds, risk, scheduling}
GET  /api/activity             → [{timestamp, type, message}] last 50 system events
```

### Write endpoints
```
POST /api/scan                 → trigger manual full scan, returns job ID
POST /api/analyze/{ticker}     → run on-demand analysis, returns full recommendation
POST /api/watchlist/add        → {ticker} add to user watchlist
POST /api/watchlist/remove     → {ticker} remove from watchlist
```

## Data Flow

```
StockPulse Python Modules (existing, unchanged)
    ↓ direct imports
FastAPI Server (stockpulse/api/server.py)
    ↓ REST JSON responses
Next.js Frontend (stockpulse-ui/)
    ↓ rendered pages
Browser
```

- FastAPI imports and calls existing functions: `get_portfolio_status()`, `generate_recommendation()`, `load_watchlists()`, etc.
- No database. Reads YAML configs, JSON state files, and scan output files directly.
- Polling interval: 30 seconds for dashboard/activity, 5 seconds during active scan.

## File Structure

```
stockpulse-ui/                    # Next.js app
├── package.json
├── tailwind.config.ts
├── next.config.ts
├── app/
│   ├── layout.tsx                # Root layout with nav
│   ├── page.tsx                  # Dashboard
│   ├── watchlist/page.tsx
│   ├── portfolio/page.tsx
│   ├── signals/page.tsx
│   ├── validation/page.tsx
│   ├── reports/page.tsx
│   └── settings/page.tsx
├── components/
│   ├── nav/                      # Top navigation, notification bell, scan status
│   ├── dashboard/                # Stats cards, top signals table, activity feed
│   ├── watchlist/                # Ticker table, filters, signal detail panel
│   ├── portfolio/                # Positions table, sector chart, risk panel
│   ├── signals/                  # Signal bar chart, buckets, ticker search
│   ├── validation/               # Stats table, test results, verdict
│   ├── reports/                  # Report list, markdown renderer
│   ├── settings/                 # Config panels, manual controls
│   └── ui/                       # shadcn/ui components
├── lib/
│   ├── api.ts                    # API client functions
│   ├── types.ts                  # TypeScript interfaces matching Python data models
│   └── utils.ts                  # Formatters, color helpers
└── hooks/
    ├── use-polling.ts            # Auto-refresh hook with configurable interval
    └── use-scan-status.ts        # Scan status polling

stockpulse/api/                   # FastAPI server (inside existing Python package)
├── __init__.py
├── server.py                     # FastAPI app with all routes
├── models.py                     # Pydantic models matching existing data shapes
└── scan_manager.py               # Background scan management
```

## Running

```bash
# Start FastAPI backend
uvicorn stockpulse.api.server:app --port 8000

# Start Next.js frontend (separate terminal)
cd stockpulse-ui && npm run dev

# Or via Makefile
make ui        # starts both
```

## Responsive Behavior

- Desktop (>1024px): Full layout, side panels visible
- Tablet (768-1024px): Stacked layout, collapsible panels
- Mobile (<768px): Single column, bottom tab navigation, swipeable cards
