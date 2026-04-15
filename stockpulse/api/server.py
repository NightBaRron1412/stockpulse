"""FastAPI server wrapping StockPulse modules."""
import json
import logging
import threading
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="StockPulse API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _read_json(path: Path) -> dict | list:
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def _get_latest_scan() -> list[dict]:
    """Get recommendations from the most recent scan JSON file, filtered by active filters."""
    json_dir = PROJECT_ROOT / "outputs" / "json"
    if not json_dir.exists():
        return []
    files = sorted(json_dir.glob("*.json"), reverse=True)
    recs = []
    for f in files:
        try:
            data = _read_json(f)
            if isinstance(data, dict) and "recommendations" in data:
                recs = data.get("recommendations", [])
                break
        except Exception:
            continue

    # Apply Shariah filter if enabled (fast — hardcoded lists + cache only)
    from stockpulse.config.settings import load_strategies
    if load_strategies().get("filters", {}).get("shariah_only", False):
        from stockpulse.filters.shariah import is_compliant_fast
        recs = [r for r in recs if is_compliant_fast(r.get("ticker", ""))]

    return recs


def _parse_activity_log() -> list[dict]:
    """Parse system log into clean, human-readable activity events."""
    log_path = PROJECT_ROOT / "outputs" / "logs" / "stockpulse.log"
    if not log_path.exists():
        return []
    events = []
    try:
        lines = log_path.read_text().strip().split("\n")
        for line in lines[-500:]:
            ts = line[:19]  # "2026-04-14 09:35:00"
            # Only process meaningful events, skip APScheduler noise
            if "MORNING SCAN START" in line:
                events.append({"timestamp": ts, "type": "scan", "message": "Morning scan started"})
            elif "Scan complete:" in line:
                try:
                    msg = line.split("Scan complete: ")[1].split(".")[0]
                    events.append({"timestamp": ts, "type": "scan", "message": f"Scan complete — {msg}"})
                except Exception:
                    events.append({"timestamp": ts, "type": "scan", "message": "Scan completed"})
            elif "Scanned " in line and "/" in line:
                try:
                    progress = line.split("Scanned ")[1].split(" ")[0]
                    events.append({"timestamp": ts, "type": "scan", "message": f"Scanning... {progress}"})
                except Exception:
                    pass
            elif "Morning scan complete:" in line:
                try:
                    msg = line.split("Morning scan complete: ")[1].split(". Report:")[0]
                    events.append({"timestamp": ts, "type": "scan", "message": f"Morning scan: {msg}"})
                except Exception:
                    pass
            elif "changes detected" in line and "no " not in line:
                try:
                    count = line.split("Intraday: ")[1].split(" ")[0]
                    events.append({"timestamp": ts, "type": "alert", "message": f"Intraday: {count} signal changes detected"})
                except Exception:
                    events.append({"timestamp": ts, "type": "alert", "message": "Intraday changes detected"})
            elif "Auto-discovered" in line:
                try:
                    msg = line.split("Auto-discovered ")[1]
                    events.append({"timestamp": ts, "type": "alert", "message": f"Discovered {msg[:80]}"})
                except Exception:
                    events.append({"timestamp": ts, "type": "alert", "message": "New tickers discovered"})
            elif "milestone alerts" in line:
                try:
                    msg = line.split("Portfolio check: ")[1]
                    if "0 milestone" not in msg or "0 invalidation" not in msg:
                        events.append({"timestamp": ts, "type": "portfolio", "message": f"Portfolio: {msg[:80]}"})
                except Exception:
                    pass
            elif "EOD RECAP START" in line:
                events.append({"timestamp": ts, "type": "scan", "message": "EOD recap started"})
            elif "EOD recap complete" in line:
                events.append({"timestamp": ts, "type": "scan", "message": "EOD recap completed"})
            elif "WEEKLY DIGEST" in line:
                events.append({"timestamp": ts, "type": "system", "message": "Weekly digest generated"})
            elif "SEC filing scan" in line and "---" in line:
                events.append({"timestamp": ts, "type": "system", "message": "SEC filing scan started"})
            elif "Auto-removed" in line:
                try:
                    msg = line.split("Auto-removed ")[1]
                    events.append({"timestamp": ts, "type": "system", "message": f"Removed {msg[:80]}"})
                except Exception:
                    pass
    except Exception:
        pass
    return list(reversed(events[-30:]))


