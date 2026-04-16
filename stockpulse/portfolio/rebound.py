"""Rebound-2D sleeve — separate P&L tracking for short-term dip trades.

Tracks active and closed rebound trades independently from the main portfolio.
"""
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_STATE_FILE = Path(__file__).resolve().parent.parent.parent / "outputs" / ".rebound_state.json"


def _load_state() -> dict:
    try:
        if _STATE_FILE.exists():
            return json.loads(_STATE_FILE.read_text())
    except Exception:
        pass
    return {
        "sleeve_size": 2000,
        "cash": 2000,
        "active_trades": [],
        "closed_trades": [],
        "stats": {"total_trades": 0, "wins": 0, "losses": 0, "total_pnl": 0},
        "guardrails": {"round_trips_today": 0, "round_trips_this_week": 0, "last_trade_date": ""},
    }


def _save_state(state: dict) -> None:
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps(state, indent=2, default=str))
    except Exception:
        logger.debug("Failed to save rebound state")


def get_sleeve_status() -> dict:
    """Get current rebound sleeve status."""
    state = _load_state()
    active = state.get("active_trades", [])
    stats = state.get("stats", {})
    win_rate = (stats["wins"] / stats["total_trades"] * 100) if stats.get("total_trades", 0) > 0 else 0

    return {
        "sleeve_size": state.get("sleeve_size", 2000),
        "cash": state.get("cash", 2000),
        "active_trades": active,
        "active_count": len(active),
        "total_trades": stats.get("total_trades", 0),
        "wins": stats.get("wins", 0),
        "losses": stats.get("losses", 0),
        "win_rate": round(win_rate, 1),
        "total_pnl": round(stats.get("total_pnl", 0), 2),
        "round_trips_today": state.get("guardrails", {}).get("round_trips_today", 0),
        "round_trips_this_week": state.get("guardrails", {}).get("round_trips_this_week", 0),
    }


def open_trade(ticker: str, shares: int, entry_price: float, stop_price: float,
               target_price: float, setup: str = "") -> dict:
    """Record a new rebound trade entry."""
    from stockpulse.config.settings import load_strategies
    config = load_strategies().get("rebound_mode", {})
    guardrails = config.get("guardrails", {})

    state = _load_state()
    today = datetime.now().strftime("%Y-%m-%d")

    # Reset daily/weekly counters
    gr = state.get("guardrails", {})
    if gr.get("last_trade_date", "") != today:
        gr["round_trips_today"] = 0
    # Simple weekly reset (Monday)
    if datetime.now().weekday() == 0 and gr.get("last_trade_date", "") != today:
        gr["round_trips_this_week"] = 0

    # Check guardrails
    max_daily = guardrails.get("max_round_trips_per_day", 1)
    max_weekly = guardrails.get("max_round_trips_per_week", 3)
    max_positions = config.get("sizing", {}).get("max_positions", 1)

    if gr.get("round_trips_today", 0) >= max_daily:
        return {"error": f"Max {max_daily} round-trip(s) per day reached"}
    if gr.get("round_trips_this_week", 0) >= max_weekly:
        return {"error": f"Max {max_weekly} round-trip(s) per week reached"}
    if len(state.get("active_trades", [])) >= max_positions:
        return {"error": f"Max {max_positions} active position(s)"}

    cost = round(shares * entry_price, 2)
    if cost > state.get("cash", 0):
        return {"error": f"Insufficient sleeve cash: ${state.get('cash', 0):.0f} < ${cost:.0f}"}

    trade = {
        "ticker": ticker,
        "shares": shares,
        "entry_price": round(entry_price, 2),
        "entry_time": datetime.now().isoformat(),
        "entry_date": today,
        "stop_price": round(stop_price, 2),
        "target_price": round(target_price, 2),
        "cost": cost,
        "setup": setup,
        "status": "active",
        "max_hold_date": None,  # Set based on exit rules
    }

    # Set max hold date
    max_hold = config.get("exit", {}).get("max_hold_days", 2)
    from datetime import timedelta
    hold_until = datetime.now() + timedelta(days=max_hold)
    trade["max_hold_date"] = hold_until.strftime("%Y-%m-%d")

    state.setdefault("active_trades", []).append(trade)
    state["cash"] = round(state.get("cash", 0) - cost, 2)
    _save_state(state)

    return {"status": "opened", "trade": trade}


