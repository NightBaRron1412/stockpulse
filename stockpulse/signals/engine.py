"""Signal aggregator -- computes all signals for a ticker."""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from stockpulse.config.settings import load_strategies
from stockpulse.signals.technical import (
    calc_rsi_signal, calc_macd_signal, calc_ma_signal,
    calc_volume_signal, calc_breakout_signal, calc_gap_signal, calc_adx_signal,
)
from stockpulse.signals.fundamental import (
    calc_earnings_signal, calc_sec_filing_signal, calc_news_sentiment_signal,
)
from stockpulse.signals.relative_strength import calc_relative_strength

logger = logging.getLogger(__name__)


def check_confirmation_buckets(signals: dict) -> dict:
    """Check how many signal buckets confirm the direction.
    Returns {confirming_count, buckets_detail, passes_threshold}."""
    strat = load_strategies()
    conf = strat.get("confirmation", {})
    required = conf.get("require_buckets", 2)
    bucket_defs = conf.get("buckets", {
        "trend": ["moving_averages", "macd", "adx"],
        "participation": ["volume", "breakout"],
        "catalyst": ["sec_filing"],
    })

    confirming = 0
    detail = {}

    for bucket_name, signal_names in bucket_defs.items():
        bucket_scores = []
        for name in signal_names:
            sig = signals.get(name, {})
            bucket_scores.append(sig.get("score", 0))

        # Bucket confirms if average score > 15
        avg = sum(bucket_scores) / len(bucket_scores) if bucket_scores else 0
        confirms = avg > 15
        detail[bucket_name] = {"avg_score": avg, "confirms": confirms}
        if confirms:
            confirming += 1

    return {
        "confirming_count": confirming,
        "required": required,
        "total_buckets": len(bucket_defs),
        "passes": confirming >= required,
        "buckets": detail,
    }


def compute_all_signals(ticker: str, df: pd.DataFrame, use_llm: bool = True) -> dict:
    strat = load_strategies()
    signal_cfg = strat.get("signals", {})
    signals = {}
    technical_calculators = {
        "rsi": calc_rsi_signal, "macd": calc_macd_signal,
        "moving_averages": calc_ma_signal, "volume": calc_volume_signal,
        "breakout": calc_breakout_signal, "gap": calc_gap_signal, "adx": calc_adx_signal,
    }
    for name, calc_fn in technical_calculators.items():
        try:
            score = calc_fn(df)
            weight = signal_cfg.get(name, {}).get("weight", 0.0)
            signals[name] = {"score": score, "weight": weight, "value": score}
        except Exception:
            logger.debug("Signal %s failed for %s", name, ticker)
            signals[name] = {"score": 0.0, "weight": 0.0, "value": None}
    fundamental_calculators = {
        "earnings": calc_earnings_signal, "sec_filing": calc_sec_filing_signal,
    }
    for name, calc_fn in fundamental_calculators.items():
        try:
            score = calc_fn(ticker)
            weight = signal_cfg.get(name, {}).get("weight", 0.0)
            signals[name] = {"score": score, "weight": weight, "value": score}
        except Exception:
            logger.debug("Signal %s failed for %s", name, ticker)
            signals[name] = {"score": 0.0, "weight": 0.0, "value": None}

    # News sentiment (LLM or keyword fallback)
    try:
        score = calc_news_sentiment_signal(ticker, use_llm=use_llm)
        weight = signal_cfg.get("news_sentiment", {}).get("weight", 0.0)
        signals["news_sentiment"] = {"score": score, "weight": weight, "value": score}
    except Exception:
        logger.debug("Signal news_sentiment failed for %s", ticker)
        signals["news_sentiment"] = {"score": 0.0, "weight": 0.0, "value": None}

    # Relative strength vs SPY + sector (needs ticker name and DataFrame)
    try:
        rs_score = calc_relative_strength(ticker, df)
        rs_weight = signal_cfg.get("relative_strength", {}).get("weight", 0.12)
        signals["relative_strength"] = {"score": rs_score, "weight": rs_weight, "value": rs_score}
    except Exception:
        logger.debug("Relative strength failed for %s", ticker)
        signals["relative_strength"] = {"score": 0.0, "weight": 0.0, "value": None}

    return signals


# ---------------------------------------------------------------------------
# Score history tracking (persisted in outputs/.score_history.json)
# ---------------------------------------------------------------------------

_SCORE_HISTORY_FILE = (
    Path(__file__).resolve().parent.parent.parent / "outputs" / ".score_history.json"
)


def _load_score_history() -> dict:
    if _SCORE_HISTORY_FILE.exists():
        try:
            with open(_SCORE_HISTORY_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_score_history(history: dict) -> None:
    _SCORE_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_SCORE_HISTORY_FILE, "w") as f:
        json.dump(history, f)


def compute_score_acceleration(
    ticker: str, current_score: float, confirmation: dict
) -> float:
    """Compute score acceleration bonus .

    : use as modifier (max +8 points), not core signal.
    Requires score >= 35 AND breadth >= 2 AND persist >= 2.
    """
    history = _load_score_history()
    ticker_hist = history.get(ticker, [])

    # Record current score
    ticker_hist.append(
        {"date": datetime.now().isoformat()[:10], "score": current_score}
    )
    # Keep last 10 scans
    ticker_hist = ticker_hist[-10:]
    history[ticker] = ticker_hist

    # Prune stale tickers (not updated in 30+ days)
    cutoff = (datetime.now() - timedelta(days=30)).isoformat()[:10]
    stale = [t for t, hist in history.items()
             if hist and hist[-1].get("date", "") < cutoff]
    for t in stale:
        del history[t]

    _save_score_history(history)

    if len(ticker_hist) < 3:
        return 0.0

    score_t = current_score
    score_t1 = ticker_hist[-2]["score"]
    score_t3 = (
        ticker_hist[-4]["score"]
        if len(ticker_hist) >= 4
        else ticker_hist[-3]["score"]
    )

    vel1 = score_t - score_t1
    vel3 = score_t - score_t3

    # Count how many buckets improved (simplified: use confirming_count)
    breadth = confirmation.get("confirming_count", 0)

    # Persist: how many of last 3 scans had score >= 35
    persist = sum(1 for h in ticker_hist[-3:] if h["score"] >= 35)

    accel_bonus = 0.0
    if score_t >= 35 and breadth >= 2 and persist >= 2:
        accel_bonus = min(0.25 * vel1 + 0.15 * vel3, 8.0)
        accel_bonus = max(accel_bonus, 0.0)  # no negative bonus

    return accel_bonus