def _get_scan_status() -> dict:
    """Check if a scan or job is currently running."""
    log_path = PROJECT_ROOT / "outputs" / "logs" / "stockpulse.log"
    last_completed = "Never"
    running = False
    progress = ""
    current_job = ""
    if log_path.exists():
        try:
            # Read only last 100 lines for performance
            with open(log_path) as f:
                lines = f.readlines()[-100:]

            # Walk backwards: find the latest completion and latest start
            latest_complete_ts = ""
            latest_start_ts = ""
            latest_progress = ""

            for line in reversed(lines):
                ts = line[:19] if len(line) >= 19 else ""

                if ("Scan complete" in line or "Morning scan complete" in line) and not latest_complete_ts:
                    latest_complete_ts = ts
                    last_completed = ts

                if ("MORNING SCAN START" in line or "Starting full scan" in line) and not latest_start_ts:
                    latest_start_ts = ts
                    current_job = "Morning Scan"

                if "Scanned " in line and "/" in line and not latest_progress:
                    try:
                        latest_progress = line.split("Scanned ")[1].split(" ")[0]
                    except Exception:
                        pass

            # Running = started after last completed
            if latest_start_ts and (not latest_complete_ts or latest_start_ts > latest_complete_ts):
                running = True
                progress = latest_progress
            else:
                # Check recent lines for short jobs (intraday, portfolio, SEC)
                recent = lines[-5:] if len(lines) >= 5 else lines
                started_job = None
                for line in recent:
                    if "--- Intraday check ---" in line:
                        started_job = "Intraday Check"
                    elif "--- Portfolio check ---" in line:
                        started_job = "Portfolio Check"
                    elif "--- SEC filing scan ---" in line:
                        started_job = "SEC Scan"
                    elif "executed successfully" in line or "no changes" in line or "complete" in line:
                        started_job = None
                if started_job:
                    running = True
                    current_job = started_job
        except Exception:
            pass
    return {
        "running": running,
        "progress": progress if running else current_job,
        "last_completed": last_completed,
        "next_scheduled": "09:35 ET",
    }


# ═══════════════════════════════════════════════════
# Dashboard
# ═══════════════════════════════════════════════════

@app.get("/api/dashboard")
def get_dashboard():
    from stockpulse.portfolio.tracker import get_portfolio_status
    portfolio = get_portfolio_status()
    all_recs = _get_latest_scan()
    top_signals = sorted(all_recs, key=lambda r: abs(r.get("composite_score", 0)), reverse=True)[:10]
    counts = {}
    for r in all_recs:
        a = r.get("action", "HOLD")
        counts[a] = counts.get(a, 0) + 1
    return {
        "portfolio": portfolio,
        "top_signals": top_signals,
        "activity": _parse_activity_log(),
        "scan_status": _get_scan_status(),
        "signal_count": counts,
        "total_scanned": len(all_recs),
    }


# ═══════════════════════════════════════════════════
# Watchlist
# ═══════════════════════════════════════════════════

@app.get("/api/watchlist")
def get_watchlist():
    from stockpulse.config.settings import load_watchlists
    wl = load_watchlists()
    all_recs = _get_latest_scan()
    recs_map = {r["ticker"]: r for r in all_recs}
    result = []
    seen = set()
    for ticker in wl.get("user", []):
        rec = recs_map.get(ticker, {"ticker": ticker, "action": "UNKNOWN", "composite_score": 0, "confidence": 0})
        rec["source"] = "user"
        result.append(rec)
        seen.add(ticker)
    for ticker in wl.get("discovered", []):
        if ticker not in seen:
            rec = recs_map.get(ticker, {"ticker": ticker, "action": "UNKNOWN", "composite_score": 0, "confidence": 0})
            rec["source"] = "discovered"
            result.append(rec)
            seen.add(ticker)
    result.sort(key=lambda x: x.get("composite_score", 0), reverse=True)
    return result


@app.get("/api/watchlist/{ticker}")
def get_watchlist_ticker(ticker: str):
    from stockpulse.data.provider import get_price_history
    from stockpulse.research.recommendation import generate_recommendation
    df = get_price_history(ticker.upper(), period="1y")
    if df.empty:
        raise HTTPException(404, f"No data for {ticker}")
    return generate_recommendation(ticker.upper(), df)


# ═══════════════════════════════════════════════════
# Portfolio
# ═══════════════════════════════════════════════════

@app.get("/api/portfolio")
def get_portfolio():
    from stockpulse.portfolio.tracker import get_portfolio_status
    from stockpulse.portfolio.risk import check_drawdown_status
    from stockpulse.config.settings import load_portfolio
    status = get_portfolio_status()
    peak = max(status["total_current"], status["total_invested"]) if status["total_invested"] > 0 else 1
    dd = check_drawdown_status(status["total_current"], peak)
    port = load_portfolio()
    cash = port.get("cash", 0)
    return {**status, "drawdown": dd, "cash": cash}

@app.get("/api/portfolio/lots/{ticker}")
def get_portfolio_lots(ticker: str):
    from stockpulse.portfolio.lots import get_lots, compute_lot_tax_info
    from stockpulse.data.provider import get_latest_price
    lots = get_lots(ticker.upper())
    if not lots:
        raise HTTPException(404, f"No lots for {ticker}")
    try:
        price = get_latest_price(ticker.upper())
    except Exception:
        price = 0
    return {
        "ticker": ticker.upper(),
        "current_price": price,
        "lots": [compute_lot_tax_info(lot, price) for lot in lots],
    }

