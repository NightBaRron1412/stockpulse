"""APScheduler job definitions for StockPulse."""
import logging
from stockpulse.config.settings import load_watchlists
from stockpulse.scanners.market_scanner import run_full_scan, run_watchlist_scan
from stockpulse.reports.daily import generate_morning_report, generate_eod_report
from stockpulse.reports.intraday import detect_changes, generate_intraday_report
from stockpulse.alerts.dispatcher import dispatch_recommendations, dispatch_alert

logger = logging.getLogger(__name__)

def morning_scan_job():
    logger.info("=== MORNING SCAN START ===")
    try:
        recommendations = run_full_scan()
        report_path = generate_morning_report(recommendations)
        dispatch_recommendations(recommendations)
        buys = sum(1 for r in recommendations if r["action"] == "BUY")
        sells = sum(1 for r in recommendations if r["action"] == "SELL")
        logger.info("Morning scan complete: %d tickers, %d BUY, %d SELL. Report: %s",
            len(recommendations), buys, sells, report_path)
        dispatch_alert({"ticker": "SUMMARY", "action": "INFO", "confidence": 100,
            "thesis": f"Morning scan complete: {buys} BUY, {sells} SELL signals from {len(recommendations)} tickers",
            "type": "summary", "technical_summary": f"Report at {report_path}",
            "catalyst_summary": "", "invalidation": ""})
    except Exception:
        logger.exception("Morning scan failed")

def intraday_check_job():
    logger.info("--- Intraday check ---")
    try:
        wl = load_watchlists()
        tickers = wl.get("user", []) + [
            item["ticker"] if isinstance(item, dict) else item
            for item in wl.get("priority", [])]
        tickers = list(set(tickers))
        if not tickers:
            return
        recommendations = run_watchlist_scan(tickers)
        changes = detect_changes(recommendations)
        if changes:
            generate_intraday_report(changes)
            for change in changes:
                dispatch_alert(change)
            logger.info("Intraday: %d changes detected", len(changes))
        else:
            logger.info("Intraday: no changes detected")
    except Exception:
        logger.exception("Intraday check failed")

def eod_recap_job():
    logger.info("=== EOD RECAP START ===")
    try:
        wl = load_watchlists()
        tickers = wl.get("user", [])
        recommendations = run_watchlist_scan(tickers) if tickers else run_full_scan()
        report_path = generate_eod_report(recommendations)
        logger.info("EOD recap complete. Report: %s", report_path)
    except Exception:
        logger.exception("EOD recap failed")

def sec_scan_job():
    logger.info("--- SEC filing scan ---")
    try:
        from stockpulse.scanners.catalyst_scanner import scan_catalysts
        wl = load_watchlists()
        tickers = wl.get("user", [])
        catalysts = scan_catalysts(tickers)
        for ticker, data in catalysts.items():
            if data.get("filings"):
                dispatch_alert({"ticker": ticker, "action": "INFO", "confidence": 50,
                    "thesis": f"New SEC filing(s) detected: {len(data['filings'])} recent filings",
                    "type": "sec_filing", "technical_summary": "",
                    "catalyst_summary": str(data["filings"][:3]), "invalidation": ""})
    except Exception:
        logger.exception("SEC scan failed")
