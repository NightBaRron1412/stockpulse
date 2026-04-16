"""APScheduler job definitions for StockPulse."""
import logging
from stockpulse.config.settings import load_watchlists
from stockpulse.scanners.market_scanner import run_full_scan, run_watchlist_scan
from stockpulse.reports.daily import generate_morning_report, generate_eod_report
from stockpulse.reports.intraday import detect_changes, generate_intraday_report
from stockpulse.alerts.dispatcher import dispatch_recommendations, dispatch_alert

logger = logging.getLogger(__name__)

def _is_day_trading_focus() -> bool:
    from stockpulse.config.settings import load_strategies
    return load_strategies().get("rebound_mode", {}).get("day_trading_focus", False)


def morning_scan_job():
    logger.info("=== MORNING SCAN START ===")
    if _is_day_trading_focus():
        logger.info("Day trading focus mode — skipping morning position scan, running rebound scan only")
        _run_rebound_check()
        return
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
        _run_advisor("morning_scan", recommendations)
    except Exception:
        logger.exception("Morning scan failed")

def intraday_check_job():
    logger.info("--- Intraday check ---")
    if _is_day_trading_focus():
        logger.info("Day trading focus — rebound scan only")
        _run_rebound_check()
        return
    try:
        wl = load_watchlists()
        user_tickers = set(wl.get("user", []))
        all_tickers = list(user_tickers | {
            item["ticker"] if isinstance(item, dict) else item
            for item in wl.get("priority", [])})
        if not all_tickers:
            return
        recommendations = run_watchlist_scan(all_tickers)
        changes = detect_changes(recommendations)
        if changes:
            # Separate tier changes from score movements
            tier_changes = [c for c in changes if c.get("type") == "action_change"]
            score_moves = [c for c in changes if c.get("type") == "score_movement"]
            approaching = [c for c in changes if c.get("type") == "approaching_threshold"]

            if tier_changes:
                generate_intraday_report(tier_changes)

            for change in changes:
                change_type = change.get("type", "action_change")
                if change_type == "action_change":
                    thesis = f"{change['ticker']}: {change.get('previous_action', '?')} → {change['new_action']}. {change.get('thesis', '')}"
                elif change_type == "score_movement":
                    thesis = change.get("thesis", "")
                elif change_type == "approaching_threshold":
                    thesis = change.get("thesis", "")
                else:
                    thesis = change.get("thesis", "")

                alert = {
                    "ticker": change["ticker"],
                    "action": change["new_action"],
                    "confidence": change.get("confidence", 50),
                    "thesis": thesis,
                    "type": change_type,
                    "technical_summary": "",
                    "catalyst_summary": "",
                    "invalidation": "",
                }
                # Only send Telegram for tier changes and approaching threshold
                if change_type in ("action_change", "approaching_threshold"):
                    dispatch_alert(alert)
                else:
                    # Score movements: log only, don't spam Telegram
                    from stockpulse.alerts.log_alert import send_log_alert
                    send_log_alert(alert)

            # Track BUY/WATCHLIST signals for performance validation
            for rec in recommendations:
                if rec.get("action") in ("BUY", "WATCHLIST"):
                    try:
                        from stockpulse.research.tracker import log_signal
                        log_signal(rec)
                    except Exception:
                        pass
            logger.info("Intraday: %d changes (%d tier, %d score, %d approaching)",
                        len(changes), len(tier_changes), len(score_moves), len(approaching))
        else:
            logger.info("Intraday: no changes detected")

        # Always generate a status report (even when no changes)
        _generate_intraday_status(recommendations, changes)

        _run_advisor("intraday", recommendations)
        _run_rebound_check()
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
        _run_eod_plan(recommendations)

        # Review past signal performance
        from stockpulse.research.tracker import review_signals
        perf = review_signals()
        if perf.get("total_signals", 0) > 0:
            logger.info("Signal performance: %s", perf)

        # Daily cache cleanup
        try:
            from stockpulse.data.cache import cleanup_expired_cache
            removed = cleanup_expired_cache()
            if removed > 0:
                logger.info("Cache cleanup: removed %d expired files", removed)
        except Exception:
            pass
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

def portfolio_check_job():
    """Check portfolio positions for P&L milestones and invalidation."""
    logger.info("--- Portfolio check ---")
    try:
        from stockpulse.portfolio.tracker import dispatch_portfolio_alerts
        dispatch_portfolio_alerts()
    except Exception:
        logger.exception("Portfolio check failed")


def signal_tracking_job():
    """Check outcomes for tracked signals and send validation milestones to Telegram."""
    logger.info("--- Signal tracking check ---")
    try:
        from stockpulse.research.tracker import check_signal_outcomes, _load_tracker
        results = check_signal_outcomes()
        total = sum(results.values())
        if total > 0:
            logger.info("Signal outcomes resolved: %s", results)

        # Send validation report at milestones: 30, 50, 75, 100, 150, 250 BUY signals
        tracker = _load_tracker()
        validation = tracker.get("validation", {})
        sample = validation.get("sample_size", {})
        n_buy = sample.get("buy_signals", 0)

        milestones = [30, 50, 75, 100, 150, 250]
        # Check if we just crossed a milestone
        prev_count = n_buy - total  # approximate previous count
        for m in milestones:
            if prev_count < m <= n_buy:
                _send_validation_report(n_buy, validation)
                break

    except Exception:
        logger.exception("Signal tracking check failed")