@app.post("/api/portfolio/cash")
def update_cash(data: dict):
    """Update cash balance in portfolio."""
    from stockpulse.config.settings import load_portfolio
    import yaml
    cash = data.get("cash", 0)
    if not isinstance(cash, (int, float)) or cash < 0:
        raise HTTPException(400, "cash must be a non-negative number")
    port_path = PROJECT_ROOT / "stockpulse" / "config" / "portfolio.yaml"
    port = load_portfolio()
    port["cash"] = round(float(cash), 2)
    with open(port_path, "w") as f:
        yaml.dump(port, f, default_flow_style=False, sort_keys=False)
    return {"status": "updated", "cash": port["cash"]}


# ═══════════════════════════════════════════════════
# Portfolio Import & Manual Edit
# ═══════════════════════════════════════════════════

_TICKER_ALIASES = {"GOLD": "GLD"}  # Wealthsimple gold → GLD proxy


def _parse_wealthsimple_text(text: str) -> list[dict]:
    """Parse pasted Wealthsimple portfolio text into positions.

    Wealthsimple format per position block:
      TICKER
      Company Name
      Account Tag
      $VALUE CURRENCY    <- total value of position
      QUANTITY shares/ounces
      ... return lines ...
      $PRICE CURRENCY    <- per-share price
      ... price change ...
      Buy
      Sell
    """
    import re
    lines = text.strip().split("\n")
    positions = []

    # Find all ticker positions by looking for "Buy\nSell" markers
    # and working backwards to find the ticker
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Look for standalone ticker (all caps, 1-5 chars)
        ticker_match = re.match(r'^([A-Z]{1,5})$', line)
        if not ticker_match:
            i += 1
            continue

        ticker = ticker_match.group(1)
        # Skip if it's "Buy" or "Sell" or common non-ticker words
        if ticker in ("Buy", "Sell", "USD", "CAD", "ETF"):
            i += 1
            continue

        ticker = _TICKER_ALIASES.get(ticker, ticker)

        # Collect all lines until next standalone ticker or end
        block_lines = []
        j = i + 1
        while j < len(lines):
            bl = lines[j].strip()
            # Stop at next ticker (but not at "Buy"/"Sell")
            if re.match(r'^[A-Z]{1,5}$', bl) and bl not in ("Buy", "Sell", "USD", "CAD", "ETF"):
                # Check if it looks like a company name follows
                if j + 1 < len(lines) and not re.match(r'^[A-Z]{1,5}$', lines[j + 1].strip()):
                    break
            block_lines.append(bl)
            j += 1

        # Parse block: first $XXX is total value, first "N shares" is quantity
        total_value = None
        shares = None
        currency = "USD"

        for bl in block_lines:
            # Value: "$134.47 USD" or "$2,323.80 CAD"
            val_match = re.match(r'^\$([0-9,]+\.?\d*)\s*(USD|CAD)', bl)
            if val_match and total_value is None:
                total_value = float(val_match.group(1).replace(",", ""))
                currency = val_match.group(2)

            # Shares: "0.8811 shares"
            shares_match = re.match(r'^([0-9.]+)\s*shares', bl)
            if shares_match and shares is None:
                shares = float(shares_match.group(1))

            # Ounces (gold): "0.3508951974 ounces"
            oz_match = re.match(r'^([0-9.]+)\s*ounces', bl)
            if oz_match and shares is None and ticker == "GLD":
                oz = float(oz_match.group(1))
                shares = round(oz * 10, 4)

        if shares and shares > 0 and total_value and total_value > 0:
            if currency == "CAD":
                total_value *= 0.72
            entry_price = round(total_value / shares, 2)
            positions.append({
                "ticker": ticker,
                "shares": round(shares, 6),
                "entry_price": entry_price,
            })

        i = j if j > i + 1 else i + 1

    return positions


@app.post("/api/portfolio/import")
def import_portfolio(data: dict):
    """Parse Wealthsimple portfolio text and replace all positions."""
    import yaml
    import uuid
    from datetime import datetime

    text = data.get("text", "")
    if not text.strip():
        raise HTTPException(400, "text required")

    parsed = _parse_wealthsimple_text(text)
    if not parsed:
        raise HTTPException(400, "Could not parse any positions from text")

    # Build new portfolio
    today = datetime.now().strftime("%Y-%m-%d")
    from stockpulse.config.settings import load_portfolio
    port = load_portfolio()

    positions = []
    for p in parsed:
        positions.append({
            "ticker": p["ticker"],
            "shares": p["shares"],
            "entry_price": p["entry_price"],
            "entry_date": today,
            "lots": [{
                "lot_id": str(uuid.uuid4())[:8],
                "shares": p["shares"],
                "cost_basis": p["entry_price"],
                "acquired_at": today,
                "source": "import",
            }],
        })

    port["positions"] = positions
    port["cash"] = data.get("cash", 0)

    port_path = PROJECT_ROOT / "stockpulse" / "config" / "portfolio.yaml"
    with open(port_path, "w") as f:
        yaml.dump(port, f, default_flow_style=False, sort_keys=False)

    return {
        "status": "imported",
        "positions": len(positions),
        "tickers": [p["ticker"] for p in positions],
    }