def close_trade(ticker: str, exit_price: float, reason: str = "manual") -> dict:
    """Close a rebound trade and record P&L."""
    state = _load_state()
    active = state.get("active_trades", [])
    today = datetime.now().strftime("%Y-%m-%d")

    trade = next((t for t in active if t["ticker"] == ticker), None)
    if not trade:
        return {"error": f"No active trade for {ticker}"}

    proceeds = round(trade["shares"] * exit_price, 2)
    pnl = round(proceeds - trade["cost"], 2)
    pnl_pct = round((pnl / trade["cost"]) * 100, 2) if trade["cost"] > 0 else 0

    closed = {
        **trade,
        "exit_price": round(exit_price, 2),
        "exit_time": datetime.now().isoformat(),
        "exit_date": today,
        "exit_reason": reason,
        "proceeds": proceeds,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "status": "closed",
    }

    # Update state
    state["active_trades"] = [t for t in active if t["ticker"] != ticker]
    state.setdefault("closed_trades", []).append(closed)
    state["cash"] = round(state.get("cash", 0) + proceeds, 2)

    # Update stats
    stats = state.get("stats", {})
    stats["total_trades"] = stats.get("total_trades", 0) + 1
    if pnl > 0:
        stats["wins"] = stats.get("wins", 0) + 1
    else:
        stats["losses"] = stats.get("losses", 0) + 1
    stats["total_pnl"] = round(stats.get("total_pnl", 0) + pnl, 2)
    state["stats"] = stats

    # Update guardrails
    gr = state.get("guardrails", {})
    gr["round_trips_today"] = gr.get("round_trips_today", 0) + 1
    gr["round_trips_this_week"] = gr.get("round_trips_this_week", 0) + 1
    gr["last_trade_date"] = today
    state["guardrails"] = gr

    _save_state(state)

    return {"status": "closed", "trade": closed, "pnl": pnl, "pnl_pct": pnl_pct}


def check_active_exits() -> list[dict]:
    """Check active trades for exit conditions (stop, target, time)."""
    from stockpulse.data.provider import get_current_quote

    state = _load_state()
    alerts = []
    today = datetime.now().strftime("%Y-%m-%d")

    for trade in state.get("active_trades", []):
        ticker = trade["ticker"]
        try:
            quote = get_current_quote(ticker)
            price = quote.get("price", 0)
            if price <= 0:
                continue

            # Stop hit
            if price <= trade["stop_price"]:
                alerts.append({
                    "ticker": ticker, "action": "STOP_HIT", "severity": "urgent",
                    "price": price, "stop": trade["stop_price"],
                    "summary": f"STOP HIT {ticker}: ${price:.2f} <= stop ${trade['stop_price']:.2f}. Exit immediately.",
                })

            # Target hit
            elif price >= trade["target_price"]:
                alerts.append({
                    "ticker": ticker, "action": "TARGET_HIT", "severity": "actionable",
                    "price": price, "target": trade["target_price"],
                    "summary": f"TARGET HIT {ticker}: ${price:.2f} >= target ${trade['target_price']:.2f}. Take profit.",
                })

            # Max hold exceeded
            elif trade.get("max_hold_date") and today > trade["max_hold_date"]:
                alerts.append({
                    "ticker": ticker, "action": "TIME_EXIT", "severity": "actionable",
                    "price": price,
                    "summary": f"TIME EXIT {ticker}: Max hold exceeded ({trade['max_hold_date']}). Exit at ${price:.2f}.",
                })

        except Exception:
            pass

    return alerts