def _send_validation_report(n_buy: int, validation: dict):
    """Send a simple ping when validation milestones are reached."""
    status = validation.get("status", "collecting")
    phase = validation.get("sample_size", {}).get("phase", "collecting")

    if status == "working":
        msg = f"Validation ready: {n_buy} BUY signals analyzed. VERDICT: MODEL IS WORKING. Run 'python run.py scan' or check outputs/reports/ for full stats."
    elif status == "needs_calibration":
        msg = f"Validation ready: {n_buy} BUY signals analyzed. VERDICT: NEEDS CALIBRATION. Check outputs/reports/ for details."
    else:
        msg = f"Validation milestone: {n_buy} BUY signals tracked ({phase} phase). Full report in outputs/reports/."

    dispatch_alert({
        "ticker": "VALIDATION",
        "action": "INFO",
        "confidence": 100,
        "thesis": msg,
        "type": "validation_milestone",
        "technical_summary": "",
        "catalyst_summary": "",
        "invalidation": "",
    })


def _generate_intraday_status(recommendations: list[dict], changes: list[dict]) -> None:
    """Generate a brief intraday status report — always, even with no changes."""
    from datetime import datetime
    from pathlib import Path
    from stockpulse.config.settings import get_config

    try:
        cfg = get_config()
        reports_dir = Path(cfg["outputs_dir"]) / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M")
        report_path = reports_dir / f"{timestamp}-intraday.md"

        # Top movers by score
        sorted_recs = sorted(recommendations, key=lambda r: r.get("composite_score", 0), reverse=True)
        top = sorted_recs[:5]
        bottom = sorted(recommendations, key=lambda r: r.get("composite_score", 0))[:3]

        # Count by action
        counts = {}
        for r in recommendations:
            a = r.get("action", "HOLD")
            counts[a] = counts.get(a, 0) + 1

        lines = [
            f"# Intraday Status — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            f"**{len(recommendations)} tickers scanned** | "
            + " | ".join(f"{a}: {c}" for a, c in sorted(counts.items())),
            "",
        ]

        if changes:
            tier_changes = [c for c in changes if c.get("type") == "action_change"]
            score_moves = [c for c in changes if c.get("type") == "score_movement"]
            approaching = [c for c in changes if c.get("type") == "approaching_threshold"]
            lines.append(f"## Changes: {len(tier_changes)} tier, {len(score_moves)} score, {len(approaching)} approaching")
            lines.append("")
            for c in changes:
                ctype = c.get("type", "")
                if ctype == "action_change":
                    lines.append(f"- **{c['ticker']}**: {c.get('previous_action', '?')} → {c.get('new_action', '?')} ({c.get('score_delta', 0):+.1f} pts). {c.get('thesis', '')[:80]}")
                elif ctype == "score_movement":
                    lines.append(f"- **{c['ticker']}**: {c.get('thesis', '')[:100]}")
                elif ctype == "approaching_threshold":
                    lines.append(f"- **{c['ticker']}**: {c.get('thesis', '')[:100]}")
            lines.append("")
        else:
            lines.append("**No signal changes**")
            lines.append("")

        lines.append("## Top Movers")
        lines.append("")
        for r in top:
            lines.append(f"- **{r['ticker']}** {r['action']} ({r['composite_score']:+.1f})")
        lines.append("")

        if bottom and bottom[0].get("composite_score", 0) < 0:
            lines.append("## Weakest")
            lines.append("")
            for r in bottom:
                if r.get("composite_score", 0) < 0:
                    lines.append(f"- **{r['ticker']}** {r['action']} ({r['composite_score']:+.1f})")
            lines.append("")

        lines.append("---")
        report_path.write_text("\n".join(lines))
        logger.info("Intraday status report: %s", report_path)
    except Exception:
        logger.debug("Failed to generate intraday status report")


