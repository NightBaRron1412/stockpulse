"""Tax lot tracking for portfolio positions.

Each position can have multiple lots with different cost bases and dates.
Supports FIFO sell selection, short/long-term classification, and wash sale detection.
"""
import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_PORTFOLIO_PATH = Path(__file__).resolve().parent.parent / "config" / "portfolio.yaml"

# Sold lots history for wash sale detection
_SOLD_LOTS_PATH = Path(__file__).resolve().parent.parent.parent / "outputs" / ".sold_lots.json"


def _load_portfolio() -> dict:
    try:
        with open(_PORTFOLIO_PATH) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _save_portfolio(data: dict) -> None:
    with open(_PORTFOLIO_PATH, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def ensure_lots(portfolio: dict | None = None) -> dict:
    """Ensure all positions have a lots array. Migrates single-entry positions.

    Backward compatible: if a position has no 'lots' key, creates one lot
    from the existing entry_price/entry_date/shares.
    """
    if portfolio is None:
        portfolio = _load_portfolio()

    modified = False
    for pos in portfolio.get("positions", []):
        if "lots" not in pos:
            pos["lots"] = [{
                "lot_id": str(uuid.uuid4())[:8],
                "shares": pos["shares"],
                "cost_basis": pos["entry_price"],
                "acquired_at": pos["entry_date"],
                "source": "migration",
            }]
            modified = True

    if modified:
        _save_portfolio(portfolio)

    return portfolio


def get_lots(ticker: str, portfolio: dict | None = None) -> list[dict]:
    """Get all open lots for a ticker, sorted by date (FIFO order)."""
    if portfolio is None:
        portfolio = _load_portfolio()

    for pos in portfolio.get("positions", []):
        if pos["ticker"] == ticker:
            lots = pos.get("lots", [])
            # Sort by acquisition date (FIFO)
            lots.sort(key=lambda l: l.get("acquired_at", ""))
            return lots

    return []


def add_lot(ticker: str, shares: float, cost_basis: float,
            acquired_at: str | None = None) -> dict:
    """Add a new lot to an existing position."""
    portfolio = _load_portfolio()
    acquired_at = acquired_at or datetime.now().strftime("%Y-%m-%d")

    lot = {
        "lot_id": str(uuid.uuid4())[:8],
        "shares": shares,
        "cost_basis": cost_basis,
        "acquired_at": acquired_at,
        "source": "manual",
    }

    for pos in portfolio.get("positions", []):
        if pos["ticker"] == ticker:
            pos.setdefault("lots", []).append(lot)
            # Update aggregate shares
            pos["shares"] = sum(l["shares"] for l in pos["lots"])
            _save_portfolio(portfolio)
            return lot

    # Position doesn't exist — create it
    portfolio.setdefault("positions", []).append({
        "ticker": ticker,
        "shares": shares,
        "entry_price": cost_basis,
        "entry_date": acquired_at,
        "lots": [lot],
    })
    _save_portfolio(portfolio)
    return lot


def compute_lot_tax_info(lot: dict, current_price: float) -> dict:
    """Compute tax classification for a single lot."""
    acquired = lot.get("acquired_at", "")
    cost = lot.get("cost_basis", 0)
    shares = lot.get("shares", 0)

    try:
        acq_date = datetime.strptime(acquired, "%Y-%m-%d")
        holding_days = (datetime.now() - acq_date).days
    except Exception:
        holding_days = 0

    is_long_term = holding_days >= 365
    gain_per_share = current_price - cost
    total_gain = gain_per_share * shares
    gain_pct = (gain_per_share / cost * 100) if cost > 0 else 0

    return {
        "lot_id": lot.get("lot_id", ""),
        "shares": shares,
        "cost_basis": cost,
        "acquired_at": acquired,
        "holding_days": holding_days,
        "is_long_term": is_long_term,
        "term": "long-term" if is_long_term else "short-term",
        "gain_per_share": round(gain_per_share, 2),
        "total_gain": round(total_gain, 2),
        "gain_pct": round(gain_pct, 2),
    }


def select_lots_fifo(ticker: str, shares_to_sell: float,
                     portfolio: dict | None = None) -> list[dict]:
    """Select lots to sell using FIFO (first in, first out).

    Returns list of {lot_id, shares_to_sell, cost_basis, acquired_at, ...}
    """
    lots = get_lots(ticker, portfolio)
    selected = []
    remaining = shares_to_sell

    for lot in lots:
        if remaining <= 0:
            break
        sell_shares = min(lot["shares"], remaining)
        selected.append({
            "lot_id": lot["lot_id"],
            "shares_to_sell": sell_shares,
            "cost_basis": lot["cost_basis"],
            "acquired_at": lot.get("acquired_at", ""),
        })
        remaining -= sell_shares

    return selected


def compute_tax_impact(ticker: str, shares_to_sell: float, current_price: float,
                       portfolio: dict | None = None) -> dict:
    """Compute total tax impact of selling shares using FIFO.

    Returns {
        total_gain, short_term_gain, long_term_gain,
        lots_detail: [{lot_id, shares, cost_basis, gain, term}]
    }
    """
    selected = select_lots_fifo(ticker, shares_to_sell, portfolio)
    short_term = 0.0
    long_term = 0.0
    details = []

    for sel in selected:
        gain = (current_price - sel["cost_basis"]) * sel["shares_to_sell"]
        try:
            acq = datetime.strptime(sel["acquired_at"], "%Y-%m-%d")
            is_lt = (datetime.now() - acq).days >= 365
        except Exception:
            is_lt = False

        if is_lt:
            long_term += gain
        else:
            short_term += gain

        details.append({
            "lot_id": sel["lot_id"],
            "shares": sel["shares_to_sell"],
            "cost_basis": sel["cost_basis"],
            "gain": round(gain, 2),
            "term": "long-term" if is_lt else "short-term",
        })

    return {
        "total_gain": round(short_term + long_term, 2),
        "short_term_gain": round(short_term, 2),
        "long_term_gain": round(long_term, 2),
        "lots_detail": details,
    }


def check_wash_sale(ticker: str, sold_lots_history: list[dict] | None = None) -> dict:
    """Check if buying this ticker would trigger a wash sale.

    A wash sale occurs if the same ticker was sold at a loss within
    30 days before or after the purchase.
    """
    import json

    if sold_lots_history is None:
        try:
            if _SOLD_LOTS_PATH.exists():
                sold_lots_history = json.loads(_SOLD_LOTS_PATH.read_text())
            else:
                sold_lots_history = []
        except Exception:
            sold_lots_history = []

    now = datetime.now()
    window = timedelta(days=30)

    for sale in sold_lots_history:
        if sale.get("ticker") != ticker:
            continue
        if sale.get("gain", 0) >= 0:
            continue  # Only losses trigger wash sales

        try:
            sold_date = datetime.strptime(sale["sold_at"], "%Y-%m-%d")
        except Exception:
            continue

        if abs((now - sold_date).days) <= 30:
            return {
                "wash_sale": True,
                "sold_at": sale["sold_at"],
                "loss": sale["gain"],
                "lot_id": sale.get("lot_id", ""),
            }

    return {"wash_sale": False}
