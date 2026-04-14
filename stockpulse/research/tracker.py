"""Signal performance tracker with statistical validation .

Primary endpoint: BUY signals, 10-trading-day excess return vs SPY.
Secondary: 5d, 20d horizons. WATCHLIST tracked separately.

Statistical tests:
- Paired t-test on excess returns
- Wilcoxon signed-rank test
- Exact binomial on relative hit rate
- Bootstrap 95% CI
- BUY vs WATCHLIST separation
"""

import json
import logging
import math
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from scipy import stats as scipy_stats

from stockpulse.config.settings import get_config
from stockpulse.data.provider import get_current_quote, get_price_history

logger = logging.getLogger(__name__)

_TRACKER_FILE = Path(__file__).resolve().parent.parent.parent / "outputs" / ".signal_tracker.json"
_HORIZONS = {"5d": 7, "10d": 14, "20d": 28}  # calendar days approximation


def _load_tracker() -> dict:
    default = {"signals": [], "stats": {}, "validation": {}}
    if _TRACKER_FILE.exists():
        try:
            with open(_TRACKER_FILE) as f:
                data = json.load(f)
            # Ensure required keys exist (handles files reset by make clean)
            for key in default:
                if key not in data:
                    data[key] = default[key]
            return data
        except Exception:
            pass
    return default


def _save_tracker(data: dict) -> None:
    _TRACKER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_TRACKER_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


def log_signal(recommendation: dict) -> None:
    """Log a BUY or WATCHLIST signal for future performance tracking."""
    action = recommendation.get("action", "")
    if action not in ("BUY", "WATCHLIST"):
        return

    tracker = _load_tracker()
    ticker = recommendation["ticker"]
    today = datetime.now().strftime("%Y-%m-%d")

    # No duplicates on same day
    if any(s["ticker"] == ticker and s["signal_date"] == today for s in tracker["signals"]):
        return

    quote = get_current_quote(ticker)
    entry_price = quote.get("price", 0)
    if entry_price <= 0:
        return

    # Also record SPY price at signal time for paired comparison
    spy_quote = get_current_quote("SPY")
    spy_entry = spy_quote.get("price", 0)

    signal_record = {
        "ticker": ticker,
        "action": action,
        "signal_date": today,
        "entry_price": entry_price,
        "spy_entry_price": spy_entry,
        "composite_score": recommendation.get("composite_score", 0),
        "confidence": recommendation.get("confidence", 0),
        "thesis": recommendation.get("thesis", "")[:200],
        "checkpoints": {},
    }

    for horizon in _HORIZONS:
        signal_record["checkpoints"][horizon] = {
            "checked": False,
            "stock_price": None,
            "stock_return_pct": None,
            "spy_price": None,
            "spy_return_pct": None,
            "excess_vs_spy": None,
            "date": None,
        }

    tracker["signals"].append(signal_record)
    tracker["signals"] = tracker["signals"][-500:]
    _save_tracker(tracker)
    logger.info("Tracked signal: %s %s at $%.2f (SPY: $%.2f)", action, ticker, entry_price, spy_entry)


def check_signal_outcomes() -> dict:
    """Check prices for signals that have reached their checkpoint horizons."""
    tracker = _load_tracker()
    today = datetime.now()
    newly_resolved = {h: 0 for h in _HORIZONS}

    for signal in tracker["signals"]:
        signal_date = datetime.strptime(signal["signal_date"], "%Y-%m-%d")
        entry_price = signal["entry_price"]
        spy_entry = signal.get("spy_entry_price", 0)

        if entry_price <= 0:
            continue

        for horizon, cal_days in _HORIZONS.items():
            cp = signal["checkpoints"][horizon]
            if cp["checked"]:
                continue
            if (today - signal_date).days < cal_days:
                continue

            try:
                # Stock price
                stock_quote = get_current_quote(signal["ticker"])
                stock_price = stock_quote.get("price", 0)
                if stock_price <= 0:
                    continue

                stock_return = ((stock_price - entry_price) / entry_price) * 100

                # SPY price for paired benchmark
                spy_quote = get_current_quote("SPY")
                spy_price = spy_quote.get("price", 0)
                spy_return = ((spy_price - spy_entry) / spy_entry) * 100 if spy_entry > 0 else 0

                excess = stock_return - spy_return

                cp["checked"] = True
                cp["stock_price"] = round(stock_price, 2)
                cp["stock_return_pct"] = round(stock_return, 2)
                cp["spy_price"] = round(spy_price, 2)
                cp["spy_return_pct"] = round(spy_return, 2)
                cp["excess_vs_spy"] = round(excess, 2)
                cp["date"] = today.strftime("%Y-%m-%d")

                newly_resolved[horizon] += 1
            except Exception:
                continue

    # Recompute stats and validation
    tracker["stats"] = _compute_stats(tracker["signals"])
    tracker["validation"] = _run_validation_tests(tracker["signals"])
    _save_tracker(tracker)
    return newly_resolved


