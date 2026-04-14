"""Weekly digest report — summarizes the week's signals, moves, and setups."""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from stockpulse.config.settings import get_config, load_watchlists
from stockpulse.data.provider import get_price_history, get_current_quote
from stockpulse.llm.summarizer import _call_llm
from stockpulse.alerts.dispatcher import dispatch_alert

logger = logging.getLogger(__name__)


def generate_weekly_digest() -> str:
    """Generate and send weekly digest report.

    Covers: week's price moves, any signals triggered, portfolio P&L,
    what's setting up for next week.
    """
    cfg = get_config()
    reports_dir = Path(cfg["outputs_dir"]) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    report_path = reports_dir / f"{date_str}-weekly-digest.md"

    wl = load_watchlists()
    tickers = wl.get("user", []) + wl.get("discovered", [])
    tickers = list(set(tickers))

    # Collect weekly data
    weekly_data = []
    for ticker in tickers[:20]:  # cap at 20 to limit API calls
        try:
            df = get_price_history(ticker, period="1mo")
            if df.empty or len(df) < 5:
                continue

            # This week's performance (last 5 trading days)
            week_close = float(df["Close"].iloc[-1])
            week_open = float(df["Close"].iloc[-5]) if len(df) >= 5 else float(df["Close"].iloc[0])
            week_return = ((week_close - week_open) / week_open) * 100

            # Volume trend
            avg_vol = float(df["Volume"].iloc[-20:].mean()) if len(df) >= 20 else float(df["Volume"].mean())
            week_vol = float(df["Volume"].iloc[-5:].mean()) if len(df) >= 5 else avg_vol
            rvol = week_vol / avg_vol if avg_vol > 0 else 1.0

            weekly_data.append({
                "ticker": ticker,
                "week_return": round(week_return, 2),
                "close": round(week_close, 2),
                "rvol": round(rvol, 2),
            })
        except Exception:
            continue

    weekly_data.sort(key=lambda x: x["week_return"], reverse=True)

    # Portfolio P&L
    portfolio_section = ""
    try:
        from stockpulse.portfolio.tracker import get_portfolio_status
        status = get_portfolio_status()
        if status["positions"]:
            portfolio_section = f"\n**Portfolio: ${status['total_pnl']:+,.2f} ({status['total_pnl_pct']:+.1f}%)**\n"
            for p in status["positions"]:
                portfolio_section += f"- {p['ticker']}: ${p['current_price']:.2f} ({p['pnl_pct']:+.1f}%)\n"
    except Exception:
        pass

    # Signal tracker summary
    tracker_section = ""
    try:
        from stockpulse.research.tracker import get_performance_report
        tracker_section = get_performance_report()
    except Exception:
        pass

    # Tracked signals this week
    signals_section = ""
    try:
        tracker_file = Path(cfg["outputs_dir"]) / ".signal_tracker.json"
        if tracker_file.exists():
            with open(tracker_file) as f:
                td = json.load(f)
            this_week = [s for s in td.get("signals", [])
                        if s["signal_date"] >= (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")]
            if this_week:
                signals_section = f"\n**Signals this week: {len(this_week)}**\n"
                for s in this_week:
                    signals_section += f"- {s['action']} {s['ticker']} at ${s['entry_price']:.2f} (score: {s['composite_score']:+.1f})\n"
    except Exception:
        pass

    # Build report
    top_gainers = weekly_data[:5]
    top_losers = weekly_data[-5:] if len(weekly_data) > 5 else []

    lines = [
        f"# StockPulse Weekly Digest — {date_str}",
        "",
        portfolio_section,
        "## Week's Movers (Watchlist)",
        "",
        "| Ticker | Week Return | Close | RVOL |",
        "|--------|------------|-------|------|",
    ]

    for d in weekly_data:
        emoji = "📈" if d["week_return"] > 0 else "📉"
        lines.append(f"| {emoji} {d['ticker']} | {d['week_return']:+.2f}% | ${d['close']:.2f} | {d['rvol']:.1f}x |")

    if signals_section:
        lines.append("")
        lines.append(signals_section)

    if tracker_section:
        lines.append("")
        lines.append(tracker_section)

    # LLM summary for next week outlook
    llm_summary = ""
    try:
        gainers_str = ", ".join(f"{d['ticker']} {d['week_return']:+.1f}%" for d in top_gainers)
        losers_str = ", ".join(f"{d['ticker']} {d['week_return']:+.1f}%" for d in top_losers) if top_losers else "none"

        prompt = (
            f"You are a stock market analyst writing a brief weekly digest.\n\n"
            f"Top gainers this week: {gainers_str}\n"
            f"Top losers: {losers_str}\n"
            f"{'Signals triggered: ' + signals_section if signals_section else 'No new signals this week.'}\n\n"
            f"Write 3-4 sentences summarizing the week and what to watch for next week. "
            f"Be specific about tickers. No disclaimers."
        )
        llm_summary = _call_llm(prompt, max_tokens=200)
    except Exception:
        pass

    if llm_summary:
        lines.extend(["", "## Next Week Outlook", "", llm_summary])

    lines.extend(["", "---", "*Generated by StockPulse*"])

    report_content = "\n".join(lines)
    report_path.write_text(report_content)

    # Send digest to Telegram
    dispatch_alert({
        "ticker": "WEEKLY",
        "action": "INFO",
        "confidence": 100,
        "thesis": f"Weekly digest ready. Top mover: {top_gainers[0]['ticker']} {top_gainers[0]['week_return']:+.1f}%" if top_gainers else "Weekly digest ready.",
        "type": "weekly_digest",
        "technical_summary": llm_summary[:200] if llm_summary else "",
        "catalyst_summary": portfolio_section[:200] if portfolio_section else "",
        "invalidation": "",
    })

    logger.info("Weekly digest written to %s", report_path)
    return str(report_path)