@app.post("/api/portfolio/position")
def upsert_position(data: dict):
    """Add or update a single position."""
    import yaml
    import uuid
    from datetime import datetime

    ticker = data.get("ticker", "").upper()
    shares = data.get("shares")
    entry_price = data.get("entry_price")
    if not ticker or shares is None or entry_price is None:
        raise HTTPException(400, "ticker, shares, entry_price required")

    from stockpulse.config.settings import load_portfolio
    port = load_portfolio()
    positions = port.get("positions", [])
    today = data.get("entry_date", datetime.now().strftime("%Y-%m-%d"))

    # Find existing position
    existing = next((p for p in positions if p["ticker"] == ticker), None)
    if existing:
        existing["shares"] = float(shares)
        existing["entry_price"] = float(entry_price)
        existing["entry_date"] = today
        existing["lots"] = [{
            "lot_id": str(uuid.uuid4())[:8],
            "shares": float(shares),
            "cost_basis": float(entry_price),
            "acquired_at": today,
            "source": "manual",
        }]
    else:
        positions.append({
            "ticker": ticker,
            "shares": float(shares),
            "entry_price": float(entry_price),
            "entry_date": today,
            "lots": [{
                "lot_id": str(uuid.uuid4())[:8],
                "shares": float(shares),
                "cost_basis": float(entry_price),
                "acquired_at": today,
                "source": "manual",
            }],
        })

    port["positions"] = positions
    port_path = PROJECT_ROOT / "stockpulse" / "config" / "portfolio.yaml"
    with open(port_path, "w") as f:
        yaml.dump(port, f, default_flow_style=False, sort_keys=False)

    return {"status": "updated", "ticker": ticker}


@app.delete("/api/portfolio/position/{ticker}")
def delete_position(ticker: str):
    """Remove a position."""
    import yaml
    from stockpulse.config.settings import load_portfolio

    port = load_portfolio()
    positions = port.get("positions", [])
    t = ticker.upper()
    before = len(positions)
    port["positions"] = [p for p in positions if p["ticker"] != t]

    if len(port["positions"]) == before:
        raise HTTPException(404, f"Position {t} not found")

    port_path = PROJECT_ROOT / "stockpulse" / "config" / "portfolio.yaml"
    with open(port_path, "w") as f:
        yaml.dump(port, f, default_flow_style=False, sort_keys=False)

    return {"status": "deleted", "ticker": t}


# ═══════════════════════════════════════════════════
# Signals (on-demand analysis)
# ═══════════════════════════════════════════════════

@app.post("/api/analyze/{ticker}")
def analyze_ticker(ticker: str):
    from stockpulse.data.provider import get_price_history
    from stockpulse.research.recommendation import generate_recommendation
    t = ticker.upper()
    df = get_price_history(t, period="1y")
    if df.empty:
        raise HTTPException(404, f"No data for {ticker}")
    result = generate_recommendation(t, df)

    # Save result into latest scan JSON so watchlist shows it
    try:
        json_dir = PROJECT_ROOT / "outputs" / "json"
        if json_dir.exists():
            files = sorted(json_dir.glob("*.json"), reverse=True)
            for f in files:
                data = _read_json(f)
                if isinstance(data, dict) and "recommendations" in data:
                    # Remove old entry for this ticker if exists
                    recs = [r for r in data["recommendations"] if r.get("ticker") != t]
                    # Strip non-serializable fields
                    clean = {k: v for k, v in result.items() if k != "signals" or isinstance(v, dict)}
                    recs.append(clean)
                    data["recommendations"] = recs
                    with open(f, "w") as fh:
                        json.dump(data, fh, indent=2, default=str)
                    break
    except Exception:
        pass  # Don't fail the response if save fails

    return result


# ═══════════════════════════════════════════════════
# Validation
# ═══════════════════════════════════════════════════

@app.get("/api/validation")
def get_validation():
    return _read_json(PROJECT_ROOT / "outputs" / ".signal_tracker.json") or {"signals": [], "stats": {}, "validation": {}}


# ═══════════════════════════════════════════════════
# Reports
# ═══════════════════════════════════════════════════

@app.get("/api/reports")
def list_reports():
    reports_dir = PROJECT_ROOT / "outputs" / "reports"
    if not reports_dir.exists():
        return []
    result = []
    for f in sorted(reports_dir.glob("*.md"), reverse=True):
        name = f.stem
        parts = name.split("-")
        date_str = "-".join(parts[:3]) if len(parts) >= 3 else name
        # Detect report type from filename
        name_lower = name.lower()
        if "morning" in name_lower:
            rtype, title = "morning", "Morning Scan"
        elif "eod" in name_lower:
            rtype, title = "eod", "End of Day Recap"
        elif "intraday" in name_lower:
            # Extract time from "2026-04-14-1404-intraday"
            time_part = parts[3] if len(parts) > 4 else ""
            time_str = f"{time_part[:2]}:{time_part[2:]}" if len(time_part) == 4 else time_part
            rtype, title = "intraday", f"Intraday Update ({time_str})"
        elif "weekly" in name_lower:
            rtype, title = "weekly", "Weekly Digest"
        else:
            rtype, title = "other", name
        result.append({"filename": f.name, "date": date_str, "type": rtype, "title": title})
    return result


