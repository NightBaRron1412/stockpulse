"""Momentum + Catalyst strategy -- default StockPulse strategy."""
import logging
from stockpulse.strategies.base_strategy import StockPulseStrategy
from stockpulse.data.provider import get_price_history
from stockpulse.signals.engine import compute_all_signals
from stockpulse.signals.composite import compute_composite_score

logger = logging.getLogger(__name__)

class MomentumCatalystStrategy(StockPulseStrategy):
    parameters = {"buy_threshold": 40, "exit_threshold": 10, "max_positions": 10,
        "universe": ["AAPL", "MSFT", "NVDA", "AMD", "GOOGL", "AMZN", "TSLA", "META"]}

    def on_trading_iteration(self):
        universe = self.parameters.get("universe", [])
        buy_threshold = self.parameters.get("buy_threshold", 40)
        exit_threshold = self.parameters.get("exit_threshold", 10)
        for position in self.get_positions():
            ticker = position.asset.symbol
            try:
                df = get_price_history(ticker, period="6mo")
                if df.empty:
                    continue
                signals = compute_all_signals(ticker, df)
                composite = compute_composite_score(signals)
                if composite < exit_threshold:
                    self.sell_all(ticker)
                    logger.info("EXIT %s: composite %.1f < %.1f", ticker, composite, exit_threshold)
            except Exception:
                logger.debug("Exit check failed for %s", ticker)
        current_holdings = {p.asset.symbol for p in self.get_positions()}
        max_pos = self.parameters.get("max_positions", 10)
        if len(current_holdings) >= max_pos:
            return
        for ticker in universe:
            if ticker in current_holdings or len(current_holdings) >= max_pos:
                continue
            try:
                df = get_price_history(ticker, period="6mo")
                if df.empty or len(df) < 50:
                    continue
                signals = compute_all_signals(ticker, df)
                composite = compute_composite_score(signals)
                if composite > buy_threshold:
                    pos_size = self.get_position_size()
                    if pos_size > 0:
                        price = self.get_last_price(ticker)
                        if price and price > 0:
                            qty = int(pos_size / price)
                            if qty > 0:
                                order = self.create_order(ticker, qty, "buy")
                                self.submit_order(order)
                                current_holdings.add(ticker)
                                logger.info("ENTRY %s: composite %.1f, qty %d", ticker, composite, qty)
            except Exception:
                logger.debug("Entry scan failed for %s", ticker)