def _compute_stats(signals: list) -> dict:
    """Compute aggregate stats per horizon and action type."""
    stats = {}
    for horizon in _HORIZONS:
        resolved = [s for s in signals if s["checkpoints"][horizon]["checked"]]
        if not resolved:
            stats[horizon] = {"count": 0}
            continue

        returns = [s["checkpoints"][horizon]["stock_return_pct"] for s in resolved]
        excess = [s["checkpoints"][horizon]["excess_vs_spy"] for s in resolved
                  if s["checkpoints"][horizon]["excess_vs_spy"] is not None]

        winners = [r for r in returns if r > 0]
        excess_winners = [e for e in excess if e > 0]

        stats[horizon] = {
            "count": len(resolved),
            "avg_return": round(np.mean(returns), 2),
            "median_return": round(np.median(returns), 2),
            "hit_rate": round(len(winners) / len(resolved) * 100, 1),
            "avg_excess_vs_spy": round(np.mean(excess), 2) if excess else 0,
            "relative_hit_rate": round(len(excess_winners) / len(excess) * 100, 1) if excess else 0,
        }

        # By action type
        for action in ["BUY", "WATCHLIST"]:
            action_signals = [s for s in resolved if s["action"] == action]
            if action_signals:
                action_returns = [s["checkpoints"][horizon]["stock_return_pct"] for s in action_signals]
                action_excess = [s["checkpoints"][horizon]["excess_vs_spy"] for s in action_signals
                                 if s["checkpoints"][horizon]["excess_vs_spy"] is not None]
                action_winners = [r for r in action_returns if r > 0]

                stats[f"{horizon}_{action.lower()}"] = {
                    "count": len(action_signals),
                    "avg_return": round(np.mean(action_returns), 2),
                    "avg_excess": round(np.mean(action_excess), 2) if action_excess else 0,
                    "hit_rate": round(len(action_winners) / len(action_signals) * 100, 1),
                    "distinct_dates": len(set(s["signal_date"] for s in action_signals)),
                }

    return stats


