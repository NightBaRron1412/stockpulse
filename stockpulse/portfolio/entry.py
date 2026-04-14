"""Position entry helper — validates risk and adds position to portfolio."""

import logging
from datetime import datetime

import pandas_ta as ta

from stockpulse.config.settings import load_portfolio, save_portfolio, load_strategies
from stockpulse.data.provider import get_price_history, get_current_quote
from stockpulse.portfolio.risk import (
    check_concentration_limits,
    compute_position_size,
    check_drawdown_status,
)
from stockpulse.research.recommendation import generate_recommendation
from stockpulse.alerts.dispatcher import dispatch_alert

logger = logging.getLogger(__name__)


def enter_position(ticker: str, shares: int | None = None) -> dict:
    """Validate and enter a new position.

    Checks:
    1. Current recommendation (BUY/WATCHLIST/HOLD/SELL)
    2. Risk limits (sector cap, cluster, max positions, earnings blackout)
    3. Drawdown status
    4. Computes position size if shares not specified
    5. Adds to portfolio.yaml

    Args:
        ticker: Stock ticker to buy
        shares: Number of shares. If None, auto-computed from ATR and risk config.

    Returns:
        Dict with entry details and any warnings.
    """
    result = {"ticker": ticker, "success": False, "warnings": []}

    # Get current price
    quote = get_current_quote(ticker)
    current_price = quote.get("price", 0)
    if current_price <= 0:
        result["error"] = f"Could not get price for {ticker}"
        return result

    # Get recommendation
    df = get_price_history(ticker, period="1y")
    if df.empty or len(df) < 50:
        result["error"] = f"Insufficient price data for {ticker}"
        return result

    rec = generate_recommendation(ticker, df)
    result["recommendation"] = {
        "action": rec["action"],
        "score": rec["composite_score"],
        "confidence": rec["confidence"],
        "thesis": rec["thesis"],
        "invalidation": rec["invalidation"],
    }

    # Warn if not BUY or WATCHLIST
    if rec["action"] not in ("BUY", "WATCHLIST"):
        result["warnings"].append(
            f"Current signal is {rec['action']} (score: {rec['composite_score']:+.1f}). "
            f"Entering against the signal."
        )

    # Check risk limits
    portfolio = load_portfolio()
    positions = portfolio.get("positions", [])
    total_value = sum(p["shares"] * p.get("entry_price", 0) for p in positions)
    if total_value == 0:
        total_value = load_strategies().get("backtesting", {}).get("initial_cash", 100000)

    risk_check = check_concentration_limits(ticker, positions, total_value)
    if not risk_check["allowed"]:
        result["warnings"].extend(risk_check["reasons"])

    # Drawdown check
    current_equity = sum(
        p["shares"] * get_current_quote(p["ticker"]).get("price", p["entry_price"])
        for p in positions
    ) if positions else total_value
    peak_equity = max(current_equity, total_value)
    dd = check_drawdown_status(current_equity, peak_equity)
    if dd["new_buys_paused"]:
        result["error"] = f"New buys paused: drawdown at {dd['drawdown_pct']:.1f}%"
        return result

    # Compute position size if not specified
    atr = ta.atr(df["High"], df["Low"], df["Close"], length=14)
    atr_val = float(atr.iloc[-1]) if atr is not None and not atr.dropna().empty else current_price * 0.02

    if shares is None:
        sizing = compute_position_size(
            total_value, current_price, atr_val, rec["confidence"]
        )
        # Apply cluster penalty
        if risk_check.get("size_multiplier", 1.0) < 1.0:
            sizing["shares"] = int(sizing["shares"] * risk_check["size_multiplier"])
            result["warnings"].append(
                f"Position reduced to {risk_check['size_multiplier']:.0%} "
                f"(cluster: {risk_check['cluster_tickers']})"
            )
        # Apply drawdown multiplier
        if dd["size_multiplier"] < 1.0:
            sizing["shares"] = int(sizing["shares"] * dd["size_multiplier"])
            result["warnings"].append(f"Position halved: drawdown at {dd['drawdown_pct']:.1f}%")

        shares = sizing["shares"]
        result["computed_sizing"] = sizing

    if shares <= 0:
        result["error"] = "Position size computed to 0 shares"
        return result

    # Add to portfolio
    stop_price = round(current_price - 1.5 * atr_val, 2)
    new_position = {
        "ticker": ticker,
        "shares": shares,
        "entry_price": round(current_price, 2),
        "entry_date": datetime.now().strftime("%Y-%m-%d"),
    }

    positions.append(new_position)
    portfolio["positions"] = positions
    save_portfolio(portfolio)

    result["success"] = True
    result["position"] = new_position
    result["stop_price"] = stop_price
    result["total_cost"] = round(shares * current_price, 2)

    # Alert
    dispatch_alert({
        "ticker": ticker,
        "action": "ENTRY",
        "confidence": rec["confidence"],
        "thesis": f"Entered {shares} shares at ${current_price:.2f}. Stop: ${stop_price:.2f}. {rec['thesis'][:100]}",
        "type": "portfolio_entry",
        "technical_summary": rec.get("technical_summary", ""),
        "catalyst_summary": rec.get("catalyst_summary", ""),
        "invalidation": rec.get("invalidation", ""),
    })

    logger.info(
        "Position entered: %s %d shares at $%.2f (stop $%.2f)",
        ticker, shares, current_price, stop_price,
    )
    return result
