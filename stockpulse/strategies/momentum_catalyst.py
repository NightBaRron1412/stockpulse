"""Momentum + Catalyst strategy -- default StockPulse strategy.

Uses Lumibot's historical bars for backtesting (not live data provider).
The key difference: self.get_historical_prices() returns data as of the
simulated date, so signals reflect what you would have seen at that time.
"""
import logging
import pandas as pd
import pandas_ta as ta
from stockpulse.strategies.base_strategy import StockPulseStrategy

logger = logging.getLogger(__name__)


class MomentumCatalystStrategy(StockPulseStrategy):
    parameters = {
        "buy_threshold": 8,   # Technical-only score range is roughly -35 to +35
        "exit_threshold": -5,
        "max_positions": 8,
        "universe": ["AAPL", "MSFT", "NVDA", "AMD", "GOOGL", "AMZN", "TSLA", "META"],
    }

    def on_trading_iteration(self):
        universe = self.parameters.get("universe", [])
        buy_threshold = self.parameters.get("buy_threshold", 30)
        exit_threshold = self.parameters.get("exit_threshold", 5)

        # Check existing positions for exit
        for position in self.get_positions():
            ticker = position.asset.symbol
            try:
                score = self._compute_technical_score(ticker)
                if score is not None and score < exit_threshold:
                    self.sell_all(ticker)
                    logger.info("EXIT %s: score %.1f < %.1f", ticker, score, exit_threshold)
            except Exception:
                logger.debug("Exit check failed for %s", ticker)

        # Scan for new entries
        current_holdings = {p.asset.symbol for p in self.get_positions()}
        max_pos = self.parameters.get("max_positions", 8)

        if len(current_holdings) >= max_pos:
            return

        candidates = []
        for ticker in universe:
            if ticker in current_holdings:
                continue
            try:
                score = self._compute_technical_score(ticker)
                if score is not None and score > buy_threshold:
                    candidates.append((ticker, score))
            except Exception:
                logger.debug("Entry scan failed for %s", ticker)

        # Sort by score, enter best candidates
        candidates.sort(key=lambda x: x[1], reverse=True)
        for ticker, score in candidates:
            if len(current_holdings) >= max_pos:
                break
            try:
                pos_size = self.get_position_size()
                if pos_size > 0:
                    price = self.get_last_price(ticker)
                    if price and price > 0:
                        qty = int(pos_size / price)
                        if qty > 0:
                            order = self.create_order(ticker, qty, "buy")
                            self.submit_order(order)
                            current_holdings.add(ticker)
                            logger.info("ENTRY %s: score %.1f, qty %d @ $%.2f", ticker, score, qty, price)
            except Exception:
                logger.debug("Order failed for %s", ticker)

    def _compute_technical_score(self, ticker: str) -> float | None:
        """Compute a technical-only score using Lumibot's historical data.

        Uses only price-derived signals (no API calls to Finnhub/EDGAR)
        so backtesting runs at simulated-time speed.
        """
        try:
            bars = self.get_historical_prices(ticker, 200, "day")
            if bars is None:
                return None
            df = bars.df
            if df is None or len(df) < 50:
                return None

            # Ensure we have the right columns
            if "close" in df.columns:
                df = df.rename(columns={"close": "Close", "open": "Open",
                                        "high": "High", "low": "Low", "volume": "Volume"})

            close = df["Close"]
            current_price = float(close.iloc[-1])

            score = 0.0

            # RSI (weight ~0.07)
            rsi = ta.rsi(close, length=14)
            if rsi is not None and not rsi.dropna().empty:
                rsi_val = float(rsi.iloc[-1])
                sma50 = ta.sma(close, length=50)
                in_uptrend = sma50 is not None and float(sma50.iloc[-1]) < current_price
                if in_uptrend:
                    if rsi_val <= 40: score += 3.0
                    elif rsi_val <= 50: score += 1.5
                    elif rsi_val > 75: score -= 1.0
                else:
                    if rsi_val <= 30: score += 2.0
                    elif rsi_val > 65: score -= 1.5

            # MACD (weight ~0.07)
            macd_df = ta.macd(close, fast=12, slow=26, signal=9)
            if macd_df is not None and not macd_df.dropna().empty:
                hist_col = "MACDh_12_26_9"
                if hist_col in macd_df.columns:
                    hist = macd_df[hist_col].dropna()
                    if len(hist) >= 2:
                        curr_h = float(hist.iloc[-1])
                        prev_h = float(hist.iloc[-2])
                        std = float(hist.tail(50).std()) or 1.0
                        score += (curr_h / std) * 3.0
                        if prev_h < 0 and curr_h > 0: score += 5.0
                        elif prev_h > 0 and curr_h < 0: score -= 5.0

            # Moving Averages (weight ~0.10)
            ema20 = ta.ema(close, length=20)
            sma50 = ta.sma(close, length=50)
            sma200 = ta.sma(close, length=200)

            if ema20 is not None and not ema20.dropna().empty:
                if current_price > float(ema20.iloc[-1]): score += 3.0
                else: score -= 3.0
            if sma50 is not None and not sma50.dropna().empty:
                if current_price > float(sma50.iloc[-1]): score += 3.0
                else: score -= 3.0
            if sma200 is not None and len(sma200.dropna()) > 0:
                if current_price > float(sma200.iloc[-1]): score += 4.0
                else: score -= 4.0

            # Volume (weight ~0.14)
            if len(df) > 21:
                curr_vol = float(df["Volume"].iloc[-1])
                avg_vol = float(df["Volume"].iloc[-21:-1].mean())
                if avg_vol > 0:
                    rvol = curr_vol / avg_vol
                    price_chg = float(close.iloc[-1]) - float(close.iloc[-2])
                    direction = 1.0 if price_chg > 0 else -1.0
                    if rvol >= 2.0: score += direction * 8.0
                    elif rvol >= 1.5: score += direction * 5.0
                    elif rvol >= 1.0: score += direction * 2.0

            # Breakout (weight ~0.15)
            if len(df) >= 20:
                high_20 = float(df["High"].iloc[-20:].max())
                low_20 = float(df["Low"].iloc[-20:].min())
                rng = high_20 - low_20
                if rng > 0:
                    pos = (current_price - low_20) / rng
                    if pos > 0.95: score += 5.0
                    elif pos < 0.05: score -= 5.0
                    else: score += (pos - 0.5) * 6.0

            # ADX (weight ~0.06)
            adx_df = ta.adx(df["High"], df["Low"], df["Close"], length=14)
            if adx_df is not None and not adx_df.dropna().empty:
                adx_val = float(adx_df["ADX_14"].iloc[-1])
                if adx_val > 20:
                    plus_di = float(adx_df["DMP_14"].iloc[-1])
                    minus_di = float(adx_df["DMN_14"].iloc[-1])
                    direction = 1.0 if plus_di > minus_di else -1.0
                    score += direction * min((adx_val - 15) * 0.15, 4.0)

            return score
        except Exception as e:
            logger.debug("Technical score failed for %s: %s", ticker, e)
            return None
