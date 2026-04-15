"""Portfolio tracker — P&L calculation, invalidation monitoring, personalized alerts."""

import json
import logging
from datetime import datetime
from pathlib import Path

from stockpulse.config.settings import get_config, load_portfolio
from stockpulse.data.provider import get_current_quote, get_price_history
from stockpulse.research.recommendation import generate_recommendation
from stockpulse.alerts.dispatcher import dispatch_alert

logger = logging.getLogger(__name__)

_STATE_FILE = Path(__file__).resolve().parent.parent.parent / "outputs" / ".portfolio_state.json"


def _load_state() -> dict:
    """Load alerted milestones state to avoid re-alerting."""
    if _STATE_FILE.exists():
        try:
            with open(_STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"alerted_milestones": {}}


def _save_state(state: dict) -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_portfolio_status() -> dict:
    """Calculate real-time P&L for all positions.

    Returns:
        {
            "timestamp": str,
            "total_invested": float,
            "total_current": float,
            "total_pnl": float,
            "total_pnl_pct": float,
            "positions": [
                {
                    "ticker": str,
                    "shares": int/float,
                    "entry_price": float,
                    "entry_date": str,
                    "current_price": float,
                    "invested": float,
                    "current_value": float,
                    "pnl": float,
                    "pnl_pct": float,
                },
                ...
            ]
        }
    """
    portfolio = load_portfolio()
    positions = portfolio.get("positions", [])

    if not positions:
        return {
            "timestamp": datetime.now().isoformat(),
            "total_invested": 0, "total_current": 0,
            "total_pnl": 0, "total_pnl_pct": 0,
            "positions": [],
        }

    total_invested = 0.0
    total_current = 0.0
    pos_details = []

    for pos in positions:
        ticker = pos["ticker"]
        shares = pos["shares"]
        entry_price = pos["entry_price"]

        quote = get_current_quote(ticker)
        current_price = quote.get("price", 0.0)

        invested = shares * entry_price
        current_value = shares * current_price
        pnl = current_value - invested
        pnl_pct = (pnl / invested * 100) if invested > 0 else 0.0

        total_invested += invested
        total_current += current_value

        pos_details.append({
            "ticker": ticker,
            "shares": shares,
            "entry_price": entry_price,
            "entry_date": pos.get("entry_date", ""),
            "current_price": current_price,
            "invested": round(invested, 2),
            "current_value": round(current_value, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
        })

    total_pnl = total_current - total_invested
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0.0

    return {
        "timestamp": datetime.now().isoformat(),
        "total_invested": round(total_invested, 2),
        "total_current": round(total_current, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "positions": pos_details,
    }


def check_pnl_milestones() -> list[dict]:
    """Check if any positions have crossed P&L milestone thresholds.

    Only alerts once per milestone per position (tracked in state file).
    """
    portfolio = load_portfolio()
    milestones = portfolio.get("alerts", {}).get("pnl_milestones", [5, 10, 15, 25, 50])
    state = _load_state()
    alerted = state.get("alerted_milestones", {})

    status = get_portfolio_status()
    alerts = []

    for pos in status["positions"]:
        ticker = pos["ticker"]
        pnl_pct = pos["pnl_pct"]
        ticker_alerted = set(alerted.get(ticker, []))

        for milestone in milestones:
            # Check both positive and negative milestones
            for direction in [milestone, -milestone]:
                if direction > 0 and pnl_pct >= direction and direction not in ticker_alerted:
                    alerts.append({
                        "ticker": ticker,
                        "milestone": direction,
                        "pnl_pct": pnl_pct,
                        "current_price": pos["current_price"],
                        "entry_price": pos["entry_price"],
                        "shares": pos["shares"],
                        "pnl": pos["pnl"],
                    })
                    ticker_alerted.add(direction)
                elif direction < 0 and pnl_pct <= direction and direction not in ticker_alerted:
                    alerts.append({
                        "ticker": ticker,
                        "milestone": direction,
                        "pnl_pct": pnl_pct,
                        "current_price": pos["current_price"],
                        "entry_price": pos["entry_price"],
                        "shares": pos["shares"],
                        "pnl": pos["pnl"],
                    })
                    ticker_alerted.add(direction)

        alerted[ticker] = list(ticker_alerted)

    state["alerted_milestones"] = alerted
    _save_state(state)
    return alerts


def check_invalidation_levels() -> list[dict]:
    """Check if any held positions have hit their invalidation levels."""
    portfolio = load_portfolio()
    if not portfolio.get("alerts", {}).get("check_invalidation", True):
        return []

    positions = portfolio.get("positions", [])
    alerts = []

    for pos in positions:
        ticker = pos["ticker"]
        try:
            df = get_price_history(ticker, period="1y")
            if df.empty or len(df) < 50:
                continue

            rec = generate_recommendation(ticker, df)

            # If we hold the stock and the signal says SELL, that's an invalidation
            if rec["action"] == "SELL":
                alerts.append({
                    "ticker": ticker,
                    "action": "SELL",
                    "confidence": rec["confidence"],
                    "entry_price": pos["entry_price"],
                    "current_price": get_current_quote(ticker).get("price", 0),
                    "invalidation": rec["invalidation"],
                    "thesis": rec["thesis"],
                })
        except Exception:
            logger.debug("Invalidation check failed for %s", ticker)

    return alerts


def dispatch_portfolio_alerts() -> None:
    """Run all portfolio checks and dispatch alerts."""
    # P&L milestone alerts
    milestone_alerts = check_pnl_milestones()
    for alert in milestone_alerts:
        direction = "UP" if alert["pnl_pct"] > 0 else "DOWN"
        emoji = "📈" if direction == "UP" else "📉"
        dispatch_alert({
            "ticker": alert["ticker"],
            "action": direction,
            "confidence": min(int(abs(alert["pnl_pct"])), 100),
            "thesis": (
                f"{emoji} Your {alert['ticker']} is {direction} {abs(alert['pnl_pct']):.1f}% "
                f"(entry: ${alert['entry_price']:.2f} → current: ${alert['current_price']:.2f}, "
                f"P&L: ${alert['pnl']:+.2f})"
            ),
            "type": "portfolio",
            "technical_summary": f"Crossed {alert['milestone']:+d}% milestone",
            "catalyst_summary": "",
            "invalidation": "",
        })

    # Invalidation alerts
    inv_alerts = check_invalidation_levels()
    for alert in inv_alerts:
        dispatch_alert({
            "ticker": alert["ticker"],
            "action": "SELL",
            "confidence": alert["confidence"],
            "thesis": (
                f"⚠️ Your {alert['ticker']} position has a SELL signal! "
                f"Entry: ${alert['entry_price']:.2f}, Current: ${alert['current_price']:.2f}. "
                f"{alert['thesis']}"
            ),
            "type": "portfolio_invalidation",
            "technical_summary": alert["thesis"],
            "catalyst_summary": "",
            "invalidation": alert["invalidation"],
        })

    # Update peak equity for accurate drawdown tracking
    try:
        import yaml
        port = load_portfolio()
        status = get_portfolio_status()
        current_equity = status["total_current"] + port.get("cash", 0)
        peak = port.get("peak_equity", 0)
        if current_equity > peak:
            port["peak_equity"] = round(current_equity, 2)
            port_path = Path(__file__).resolve().parent.parent / "config" / "portfolio.yaml"
            with open(port_path, "w") as f:
                yaml.dump(port, f, default_flow_style=False, sort_keys=False)
            logger.info("Peak equity updated: $%.2f", current_equity)
    except Exception:
        logger.debug("Failed to update peak equity")

    logger.info(
        "Portfolio check: %d milestone alerts, %d invalidation alerts",
        len(milestone_alerts), len(inv_alerts),
    )
