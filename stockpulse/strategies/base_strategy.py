"""Base strategy interface for StockPulse strategies."""
from lumibot.strategies import Strategy

class StockPulseStrategy(Strategy):
    parameters = {"buy_threshold": 40, "exit_threshold": 10, "max_positions": 10, "position_size": "equal_weight"}

    def initialize(self):
        self.sleeptime = "1D"
        self.set_market("NYSE")

    def get_position_size(self):
        cash = self.get_cash()
        max_pos = self.parameters.get("max_positions", 10)
        current_positions = len(self.get_positions())
        available_slots = max_pos - current_positions
        if available_slots <= 0:
            return 0
        return cash / available_slots