def _run_validation_tests(signals: list) -> dict:
    """Run the the statistical test battery.

    Only runs when there are enough resolved signals.
    Primary: BUY, 10d, excess vs SPY.
    """
    validation = {"status": "collecting", "tests": {}}

    # Get BUY signals with resolved 10d checkpoints
    buy_10d = [s for s in signals
               if s["action"] == "BUY"
               and s["checkpoints"]["10d"]["checked"]
               and s["checkpoints"]["10d"]["excess_vs_spy"] is not None]

    watchlist_10d = [s for s in signals
                     if s["action"] == "WATCHLIST"
                     and s["checkpoints"]["10d"]["checked"]
                     and s["checkpoints"]["10d"]["excess_vs_spy"] is not None]

    n_buy = len(buy_10d)
    n_watchlist = len(watchlist_10d)
    distinct_dates = len(set(s["signal_date"] for s in buy_10d))

    validation["sample_size"] = {
        "buy_signals": n_buy,
        "watchlist_signals": n_watchlist,
        "distinct_buy_dates": distinct_dates,
        "phase": "pilot" if n_buy < 75 else ("meaningful" if n_buy < 150 else ("serious" if n_buy < 250 else "validated")),
    }

    if n_buy < 10:
        validation["status"] = "insufficient_data"
        return validation

    buy_excess = np.array([s["checkpoints"]["10d"]["excess_vs_spy"] for s in buy_10d])

    # A. Paired t-test: is mean excess return > 0?
    t_stat, t_pval = scipy_stats.ttest_1samp(buy_excess, 0)
    # One-sided: we want mean > 0
    t_pval_onesided = t_pval / 2 if t_stat > 0 else 1 - t_pval / 2
    validation["tests"]["paired_t"] = {
        "mean_excess": round(float(np.mean(buy_excess)), 3),
        "t_statistic": round(float(t_stat), 3),
        "p_value_one_sided": round(float(t_pval_onesided), 4),
        "significant_at_05": t_pval_onesided < 0.05,
    }

    # B. Wilcoxon signed-rank test
    try:
        # Remove zeros for Wilcoxon
        nonzero = buy_excess[buy_excess != 0]
        if len(nonzero) >= 10:
            w_stat, w_pval = scipy_stats.wilcoxon(nonzero, alternative="greater")
            validation["tests"]["wilcoxon"] = {
                "w_statistic": round(float(w_stat), 3),
                "p_value": round(float(w_pval), 4),
                "significant_at_05": w_pval < 0.05,
            }
    except Exception:
        pass

    # C. Exact binomial test on relative hit rate
    hits = int(np.sum(buy_excess > 0))
    binom_result = scipy_stats.binomtest(hits, n_buy, 0.5, alternative="greater")
    # Wilson confidence interval
    z = 1.96
    p_hat = hits / n_buy
    denom = 1 + z**2 / n_buy
    center = (p_hat + z**2 / (2 * n_buy)) / denom
    margin = z * math.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * n_buy)) / n_buy) / denom
    wilson_lower = max(0, center - margin)
    wilson_upper = min(1, center + margin)

    validation["tests"]["binomial_hit_rate"] = {
        "hits": hits,
        "total": n_buy,
        "hit_rate": round(hits / n_buy * 100, 1),
        "p_value": round(float(binom_result.pvalue), 4),
        "wilson_95_ci": [round(wilson_lower * 100, 1), round(wilson_upper * 100, 1)],
        "wilson_lower_above_50": wilson_lower > 0.50,
    }

    # D. Bootstrap 95% CI for mean excess return
    rng = np.random.default_rng(42)
    n_boot = 10000
    boot_means = np.array([
        np.mean(rng.choice(buy_excess, size=n_buy, replace=True))
        for _ in range(n_boot)
    ])
    ci_lower, ci_upper = np.percentile(boot_means, [2.5, 97.5])
    validation["tests"]["bootstrap"] = {
        "mean_excess": round(float(np.mean(buy_excess)), 3),
        "ci_95_lower": round(float(ci_lower), 3),
        "ci_95_upper": round(float(ci_upper), 3),
        "ci_above_zero": ci_lower > 0,
    }

    # F. BUY vs WATCHLIST separation (if enough WATCHLIST data)
    if n_watchlist >= 10:
        wl_excess = np.array([s["checkpoints"]["10d"]["excess_vs_spy"] for s in watchlist_10d])
        t2_stat, t2_pval = scipy_stats.ttest_ind(buy_excess, wl_excess, alternative="greater")

        validation["tests"]["buy_vs_watchlist"] = {
            "buy_mean": round(float(np.mean(buy_excess)), 3),
            "watchlist_mean": round(float(np.mean(wl_excess)), 3),
            "difference": round(float(np.mean(buy_excess) - np.mean(wl_excess)), 3),
            "t_statistic": round(float(t2_stat), 3),
            "p_value": round(float(t2_pval), 4),
            "monotonic": float(np.mean(buy_excess)) > float(np.mean(wl_excess)),
        }

    # Overall verdict
    mean_excess = float(np.mean(buy_excess))
    hit_rate = hits / n_buy

    if n_buy >= 100:
        passing = (
            mean_excess > 0.75
            and hit_rate >= 0.55
            and wilson_lower > 0.50
            and (ci_lower > 0 if n_buy >= 75 else True)
        )
        validation["status"] = "working" if passing else "needs_calibration"
        validation["verdict"] = {
            "mean_excess_above_075": mean_excess > 0.75,
            "hit_rate_above_55": hit_rate >= 0.55,
            "wilson_lower_above_50": wilson_lower > 0.50,
            "bootstrap_ci_above_0": ci_lower > 0,
        }
    else:
        validation["status"] = "collecting"

    return validation