@app.get("/api/reports/{filename}")
def get_report(filename: str):
    path = PROJECT_ROOT / "outputs" / "reports" / filename
    if not path.exists() or ".." in filename:
        raise HTTPException(404, "Report not found")
    return {"filename": filename, "content": path.read_text()}


# ═══════════════════════════════════════════════════
# Alerts
# ═══════════════════════════════════════════════════

@app.get("/api/alerts/recent")
def get_recent_alerts():
    log_path = PROJECT_ROOT / "outputs" / "logs" / "alerts.log"
    if not log_path.exists():
        return []
    alerts = []
    for line in log_path.read_text().strip().split("\n")[-50:]:
        try:
            alerts.append(json.loads(line))
        except Exception:
            pass
    alerts.reverse()
    return alerts


# ═══════════════════════════════════════════════════
# Activity
# ═══════════════════════════════════════════════════

@app.get("/api/activity")
def get_activity():
    return _parse_activity_log()


# ═══════════════════════════════════════════════════
# Scan control
# ═══════════════════════════════════════════════════

@app.get("/api/scan/status")
def get_scan_status():
    return _get_scan_status()


@app.post("/api/scan")
def trigger_scan():
    def _run():
        import logging
        # Ensure scan logs go to the log file so status tracking works
        log_path = PROJECT_ROOT / "outputs" / "logs" / "stockpulse.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        root = logging.getLogger()
        fh = logging.FileHandler(log_path)
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                                           datefmt="%Y-%m-%d %H:%M:%S"))
        root.addHandler(fh)
        root.setLevel(logging.INFO)
        try:
            from stockpulse.scheduler.jobs import morning_scan_job
            morning_scan_job()
        finally:
            root.removeHandler(fh)
            fh.close()
    threading.Thread(target=_run, daemon=True).start()
    return {"status": "started"}


# ═══════════════════════════════════════════════════
# Backtesting
# ═══════════════════════════════════════════════════

_backtest_status = {"running": False, "progress": "", "result": None, "error": None}


@app.get("/api/backtest/status")
def get_backtest_status():
    return _backtest_status


