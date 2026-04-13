"""Signal aggregator -- computes all signals for a ticker."""
import logging
import pandas as pd
from stockpulse.config.settings import load_strategies
from stockpulse.signals.technical import (
    calc_rsi_signal, calc_macd_signal, calc_ma_signal,
    calc_volume_signal, calc_breakout_signal, calc_gap_signal, calc_adx_signal,
)
from stockpulse.signals.fundamental import (
    calc_earnings_signal, calc_sec_filing_signal, calc_news_sentiment_signal,
)

logger = logging.getLogger(__name__)

def compute_all_signals(ticker: str, df: pd.DataFrame) -> dict:
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
        "news_sentiment": calc_news_sentiment_signal,
    }
    for name, calc_fn in fundamental_calculators.items():
        try:
            score = calc_fn(ticker)
            weight = signal_cfg.get(name, {}).get("weight", 0.0)
            signals[name] = {"score": score, "weight": weight, "value": score}
        except Exception:
            logger.debug("Signal %s failed for %s", name, ticker)
            signals[name] = {"score": 0.0, "weight": 0.0, "value": None}
    return signals
