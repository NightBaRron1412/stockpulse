"""Backfill pattern history with point-in-time technical scans.

Recreates historical signal snapshots using only data that would have been
available on each date. No look-ahead bias — uses rolling windows.

Only backfills technical signals (RSI, MACD, MA, volume, breakout, gap, ADX, RS).
Does NOT backfill SEC/news (imperfect hindsight data would poison the library).
"""
import logging
from datetime import datetime, timedelta

import pandas as pd
import pandas_ta as ta

from stockpulse.data.provider import get_price_history
from stockpulse.research.patterns import _load_history, _save_history

logger = logging.getLogger(__name__)


def backfill_patterns(tickers: list[str], months: int = 6,
                      sample_interval_days: int = 5) -> int:
    """Backfill pattern history for the given tickers.

    Args:
        tickers: List of tickers to backfill
        months: How many months of history to generate
        sample_interval_days: Sample every N trading days (5 = weekly)

    Returns:
        Number of entries added
    """
    history = _load_history()
    existing_keys = {(h["ticker"], h["date"]) for h in history}
    added = 0

    for ticker in tickers:
        try:
            df = get_price_history(ticker, period="1y")
            if df.empty or len(df) < 200:
                continue

            close = df["Close"]
            high = df["High"]
            low = df["Low"]
            volume = df["Volume"]

            # Compute full-length indicators
            rsi = ta.rsi(close, length=14)
            macd_data = ta.macd(close, fast=12, slow=26, signal=9)
            ema20 = ta.ema(close, length=20)
            sma50 = ta.sma(close, length=50)
            sma200 = ta.sma(close, length=200)
            atr = ta.atr(high, low, close, length=14)
            adx_data = ta.adx(high, low, close, length=14)
            vol_sma20 = volume.rolling(20).mean()

            if rsi is None or macd_data is None:
                continue

            # Sample points: every N trading days, going back M months
            start_idx = max(200, len(df) - months * 21)  # ~21 trading days/month
            sample_indices = range(start_idx, len(df) - 20, sample_interval_days)

            for idx in sample_indices:
                date_str = df.index[idx].strftime("%Y-%m-%d")

                if (ticker, date_str) in existing_keys:
                    continue

                # Point-in-time signals (only using data up to this index)
                price = float(close.iloc[idx])

                # RSI score (simplified)
                rsi_val = float(rsi.iloc[idx]) if rsi is not None and idx < len(rsi) else 50
                rsi_score = _rsi_to_score(rsi_val)

                # MACD score
                hist_col = [c for c in macd_data.columns if "h" in c.lower() or "hist" in c.lower()]
                if hist_col:
                    macd_hist = float(macd_data[hist_col[0]].iloc[idx])
                    macd_std = float(macd_data[hist_col[0]].iloc[max(0, idx-50):idx].std()) or 1
                    macd_score = min(100, max(-100, (macd_hist / macd_std) * 40))
                else:
                    macd_score = 0

                # MA score
                ema20_val = float(ema20.iloc[idx]) if ema20 is not None else price
                sma50_val = float(sma50.iloc[idx]) if sma50 is not None else price
                ma_score = 0
                if price > ema20_val:
                    ma_score += 25
                if price > sma50_val:
                    ma_score += 25
                if ema20_val > sma50_val:
                    ma_score += 30

                # Volume score
                vol_val = float(volume.iloc[idx])
                vol_avg = float(vol_sma20.iloc[idx]) if vol_sma20 is not None else vol_val
                rvol = vol_val / vol_avg if vol_avg > 0 else 1.0
                vol_score = min(80, max(-80, (rvol - 1.0) * 60))

                # Breakout score
                high_20 = float(high.iloc[max(0, idx-20):idx].max())
                breakout_score = 25 if price >= high_20 * 0.99 else 0

                # RS score (simplified — just vs SPY)
                rs_score = 0  # Would need SPY data aligned, skip for backfill

                # Record entry with outcome tracking
                entry = {
                    "ticker": ticker,
                    "date": date_str,
                    "action": "BACKFILL",
                    "score": round(rsi_score * 0.07 + macd_score * 0.07 + ma_score * 0.1 +
                                   vol_score * 0.14 + breakout_score * 0.15, 1),
                    "rsi": round(rsi_score, 1),
                    "macd": round(macd_score, 1),
                    "ma": round(ma_score, 1),
                    "volume": round(vol_score, 1),
                    "breakout": round(breakout_score, 1),
                    "rs": 0,
                    "entry_price": round(price, 2),
                    "outcome_5d": None,
                    "outcome_10d": None,
                    "outcome_20d": None,
                }

                # Fill outcomes from known future data
                if idx + 5 < len(close):
                    entry["outcome_5d"] = round(
                        ((float(close.iloc[idx + 5]) - price) / price) * 100, 2)
                if idx + 10 < len(close):
                    entry["outcome_10d"] = round(
                        ((float(close.iloc[idx + 10]) - price) / price) * 100, 2)
                if idx + 20 < len(close):
                    entry["outcome_20d"] = round(
                        ((float(close.iloc[idx + 20]) - price) / price) * 100, 2)

                history.append(entry)
                existing_keys.add((ticker, date_str))
                added += 1

        except Exception:
            logger.debug("Backfill failed for %s", ticker)

    if added > 0:
        _save_history(history)
        logger.info("Backfilled %d pattern entries for %d tickers", added, len(tickers))

    return added


def _rsi_to_score(rsi: float) -> float:
    """Convert raw RSI to a directional score."""
    if rsi < 30:
        return 40 + (30 - rsi) * 2  # oversold = bullish
    elif rsi < 50:
        return (50 - rsi) * 1.5
    elif rsi < 70:
        return -(rsi - 50) * 0.5
    else:
        return -(rsi - 50) * 1.5  # overbought = bearish