@app.post("/api/backtest")
def trigger_backtest(data: dict = {}):
    if _backtest_status["running"]:
        return {"status": "already_running"}

    start_date = data.get("start_date", "2025-01-01")
    end_date = data.get("end_date", "2026-01-01")

    def _run():
        _backtest_status["running"] = True
        _backtest_status["progress"] = "Starting..."
        _backtest_status["error"] = None
        _backtest_status["result"] = None
        try:
            from stockpulse.backtests.runner import run_backtest
            _backtest_status["progress"] = f"Running {start_date} to {end_date}..."
            run_backtest(start_date=start_date, end_date=end_date)
            # Find the latest tearsheet
            logs_dir = PROJECT_ROOT / "logs"
            tearsheets = sorted(logs_dir.glob("*_tearsheet.html"), key=lambda f: f.stat().st_mtime, reverse=True) if logs_dir.exists() else []
            _backtest_status["result"] = {
                "tearsheet": str(tearsheets[0]) if tearsheets else None,
                "start_date": start_date,
                "end_date": end_date,
                "completed": True,
            }
            _backtest_status["progress"] = "Complete"
        except Exception as e:
            _backtest_status["error"] = str(e)
            _backtest_status["progress"] = "Failed"
        finally:
            _backtest_status["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return {"status": "started"}


@app.get("/api/backtest/tearsheet")
def get_tearsheet():
    """Serve the latest backtest tearsheet HTML."""
    logs_dir = PROJECT_ROOT / "logs"
    if not logs_dir.exists():
        raise HTTPException(404, "No backtest results")
    tearsheets = sorted(logs_dir.glob("*_tearsheet.html"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not tearsheets:
        raise HTTPException(404, "No tearsheet found")
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=tearsheets[0].read_text())


# ═══════════════════════════════════════════════════
# Market data
# ═══════════════════════════════════════════════════

@app.get("/api/quote/{ticker}")
def get_quote(ticker: str):
    from stockpulse.data.provider import get_current_quote
    return get_current_quote(ticker.upper())


@app.get("/api/history/{ticker}")
def get_history(ticker: str, period: str = "6mo"):
    from stockpulse.data.provider import get_price_history
    df = get_price_history(ticker.upper(), period=period)
    if df.empty:
        raise HTTPException(404, f"No data for {ticker}")
    return {
        "dates": [d.isoformat() for d in df.index],
        "close": [round(float(v), 2) for v in df["Close"]],
        "volume": [int(v) for v in df["Volume"]],
        "high": [round(float(v), 2) for v in df["High"]],
        "low": [round(float(v), 2) for v in df["Low"]],
        "open": [round(float(v), 2) for v in df["Open"]],
    }


# ═══════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════

@app.get("/api/config")
def get_config_endpoint():
    from stockpulse.config.settings import load_strategies, load_watchlists
    strat = load_strategies()
    wl = load_watchlists()
    # Flatten signal weights for the UI
    weights = {}
    for name, cfg in strat.get("signals", {}).items():
        w = cfg.get("weight", 0) if isinstance(cfg, dict) else 0
        if w > 0:
            weights[name] = w
    return {
        "watchlist": wl.get("user", []),
        "discovered": wl.get("discovered", []),
        "signals": strat.get("signals", {}),
        "weights": weights,
        "thresholds": strat.get("thresholds", {}),
        "confirmation": strat.get("confirmation", {}),
        "risk": strat.get("risk", {}),
        "scheduling": strat.get("scheduling", {}),
        "allocation": strat.get("allocation", {}),
        "filters": strat.get("filters", {}),
        "portfolio_advisor": strat.get("portfolio_advisor", {}),
    }


# ═══════════════════════════════════════════════════
# Portfolio Allocation Advisor
# ═══════════════════════════════════════════════════

@app.post("/api/allocate")
def suggest_allocation(data: dict):
    """Suggest portfolio allocation for a given investment amount."""
    amount = float(data.get("amount", 0))
    if amount <= 0:
        raise HTTPException(400, "Amount must be positive")

    selected_tickers = data.get("tickers", [])  # optional: user-selected tickers

    all_recs = _get_latest_scan()

    from stockpulse.portfolio.tracker import get_portfolio_status
    from stockpulse.portfolio.risk import check_concentration_limits
    from stockpulse.config.settings import load_portfolio, load_strategies

    portfolio = get_portfolio_status()
    positions = load_portfolio().get("positions", [])
    strat = load_strategies()
    risk_cfg = strat.get("risk", {})

    total_portfolio = portfolio["total_current"] + amount

    if selected_tickers:
        # User picked specific tickers — analyze them on demand
        from stockpulse.data.provider import get_price_history
        from stockpulse.research.recommendation import generate_recommendation
        candidates = []
        recs_map = {r["ticker"]: r for r in all_recs}
        for t in selected_tickers:
            t = t.upper()
            if t in recs_map:
                candidates.append(recs_map[t])
            else:
                try:
                    df = get_price_history(t, period="1y")
                    if not df.empty and len(df) >= 50:
                        candidates.append(generate_recommendation(t, df))
                except Exception:
                    pass
    else:
        # Auto-select from latest scan
        candidates = [r for r in all_recs if r.get("action") in ("BUY", "WATCHLIST")]
    candidates.sort(key=lambda r: r.get("composite_score", 0), reverse=True)

    alloc_cfg = strat.get("allocation", {})
    starter_enabled = alloc_cfg.get("watchlist_starter_enabled", True)
    starter_min_score = alloc_cfg.get("watchlist_starter_min_score", 30)
    starter_size_ratio = alloc_cfg.get("watchlist_starter_size", 0.33)
    max_wl_sleeve_pct = alloc_cfg.get("max_watchlist_sleeve", 0.25)
    max_wl_names = alloc_cfg.get("max_watchlist_names", 3)

    allocations = []
    remaining = amount
    held_tickers = {p["ticker"] for p in positions}
    max_positions = risk_cfg.get("max_positions", 8)
    max_pct = risk_cfg.get("max_position_pct", 8)
    current_count = len(positions)

    # Separate BUY and eligible WATCHLIST candidates
    buy_candidates = [r for r in candidates if r.get("action") == "BUY"]
    wl_candidates = [
        r for r in candidates
        if r.get("action") == "WATCHLIST" and r.get("composite_score", 0) >= starter_min_score
    ]

    # --- BUY candidates: full position sizing ---
    for rec in buy_candidates[:15]:
        if remaining <= 0 or current_count >= max_positions:
            break

        ticker = rec["ticker"]
        score = rec.get("composite_score", 0)

        risk_check = check_concentration_limits(ticker, positions, total_portfolio)
        if not risk_check["allowed"] and ticker not in held_tickers:
            continue

        score_factor = min(abs(score) / 55, 1.0)
        full_dollars = total_portfolio * (max_pct / 100) * score_factor * risk_check.get("size_multiplier", 1.0)
        suggested_dollars = round(min(full_dollars, remaining), 2)

        if suggested_dollars < 50:
            continue

        allocations.append({
            "ticker": ticker,
            "action": rec.get("action", "BUY"),
            "score": round(score, 1),
            "suggested_amount": suggested_dollars,
            "suggested_pct": round((suggested_dollars / amount) * 100, 1),
            "thesis": rec.get("thesis", ""),
            "sector": risk_check.get("sector", ""),
            "cluster": risk_check.get("cluster_tickers", []),
            "already_held": ticker in held_tickers,
            "risk_flags": risk_check.get("reasons", []),
            "position_type": "full",
            "size_reason": "BUY — full position",
        })

        remaining -= suggested_dollars
        if ticker not in held_tickers:
            current_count += 1

    # --- WATCHLIST starters: 33% size, strict qualifiers, capped sleeve ---
    max_wl_dollars = amount * max_wl_sleeve_pct
    wl_allocated = 0.0
    wl_count = 0
    wl_clusters_used: set = set()

    if starter_enabled:
        for rec in wl_candidates[:15]:
            if remaining <= 0 or wl_count >= max_wl_names or wl_allocated >= max_wl_dollars:
                break

            ticker = rec["ticker"]
            score = rec.get("composite_score", 0)

            # Requirement 1: trend bucket must confirm
            confirmation = rec.get("confirmation", {})
            trend_confirms = confirmation.get("buckets", {}).get("trend", {}).get("confirms", False)
            if not trend_confirms:
                continue

            # Requirement 2: relative strength score >= 60
            rs_score = rec.get("signals", {}).get("relative_strength", {}).get("score", 0)
            if rs_score < 60:
                continue

            # Requirement 3: no earnings blackout (earnings score != -30)
            earnings_score = rec.get("signals", {}).get("earnings", {}).get("score", 0)
            if earnings_score <= -30:
                continue

            # Requirement 4: concentration limits must pass
            risk_check = check_concentration_limits(ticker, positions, total_portfolio)
            if not risk_check["allowed"] and ticker not in held_tickers:
                continue

            # Requirement 5: max 1 per cluster
            cluster_tickers = risk_check.get("cluster_tickers", [])
            cluster_key = frozenset(cluster_tickers + [ticker])
            if any(c in wl_clusters_used for c in cluster_key):
                continue

            # Requirement 6: price above 20 EMA — check signals or thesis
            signals = rec.get("signals", {})
            ma_signals = signals.get("moving_averages", {})
            price_above_20ema = ma_signals.get("price_above_20ema", None)
            if price_above_20ema is None:
                # Fallback: check thesis text for explicit invalidation cue
                thesis_text = rec.get("thesis", "").lower()
                price_above_20ema = "below 20" not in thesis_text and "under 20 ema" not in thesis_text
            if not price_above_20ema:
                continue

            # Requirement 7: not invalidated
            if rec.get("invalidated", False):
                continue

            # Starter sizing: 33% of what a full BUY would get
            score_factor = min(abs(score) / 55, 1.0)
            full_dollars = total_portfolio * (max_pct / 100) * score_factor * risk_check.get("size_multiplier", 1.0)
            starter_dollars = round(
                min(full_dollars * starter_size_ratio, remaining, max_wl_dollars - wl_allocated), 2
            )

            if starter_dollars < 50:
                continue

            allocations.append({
                "ticker": ticker,
                "action": rec.get("action", "WATCHLIST"),
                "score": round(score, 1),
                "suggested_amount": starter_dollars,
                "suggested_pct": round((starter_dollars / amount) * 100, 1),
                "thesis": rec.get("thesis", ""),
                "sector": risk_check.get("sector", ""),
                "cluster": cluster_tickers,
                "already_held": ticker in held_tickers,
                "risk_flags": risk_check.get("reasons", []),
                "position_type": "starter",
                "size_reason": f"WATCHLIST starter (33% of full, score {score:.1f})",
            })

            remaining -= starter_dollars
            wl_allocated += starter_dollars
            wl_count += 1
            wl_clusters_used.update(cluster_key)
            if ticker not in held_tickers:
                current_count += 1

    cash_reserve = max(remaining, 0)

    current_analysis = []
    for pos in portfolio["positions"]:
        ticker = pos["ticker"]
        rec = next((r for r in all_recs if r.get("ticker") == ticker), None)
        signal = rec.get("action", "UNKNOWN") if rec else "UNKNOWN"
        current_analysis.append({
            "ticker": ticker,
            "current_value": pos["current_value"],
            "pnl_pct": pos["pnl_pct"],
            "signal": signal,
            "suggestion": "HOLD" if signal in ("BUY", "WATCHLIST", "HOLD") else "REVIEW" if signal == "CAUTION" else "CONSIDER TRIMMING" if signal == "SELL" else "MONITOR",
        })

    rationale = ""
    try:
        from stockpulse.llm.summarizer import _call_llm
        alloc_parts = []
        for a in allocations[:5]:
            alloc_parts.append(f"{a['ticker']} ${a['suggested_amount']:.0f} ({a['action']})")
        alloc_summary = ", ".join(alloc_parts)
        holdings_parts = []
        for p in current_analysis:
            holdings_parts.append(f"{p['ticker']} ({p['pnl_pct']:+.1f}%)")
        holdings_summary = ", ".join(holdings_parts)
        prompt = (
            f"You are a portfolio advisor. A user has ${amount:,.0f} to invest. "
            f"Based on signal analysis, the suggested allocation is: {alloc_summary}. "
            f"Cash reserve: ${cash_reserve:,.0f}. "
            f"Current holdings: {holdings_summary}. "
            f"Write a 3-4 sentence rationale explaining the allocation strategy. "
            f"Mention diversification, signal strength, and any risks. No disclaimers. No markdown formatting — write plain text only."
        )
        from stockpulse.config.settings import get_config as _gc
        rationale = _call_llm(prompt, max_tokens=200, model=_gc()["llm_model_premium"]) or ""
    except Exception:
        rationale = ""

    return {
        "amount": amount,
        "allocations": allocations,
        "cash_reserve": round(cash_reserve, 2),
        "cash_reserve_pct": round((cash_reserve / amount) * 100, 1) if amount > 0 else 0,
        "current_holdings": current_analysis,
        "total_portfolio_after": round(total_portfolio, 2),
        "rationale": rationale.strip() if rationale else "Allocation based on signal strength, risk limits, and sector diversification.",
    }


# ═══════════════════════════════════════════════════
# Watchlist management
# ═══════════════════════════════════════════════════

@app.post("/api/config/update")
def update_config(data: dict):
    """Update thresholds and risk params in strategies.yaml."""
    from stockpulse.config.settings import load_strategies
    import yaml
    strat = load_strategies()
    # Only allow updating thresholds and risk
    if "thresholds" in data:
        for key, val in data["thresholds"].items():
            if key in strat.get("thresholds", {}):
                strat["thresholds"][key] = val
    if "risk" in data:
        for key, val in data["risk"].items():
            if key in strat.get("risk", {}):
                strat["risk"][key] = val
    if "scheduling" in data:
        for key, val in data["scheduling"].items():
            if key in strat.get("scheduling", {}):
                strat["scheduling"][key] = val
    if "filters" in data:
        if "filters" not in strat:
            strat["filters"] = {}
        for key, val in data["filters"].items():
            if key in ("shariah_only",):
                strat["filters"][key] = val
    if "allocation" in data:
        # Only allow editing sizing/limits, not the requirement rules
        editable_alloc_keys = {
            "watchlist_starter_enabled", "watchlist_starter_min_score",
            "watchlist_starter_size", "watchlist_starter_risk",
            "max_watchlist_sleeve", "max_watchlist_names",
            "max_one_name_per_cluster", "add_to_full_only_on_buy_upgrade",
            "never_average_down_watchlist", "watchlist_exit_score", "watchlist_timeout_days",
        }
        for key, val in data["allocation"].items():
            if key in editable_alloc_keys and key in strat.get("allocation", {}):
                strat["allocation"][key] = val
    if "portfolio_advisor" in data:
        if "portfolio_advisor" not in strat:
            strat["portfolio_advisor"] = {}
        pa = strat["portfolio_advisor"]
        for key, val in data["portfolio_advisor"].items():
            # Handle nested dicts (suggest_trim_on_caution, suggest_swap_to_fund_buy, turnover)
            if isinstance(val, dict) and isinstance(pa.get(key), dict):
                for subkey, subval in val.items():
                    pa[key][subkey] = subval
            else:
                pa[key] = val
    # Write back
    strat_path = PROJECT_ROOT / "stockpulse" / "config" / "strategies.yaml"
    with open(strat_path, "w") as f:
        yaml.dump(strat, f, default_flow_style=False, sort_keys=False)
    return {"status": "updated"}


# ═══════════════════════════════════════════════════
# Portfolio Advisor
# ═══════════════════════════════════════════════════

@app.get("/api/advisor/suggestions")
def get_advisor_suggestions():
    from stockpulse.portfolio.advisor import get_latest_suggestions
    return get_latest_suggestions()

@app.post("/api/advisor/acknowledge")
def acknowledge_advisor(data: dict):
    suggestion_hash = data.get("hash", "")
    if not suggestion_hash:
        raise HTTPException(400, "hash required")
    from stockpulse.portfolio.advisor import acknowledge_suggestion
    success = acknowledge_suggestion(suggestion_hash)
    return {"status": "acknowledged" if success else "not_found"}

@app.post("/api/advisor/evaluate")
def trigger_advisor():
    import threading
    def _run():
        from stockpulse.portfolio.advisor import evaluate
        recs = _get_latest_scan()
        evaluate(recs, scan_trigger="manual")
    threading.Thread(target=_run, daemon=True).start()
    return {"status": "started"}

@app.get("/api/advisor/plan")
def get_advisor_plan():
    from stockpulse.portfolio.advisor import _load_state
    state = _load_state()
    return state.get("eod_plan", {"summary": "No EOD plan generated yet.", "sections": [], "total_suggestions": 0})

@app.get("/api/advisor/config")
def get_advisor_config():
    from stockpulse.config.settings import load_strategies
    return load_strategies().get("portfolio_advisor", {})


@app.post("/api/watchlist/add")
def add_to_watchlist(data: dict):
    from stockpulse.config.settings import load_watchlists, save_watchlists
    ticker = data.get("ticker", "").upper()
    if not ticker:
        raise HTTPException(400, "ticker required")
    wl = load_watchlists()
    if ticker not in wl.get("user", []):
        wl.setdefault("user", []).append(ticker)
        save_watchlists(wl)
    return {"status": "added", "ticker": ticker}


@app.post("/api/watchlist/remove")
def remove_from_watchlist(data: dict):
    from stockpulse.config.settings import load_watchlists, save_watchlists
    ticker = data.get("ticker", "").upper()
    wl = load_watchlists()
    if ticker in wl.get("user", []):
        wl["user"].remove(ticker)
    if ticker in wl.get("discovered", []):
        wl["discovered"].remove(ticker)
    wl["priority"] = [p for p in wl.get("priority", []) if p.get("ticker") != ticker]
    save_watchlists(wl)
    return {"status": "removed", "ticker": ticker}
