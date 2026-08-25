import importlib.util
import shutil
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd
import polars as pl

from backtest_engine import BacktestEngine
from data_handler import DataHandler
from run_all_strategies import StrategyRunner
from strategy_core import TradingStrategyCore


class RegressionTests(unittest.TestCase):
    @staticmethod
    def make_handler(open_prices, close_prices=None):
        open_prices = np.asarray(open_prices, dtype=float)
        if close_prices is None:
            close_prices = open_prices.copy()
        close_prices = np.asarray(close_prices, dtype=float)
        n = len(open_prices)
        high = np.maximum(open_prices, close_prices)
        low = np.minimum(open_prices, close_prices)
        return SimpleNamespace(
            dates=np.datetime64("2020-01-01")
            + np.arange(n).astype("timedelta64[D]"),
            open=open_prices,
            high=high,
            low=low,
            close=close_prices,
        )

    @staticmethod
    def make_raw_data(dates, close, volume=None):
        close = list(close)
        if volume is None:
            volume = [1.0] * len(close)
        return pl.DataFrame({
            "date": list(dates),
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "settle": close,
            "volume": volume,
        })

    def test_rsi_extreme_values(self):
        core = object.__new__(TradingStrategyCore)
        rising = core._calculate_rsi(np.arange(1.0, 31.0), 14)
        falling = core._calculate_rsi(np.arange(30.0, 0.0, -1.0), 14)
        flat = core._calculate_rsi(np.ones(30), 14)

        self.assertAlmostEqual(rising[-1], 100.0)
        self.assertAlmostEqual(falling[-1], 0.0)
        self.assertAlmostEqual(flat[-1], 50.0)

    def test_execution_price_uses_next_open_and_backtest_alignment(self):
        handler = self.make_handler(
            [10.0, 20.0, 30.0, 40.0],
            [100.0, 200.0, 300.0, 400.0],
        )
        strategy = TradingStrategyCore(handler, "EWMA", span=2)
        signal = np.array([1.0, 0.0, 0.0, 0.0])
        position, actions = strategy._generate_position_from_signals(signal)
        processed = strategy._create_processed_data(
            np.zeros(4), signal, position, actions
        )

        np.testing.assert_array_equal(
            processed["ExecutionPrice"], handler.open
        )
        backtester = BacktestEngine(strategy)
        result = backtester.run_backtest()
        np.testing.assert_allclose(
            result["StrategyReturn"],
            [0.0, 0.5, 1.0 / 3.0, 0.0],
        )

    def test_data_handler_sorts_and_casts_numeric_arrays(self):
        handler = DataHandler.__new__(DataHandler)
        handler.raw_data = self.make_raw_data(
            ["2020-01-02", "2020-01-01"],
            [2, 1],
            volume=[1, None],
        )
        result = handler.preprocess_data()

        self.assertEqual(
            result.raw_data["date"].dt.strftime("%Y-%m-%d").to_list(),
            ["2020-01-01", "2020-01-02"],
        )
        self.assertEqual(result.close.dtype, np.dtype("float64"))
        self.assertEqual(result.volume.dtype, np.dtype("float64"))
        self.assertEqual(result.volume.tolist(), [0.0, 1.0])

    def test_data_handler_rejects_missing_price_instead_of_backfilling(self):
        handler = DataHandler.__new__(DataHandler)
        handler.raw_data = self.make_raw_data(
            ["2020-01-01", "2020-01-02"],
            [None, 2.0],
        )

        with self.assertRaisesRegex(ValueError, "close.*缺失"):
            handler.preprocess_data()

    def test_data_handler_rejects_duplicate_dates(self):
        handler = DataHandler.__new__(DataHandler)
        handler.raw_data = self.make_raw_data(
            ["2020-01-01", "2020-01-01"],
            [1.0, 2.0],
        )

        with self.assertRaisesRegex(ValueError, "重复日期"):
            handler.preprocess_data()

    @unittest.skipUnless(
        importlib.util.find_spec("openpyxl"),
        "openpyxl is required for Excel export",
    )
    def test_save_to_excel_does_not_mutate_trade_dates(self):
        output_dir = Path(__file__).resolve().parent / "_test_excel_output"
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir()
        try:
            runner = StrategyRunner.__new__(StrategyRunner)
            runner.output_dir = output_dir
            runner.results = [{
                "strategy_name": "EWMA_30",
                "display_name": "EWMA Long-Short",
                "strategy_type": "EWMA",
                "cumulative_return": 1.1,
                "annualized_return": 0.1,
                "max_drawdown": -0.1,
                "total_trades": 1,
                "win_rate": 1.0,
                "avg_trade_return": 0.1,
                "parameters": "{'span': 30}",
            }]
            trade_df = pd.DataFrame({
                "Date": pd.to_datetime(["2020-01-01"]),
                "Close": [100.0],
                "ExecutionPrice": [100.0],
                "TradingSignal": [1.0],
                "Action": ["buy"],
                "Position": [1.0],
            })
            runner.strategy_data = {
                "EWMA_30": {
                    "processed_data": {},
                    "trade_df": trade_df,
                    "result": runner.results[0],
                }
            }

            runner.save_to_excel()
            runner.save_to_excel()

            self.assertTrue(pd.api.types.is_datetime64_any_dtype(trade_df["Date"]))
            self.assertTrue((output_dir / "strategy_results.xlsx").exists())
        finally:
            shutil.rmtree(output_dir)

    def test_runner_resets_state_between_runs(self):
        result = {"strategy_name": "dummy", "strategy_type": "EWMA"}
        runner = StrategyRunner.__new__(StrategyRunner)
        runner.results = []
        runner.strategy_data = {}
        runner.failures = []

        with patch.object(StrategyRunner, "load_data", return_value=object()), \
             patch.object(StrategyRunner, "run_strategy", return_value=result), \
             patch.object(StrategyRunner, "create_visualization"):
            first = runner.run_all_strategies()
            second = runner.run_all_strategies()

        self.assertEqual(len(first), 10)
        self.assertEqual(len(second), 10)
        self.assertEqual(len(runner.failures), 0)

    def test_runner_raises_after_any_strategy_failure(self):
        result = {"strategy_name": "dummy", "strategy_type": "EWMA"}
        runner = StrategyRunner.__new__(StrategyRunner)
        runner.results = []
        runner.strategy_data = {}
        runner.failures = []
        calls = 0

        def run_one(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ValueError("synthetic failure")
            return result

        with patch.object(StrategyRunner, "load_data", return_value=object()), \
             patch.object(StrategyRunner, "run_strategy", side_effect=run_one), \
             patch.object(StrategyRunner, "create_visualization"):
            with self.assertRaisesRegex(RuntimeError, "1/10"):
                runner.run_all_strategies()

        self.assertEqual(len(runner.failures), 1)
        self.assertEqual(len(runner.results), 9)


if __name__ == "__main__":
    unittest.main()
