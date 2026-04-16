"""StockPulse main entrypoint -- starts the scheduler and runs scans."""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

def setup_logging(level: str = "INFO"):
    log_dir = Path(__file__).parent / "outputs" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=getattr(logging, level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(log_dir / "stockpulse.log")])

def run_once():
    from stockpulse.scanners.market_scanner import run_full_scan
    from stockpulse.reports.daily import generate_morning_report
    from stockpulse.alerts.dispatcher import dispatch_recommendations
    logging.info("Running one-shot full scan...")
    recommendations = run_full_scan()
    report_path = generate_morning_report(recommendations)
    dispatch_recommendations(recommendations)
    buys = [r for r in recommendations if r["action"] == "BUY"]
    sells = [r for r in recommendations if r["action"] == "SELL"]
    print(f"\nScan complete: {len(recommendations)} tickers")
    print(f"BUY signals: {len(buys)}")
    print(f"SELL signals: {len(sells)}")
    print(f"Report: {report_path}")
    if buys:
        print("\nTop BUY signals:")
        for r in sorted(buys, key=lambda x: x["confidence"], reverse=True)[:5]:
            print(f"  {r['ticker']:6s} confidence={r['confidence']}% score={r['composite_score']:.1f}")

def run_scheduler():
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger
    from stockpulse.config.settings import load_strategies
    from stockpulse.scheduler.jobs import morning_scan_job, intraday_check_job, eod_recap_job, sec_scan_job, portfolio_check_job
    strat = load_strategies()
    sched_cfg = strat.get("scheduling", {})
    tz = sched_cfg.get("timezone", "US/Eastern")
    scheduler = BlockingScheduler(timezone=tz)
    morning_time = sched_cfg.get("morning_scan", "09:35")
    h, m = morning_time.split(":")
    scheduler.add_job(morning_scan_job, CronTrigger(hour=int(h), minute=int(m), day_of_week="mon-fri", timezone=tz),
        id="morning_scan", name="Morning Full Scan")
    interval_min = sched_cfg.get("intraday_interval_minutes", 30)
    scheduler.add_job(intraday_check_job, CronTrigger(minute=f"*/{interval_min}", hour="9-16",
        day_of_week="mon-fri", timezone=tz), id="intraday_check", name="Intraday Check")
    # Fast rebound scan every 10 min (separate from intraday position check)
    from stockpulse.scheduler.jobs import rebound_scan_job
    rebound_interval = sched_cfg.get("rebound_scan_interval_minutes", 10)
    scheduler.add_job(rebound_scan_job, CronTrigger(minute=f"*/{rebound_interval}", hour="10-15",
        day_of_week="mon-fri", timezone=tz), id="rebound_scan", name="Rebound Dip Scan")

    eod_time = sched_cfg.get("eod_recap", "16:30")
    h, m = eod_time.split(":")
    scheduler.add_job(eod_recap_job, CronTrigger(hour=int(h), minute=int(m), day_of_week="mon-fri", timezone=tz),
        id="eod_recap", name="EOD Recap")
    sec_interval = sched_cfg.get("sec_scan_interval_hours", 2)
    scheduler.add_job(sec_scan_job, CronTrigger(hour=f"*/{sec_interval}", day_of_week="mon-fri", timezone=tz),
        id="sec_scan", name="SEC Filing Scan")
    from stockpulse.scheduler.jobs import portfolio_check_job
    scheduler.add_job(
        portfolio_check_job,
        CronTrigger(
            minute=f"*/{interval_min}",
            hour="9-16",
            day_of_week="mon-fri",
            timezone=tz,
        ),
        id="portfolio_check",
        name="Portfolio Check",
    )
    from stockpulse.scheduler.jobs import signal_tracking_job
    scheduler.add_job(
        signal_tracking_job,
        CronTrigger(hour="17", minute="0", day_of_week="mon-fri", timezone=tz),
        id="signal_tracking",
        name="Signal Performance Check",
    )
    from stockpulse.scheduler.jobs import weekly_digest_job
    scheduler.add_job(
        weekly_digest_job,
        CronTrigger(hour="18", minute="0", day_of_week="sun", timezone=tz),
        id="weekly_digest",
        name="Weekly Digest",
    )
    logging.info("StockPulse scheduler started with %d jobs:", len(scheduler.get_jobs()))
    for job in scheduler.get_jobs():
        logging.info("  - %s: %s", job.name, job.trigger)

    # Catch-up: if morning scan was missed today, run it now
    _catch_up_morning_scan(morning_time, tz)

    print("StockPulse scheduler is running. Press Ctrl+C to stop.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Scheduler stopped.")


