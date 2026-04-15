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
    """Get recommendations from the most recent scan JSON file."""
    json_dir = PROJECT_ROOT / "outputs" / "json"
    if not json_dir.exists():
        return []
    files = sorted(json_dir.glob("*.json"), reverse=True)
    for f in files:
        try:
            data = _read_json(f)
            if isinstance(data, dict) and "recommendations" in data:
                return data.get("recommendations", [])
        except Exception:
            continue
    return []


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
            lines = log_path.read_text().strip().split("\n")
            for line in reversed(lines):
                if "Scan complete" in line and last_completed == "Never":
                    last_completed = line[:19]
                if "MORNING SCAN START" in line and last_completed == "Never":
                    running = True
                    current_job = "Morning Scan"
                if "Scanned " in line and "/" in line and running:
                    try:
                        progress = line.split("Scanned ")[1].split(" ")[0]
                    except Exception:
                        pass
                    break
            # Check if an intraday/portfolio/SEC job is actively running (started but not completed in last few lines)
            if not running:
                recent = lines[-5:] if len(lines) >= 5 else lines
                for line in reversed(recent):
                    if "--- Intraday check ---" in line:
                        current_job = "Intraday Check"
                        running = True
                        break
                    elif "--- Portfolio check ---" in line:
                        current_job = "Portfolio Check"
                        running = True
                        break
                    elif "--- SEC filing scan ---" in line:
                        current_job = "SEC Scan"
                        running = True
                        break
                    elif "executed successfully" in line or "no changes" in line or "complete" in line:
                        break  # last job finished, idle
        except Exception:
            pass
    return {
        "running": running,
        "progress": progress or current_job,
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
    status = get_portfolio_status()
    peak = max(status["total_current"], status["total_invested"]) if status["total_invested"] > 0 else 1
    dd = check_drawdown_status(status["total_current"], peak)
    return {**status, "drawdown": dd}


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
        from stockpulse.scheduler.jobs import morning_scan_job
        morning_scan_job()
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

    all_recs = _get_latest_scan()

    from stockpulse.portfolio.tracker import get_portfolio_status
    from stockpulse.portfolio.risk import check_concentration_limits
    from stockpulse.config.settings import load_portfolio, load_strategies

    portfolio = get_portfolio_status()
    positions = load_portfolio().get("positions", [])
    strat = load_strategies()
    risk_cfg = strat.get("risk", {})

    total_portfolio = portfolio["total_current"] + amount

    candidates = [r for r in all_recs if r.get("action") in ("BUY", "WATCHLIST")]
    candidates.sort(key=lambda r: r.get("composite_score", 0), reverse=True)

    allocations = []
    remaining = amount
    held_tickers = {p["ticker"] for p in positions}
    max_positions = risk_cfg.get("max_positions", 8)
    current_count = len(positions)

    for rec in candidates[:15]:
        if remaining <= 0 or current_count >= max_positions:
            break

        ticker = rec["ticker"]
        score = rec.get("composite_score", 0)
        action = rec.get("action", "HOLD")

        risk_check = check_concentration_limits(ticker, positions, total_portfolio)

        if not risk_check["allowed"] and ticker not in held_tickers:
            continue

        max_pct = risk_cfg.get("max_position_pct", 8)
        max_dollars = total_portfolio * (max_pct / 100)
        score_factor = min(abs(score) / 55, 1.0)
        suggested_dollars = min(max_dollars * score_factor * risk_check.get("size_multiplier", 1.0), remaining)
        suggested_dollars = round(suggested_dollars, 2)

        if suggested_dollars < 50:
            continue

        allocations.append({
            "ticker": ticker,
            "action": action,
            "score": round(score, 1),
            "suggested_amount": suggested_dollars,
            "suggested_pct": round((suggested_dollars / amount) * 100, 1),
            "thesis": rec.get("thesis", ""),
            "sector": risk_check.get("sector", ""),
            "cluster": risk_check.get("cluster_tickers", []),
            "already_held": ticker in held_tickers,
            "risk_flags": risk_check.get("reasons", []),
        })

        remaining -= suggested_dollars
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
        alloc_summary = ", ".join(f"{a['ticker']} ${a['suggested_amount']:.0f} ({a['action']})" for a in allocations[:5])
        prompt = (
            f"You are a portfolio advisor. A user has ${amount:,.0f} to invest. "
            f"Based on signal analysis, the suggested allocation is: {alloc_summary}. "
            f"Cash reserve: ${cash_reserve:,.0f}. "
            f"Current holdings: {', '.join(f'{p[\"ticker\"]} ({p[\"pnl_pct\"]:+.1f}%)' for p in current_analysis)}. "
            f"Write a 3-4 sentence rationale explaining the allocation strategy. "
            f"Mention diversification, signal strength, and any risks. No disclaimers."
        )
        rationale = _call_llm(prompt, max_tokens=200) or ""
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
    # Write back
    strat_path = PROJECT_ROOT / "stockpulse" / "config" / "strategies.yaml"
    with open(strat_path, "w") as f:
        yaml.dump(strat, f, default_flow_style=False, sort_keys=False)
    return {"status": "updated"}


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