def _run_rebound_check():
    """Run rebound scan + check active trade exits. Sends Telegram alerts."""
    try:
        from stockpulse.config.settings import load_strategies
        config = load_strategies().get("rebound_mode", {})
        if not config.get("enabled", False):
            return

        # Check regime — disable in risk-off
        if config.get("guardrails", {}).get("disable_in_risk_off", True):
            try:
                from stockpulse.signals.market_regime import detect_regime
                regime = detect_regime()
                if regime.get("regime") in ("selling_off", "correcting"):
                    logger.info("Rebound: disabled in %s regime", regime["regime"])
                    return
            except Exception:
                pass

        # Check exit conditions on active trades
        from stockpulse.portfolio.rebound import check_active_exits
        exits = check_active_exits()
        for alert in exits:
            dispatch_alert({
                "ticker": alert["ticker"],
                "action": alert["action"],
                "confidence": 90,
                "thesis": alert["summary"],
                "type": "rebound_exit",
                "severity": alert.get("severity", "actionable"),
                "technical_summary": "",
                "catalyst_summary": "",
                "invalidation": "",
            })

        # Scan for new candidates
        from stockpulse.scanners.rebound_scanner import scan_rebound_candidates, get_eligible_tickers
        eligible = get_eligible_tickers()
        candidates = scan_rebound_candidates(eligible)

        if candidates:
            # Alert for top 1-2 candidates only
            for c in candidates[:2]:
                dispatch_alert({
                    "ticker": c["ticker"],
                    "action": "REBOUND",
                    "confidence": c["quality"],
                    "thesis": (
                        f"Rebound setup: {c['ticker']} dipped {c['dip_pct']:.1f}%, "
                        f"reclaimed VWAP ${c['vwap']:.2f}. "
                        f"Entry ~${c['current_price']:.2f}, Stop ${c['stop_price']:.2f}, "
                        f"Target ${c['target_price']:.2f}. "
                        f"Risk ${c['risk_dollars']:.0f} / Reward ${c['reward_dollars']:.0f}."
                    ),
                    "type": "rebound_candidate",
                    "severity": "actionable",
                    "technical_summary": c["setup"],
                    "catalyst_summary": "",
                    "invalidation": f"Stop: ${c['stop_price']:.2f}",
                })
            logger.info("Rebound: %d candidates found, %d exits flagged", len(candidates), len(exits))
        elif exits:
            logger.info("Rebound: no new candidates, %d exits flagged", len(exits))
        else:
            logger.info("Rebound: no setups, no exits")

    except Exception:
        logger.exception("Rebound check failed")


def _run_advisor(scan_trigger: str, recommendations: list[dict] | None = None):
    """Run advisor evaluation after a scan. Fail-safe — never breaks the scan pipeline."""
    try:
        from stockpulse.portfolio.advisor import evaluate
        from stockpulse.config.settings import load_strategies
        config = load_strategies().get("portfolio_advisor", {})
        if not config.get("evaluate_after_every_scan", True):
            return

        suggestions = evaluate(recommendations or [], scan_trigger=scan_trigger)
        if not suggestions:
            logger.info("Advisor: no suggestions")
            return

        # Dispatch new suggestions only
        push_new_only = config.get("push_only_on_state_change", True)
        for s in suggestions:
            if not push_new_only or s.is_new:
                alert = {
                    "ticker": s.ticker, "action": s.action,
                    "confidence": s.confidence,
                    "thesis": s.summary, "type": f"advisor_{s.suggestion_type.value}",
                    "technical_summary": s.details,
                    "catalyst_summary": "", "invalidation": "",
                    "severity": s.severity.value,
                }
                dispatch_alert(alert)

        urgent = sum(1 for s in suggestions if s.severity.value == "urgent")
        actionable = sum(1 for s in suggestions if s.severity.value == "actionable")
        info = sum(1 for s in suggestions if s.severity.value == "info")
        logger.info("Advisor (%s): %d suggestions (%d urgent, %d actionable, %d info)",
                     scan_trigger, len(suggestions), urgent, actionable, info)
    except Exception:
        logger.exception("Advisor evaluation failed")


def _run_eod_plan(recommendations: list[dict]):
    """Generate consolidated EOD portfolio plan and send summary to Telegram."""
    try:
        from stockpulse.portfolio.advisor import generate_eod_plan
        plan = generate_eod_plan(recommendations)

        if plan["total_suggestions"] == 0:
            logger.info("EOD plan: no changes recommended")
            return

        # Send consolidated summary as one Telegram message
        dispatch_alert({
            "ticker": "EOD PLAN",
            "action": "INFO",
            "confidence": 100,
            "thesis": plan["summary"],
            "type": "advisor_eod_plan",
            "technical_summary": (
                f"Urgent: {plan['urgent_count']} | "
                f"Actionable: {plan['actionable_count']} | "
                f"Info: {plan['info_count']} | "
                f"Net cash impact: ${plan['net_cash_impact']:+,.0f}"
            ),
            "catalyst_summary": "",
            "invalidation": "",
            "severity": "actionable" if plan["urgent_count"] > 0 or plan["actionable_count"] > 0 else "info",
        })

        logger.info("EOD plan: %s", plan["summary"])
    except Exception:
        logger.exception("EOD plan generation failed")


def weekly_digest_job():
    """Generate and send weekly digest every Sunday."""
    logger.info("=== WEEKLY DIGEST ===")
    try:
        from stockpulse.reports.weekly import generate_weekly_digest
        path = generate_weekly_digest()
        logger.info("Weekly digest complete: %s", path)
    except Exception:
        logger.exception("Weekly digest failed")