def _catch_up_morning_scan(morning_time: str, tz: str):
    """If the morning scan was missed today (service started late), run it now."""
    import threading
    from datetime import datetime
    try:
        from pytz import timezone
        now = datetime.now(timezone(tz))
        h, m = map(int, morning_time.split(":"))

        # Only catch up on weekdays, after the scheduled time, before EOD
        if now.weekday() >= 5:  # Weekend
            return
        if now.hour < h or (now.hour == h and now.minute < m):
            return  # Before scheduled time
        if now.hour >= 16:
            return  # After market close

        # Check if a scan already ran today
        log_path = Path(__file__).parent / "outputs" / "logs" / "stockpulse.log"
        today_str = now.strftime("%Y-%m-%d")
        if log_path.exists():
            try:
                for line in log_path.read_text().split("\n")[-200:]:
                    if today_str in line and ("Morning scan complete" in line or "Scan complete" in line):
                        logging.info("Morning scan already ran today, skipping catch-up")
                        return
            except Exception:
                pass

        logging.info("Morning scan was missed today (service started at %s). Running catch-up scan...", now.strftime("%H:%M"))
        from stockpulse.scheduler.jobs import morning_scan_job
        threading.Thread(target=morning_scan_job, daemon=True).start()
    except Exception:
        logging.exception("Catch-up scan check failed")

def main():
    parser = argparse.ArgumentParser(description="StockPulse -- Stock Research & Alert System")
    parser.add_argument("mode", choices=["scan", "schedule", "backtest", "performance", "enter"],
        help="scan: one-shot scan | schedule: start scheduler | backtest: run backtest | performance: signal performance report | enter: enter a position")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    parser.add_argument("--start", help="Backtest start date (YYYY-MM-DD)")
    parser.add_argument("--end", help="Backtest end date (YYYY-MM-DD)")
    parser.add_argument("--ticker", help="Ticker for enter mode")
    parser.add_argument("--shares", type=int, help="Number of shares (auto-computed if omitted)")
    args = parser.parse_args()
    setup_logging(args.log_level)
    if args.mode == "scan":
        run_once()
    elif args.mode == "schedule":
        run_scheduler()
    elif args.mode == "backtest":
        from stockpulse.backtests.runner import run_backtest
        run_backtest(start_date=args.start, end_date=args.end)
    elif args.mode == "performance":
        from stockpulse.research.tracker import generate_performance_report, review_signals
        summary = review_signals()
        path = generate_performance_report()
        print(f"Signal performance report: {path}")
        print(f"Total signals tracked: {summary['total_signals']}")
        for period_key in ["day_5", "day_10", "day_20"]:
            p = summary["periods"].get(period_key, {})
            if p.get("reviewed", 0) > 0:
                print(f"  {period_key}: hit_rate={p['hit_rate']}% avg_return={p['avg_return']:+.2f}% profit_factor={p['profit_factor']:.2f}")
    elif args.mode == "enter":
        if not args.ticker:
            print("Error: --ticker required for enter mode")
            sys.exit(1)
        from stockpulse.portfolio.entry import enter_position
        result = enter_position(args.ticker, args.shares)
        if result["success"]:
            pos = result["position"]
            print(f"\nPosition entered:")
            print(f"  {pos['ticker']}: {pos['shares']} shares at ${pos['entry_price']:.2f}")
            print(f"  Total cost: ${result['total_cost']:,.2f}")
            print(f"  Stop loss: ${result['stop_price']:.2f}")
            rec = result.get("recommendation", {})
            print(f"  Signal: {rec.get('action', '?')} (score: {rec.get('score', 0):+.1f})")
            print(f"  Thesis: {rec.get('thesis', '')[:100]}")
        else:
            print(f"\nEntry failed: {result.get('error', 'unknown')}")
        if result.get("warnings"):
            print("\nWarnings:")
            for w in result["warnings"]:
                print(f"  - {w}")

if __name__ == "__main__":
    main()