def get_performance_report() -> str:
    """Generate markdown performance report with statistical tests."""
    tracker = _load_tracker()
    stats = tracker.get("stats", {})
    validation = tracker.get("validation", {})
    total_signals = len(tracker.get("signals", []))

    lines = [
        "## Signal Performance Tracker",
        "",
        f"**Total signals tracked:** {total_signals}",
    ]

    sample = validation.get("sample_size", {})
    if sample:
        lines.append(f"**Phase:** {sample.get('phase', 'collecting')} "
                     f"({sample.get('buy_signals', 0)} BUY, "
                     f"{sample.get('watchlist_signals', 0)} WATCHLIST, "
                     f"{sample.get('distinct_buy_dates', 0)} distinct dates)")
    lines.append("")

    # Stats table
    if stats:
        lines.append("| Period | Signals | Avg Return | Avg Excess vs SPY | Hit Rate | Rel Hit Rate |")
        lines.append("|--------|---------|-----------|-------------------|----------|-------------|")
        for horizon in ["5d", "10d", "20d"]:
            s = stats.get(horizon, {})
            if s.get("count", 0) > 0:
                lines.append(
                    f"| {horizon} | {s['count']} | {s['avg_return']:+.2f}% | "
                    f"{s.get('avg_excess_vs_spy', 0):+.2f}% | "
                    f"{s['hit_rate']:.0f}% | {s.get('relative_hit_rate', 0):.0f}% |"
                )
        lines.append("")

    # Validation tests
    tests = validation.get("tests", {})
    if tests:
        lines.append("### Statistical Validation (Primary: BUY 10d vs SPY)")
        lines.append("")

        t_test = tests.get("paired_t", {})
        if t_test:
            sig = "Yes" if t_test.get("significant_at_05") else "No"
            lines.append(f"- **Paired t-test:** mean excess = {t_test.get('mean_excess', 0):+.3f}%, "
                        f"t = {t_test.get('t_statistic', 0):.2f}, "
                        f"p = {t_test.get('p_value_one_sided', 1):.4f} (sig: {sig})")

        binom = tests.get("binomial_hit_rate", {})
        if binom:
            ci = binom.get("wilson_95_ci", [0, 0])
            lines.append(f"- **Hit rate:** {binom.get('hits', 0)}/{binom.get('total', 0)} = "
                        f"{binom.get('hit_rate', 0):.1f}%, "
                        f"Wilson 95% CI: [{ci[0]:.1f}%, {ci[1]:.1f}%]")

        boot = tests.get("bootstrap", {})
        if boot:
            above = "above" if boot.get("ci_above_zero") else "straddles"
            lines.append(f"- **Bootstrap 95% CI:** [{boot.get('ci_95_lower', 0):+.3f}%, "
                        f"{boot.get('ci_95_upper', 0):+.3f}%] ({above} zero)")

        bvw = tests.get("buy_vs_watchlist", {})
        if bvw:
            mono = "Yes (monotonic)" if bvw.get("monotonic") else "No"
            lines.append(f"- **BUY vs WATCHLIST:** BUY {bvw.get('buy_mean', 0):+.3f}% vs "
                        f"WL {bvw.get('watchlist_mean', 0):+.3f}% "
                        f"(diff: {bvw.get('difference', 0):+.3f}%, {mono})")
        lines.append("")

    # Verdict
    status = validation.get("status", "collecting")
    if status == "working":
        lines.append("**Verdict: MODEL IS WORKING**")
    elif status == "needs_calibration":
        lines.append("**Verdict: NEEDS CALIBRATION** -- not meeting target thresholds")
        verdict = validation.get("verdict", {})
        for k, v in verdict.items():
            lines.append(f"  - {k}: {'PASS' if v else 'FAIL'}")
    elif status == "insufficient_data":
        lines.append("*Insufficient data. Need 10+ resolved BUY signals to begin testing.*")
    else:
        lines.append("*Collecting data. Statistical tests run after 10+ BUY signals resolve.*")

    # Recent signals
    recent = tracker.get("signals", [])[-10:]
    if recent:
        lines.extend(["", "### Recent Signals", ""])
        lines.append("| Date | Ticker | Action | Entry | Score | 5d | 10d | 20d |")
        lines.append("|------|--------|--------|-------|-------|-----|------|------|")
        for s in reversed(recent):
            vals = []
            for h in ["5d", "10d", "20d"]:
                cp = s["checkpoints"].get(h, {})
                if cp.get("checked"):
                    excess = cp.get("excess_vs_spy")
                    if excess is not None:
                        vals.append(f"{excess:+.1f}%")
                    else:
                        vals.append(f"{cp.get('stock_return_pct', 0):+.1f}%")
                else:
                    vals.append("...")
            lines.append(
                f"| {s['signal_date']} | {s['ticker']} | {s['action']} | "
                f"${s['entry_price']:.2f} | {s['composite_score']:+.1f} | "
                f"{vals[0]} | {vals[1]} | {vals[2]} |"
            )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Backward-compatibility shims for callers using the old API
# (jobs.py eod_recap_job, run.py performance mode, daily.py reports)
# ---------------------------------------------------------------------------

def review_signals() -> dict:
    """Legacy wrapper: check outcomes and return summary in old format.

    Calls check_signal_outcomes() then maps stats into the period key format
    expected by existing callers (day_5, day_10, day_20).
    """
    check_signal_outcomes()
    tracker = _load_tracker()
    stats = tracker.get("stats", {})
    total = len(tracker.get("signals", []))

    periods: dict = {}
    key_map = {"5d": "day_5", "10d": "day_10", "20d": "day_20"}
    for new_key, old_key in key_map.items():
        s = stats.get(new_key, {})
        count = s.get("count", 0)
        if count == 0:
            periods[old_key] = {"reviewed": 0}
        else:
            avg_return = s.get("avg_return", 0)
            hit_rate = s.get("hit_rate", 0)
            periods[old_key] = {
                "reviewed": count,
                "hit_rate": hit_rate,
                "avg_return": avg_return,
                "avg_excess_vs_spy": s.get("avg_excess_vs_spy", 0),
                "relative_hit_rate": s.get("relative_hit_rate", 0),
            }

    return {"total_signals": total, "periods": periods}


def generate_performance_report() -> str:
    """Legacy wrapper: write a markdown performance report file and return its path."""
    report_dir = _TRACKER_FILE.parent / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{datetime.now().strftime('%Y-%m-%d')}-performance.md"
    path.write_text(get_performance_report())
    return str(path)
