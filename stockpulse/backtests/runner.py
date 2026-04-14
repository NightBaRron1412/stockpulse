"""Lumibot backtest runner for StockPulse strategies."""
import logging
import sys
from datetime import datetime
from pathlib import Path
from stockpulse.config.settings import load_strategies, load_watchlists

logger = logging.getLogger(__name__)
RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / "backtests" / "results"

def run_backtest(start_date: str | None = None, end_date: str | None = None, strategy_name: str = "momentum_catalyst"):
    from lumibot.backtesting import YahooDataBacktesting
    start = datetime.strptime(start_date or "2024-01-01", "%Y-%m-%d")
    end = datetime.strptime(end_date or "2025-12-31", "%Y-%m-%d")
    strat_cfg = load_strategies()
    bt_cfg = strat_cfg.get("backtesting", {})
    wl = load_watchlists()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if strategy_name == "momentum_catalyst":
        from stockpulse.strategies.momentum_catalyst import MomentumCatalystStrategy
        # Backtest uses technical-only scores (range ~-35 to +35),
        # NOT the full composite score (range -100 to +100).
        # So thresholds must be scaled for the backtest score range.
        MomentumCatalystStrategy.parameters.update({
            "buy_threshold": 8,    # ~top 25% of technical score range
            "exit_threshold": -5,  # exit when score turns mildly negative
            "max_positions": bt_cfg.get("max_positions", 8),
            "universe": wl.get("user", ["AAPL", "MSFT", "NVDA", "AMD"])})
        print(f"Running backtest: {strategy_name}")
        print(f"  Period: {start.date()} to {end.date()}")
        print(f"  Initial cash: ${bt_cfg.get('initial_cash', 100000):,.0f}")
        print(f"  Universe: {MomentumCatalystStrategy.parameters['universe']}")
        results = MomentumCatalystStrategy.backtest(YahooDataBacktesting, start, end,
            budget=bt_cfg.get("initial_cash", 100000), name="StockPulse Momentum+Catalyst")
        print("\nBacktest complete. Check Lumibot's output for detailed results.")
        return results
    else:
        print(f"Unknown strategy: {strategy_name}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="StockPulse Backtest Runner")
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--strategy", default="momentum_catalyst")
    args = parser.parse_args()
    run_backtest(args.start, args.end, args.strategy)
