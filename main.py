from datetime import datetime

from backtest_engine import BacktestEngine
from data_handler import DataHandler
from strategy_core import TradingStrategyCore
from visualization import StrategyVisualizer

if __name__ == "__main__":
    data_loader = DataHandler("data/AUFI_WI.parquet", file_type="parquet")
    data_loader.preprocess_data(
        start_date=datetime(2020, 1, 1), end_date=datetime(2026, 5, 15)
    )
    # 初始化策略核心
    strategy = TradingStrategyCore(data_loader, strategy_type="EWMA_LONG_ONLY", span=30)
    # 初始化其他模块
    backtester = BacktestEngine(strategy)
    visualizer = StrategyVisualizer(strategy, data_loader)
    # 执行流程
    strategy.generate_signals()
    backtester.run_backtest()
    trade_record = backtester.generate_trading_records()  # 改为通过回测引擎调用
    visualizer.plot_results()
