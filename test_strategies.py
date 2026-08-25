from pathlib import Path
from datetime import datetime
import polars as pl
from data_handler import DataHandler
from strategy_core import TradingStrategyCore
from backtest_engine import BacktestEngine
from visualization import StrategyVisualizer

_BASE_DIR = Path(__file__).resolve().parent
_DATA_PATH = _BASE_DIR / "data" / "AUFI_WI.parquet"

def test_all_strategies():
    """测试所有可用的交易策略"""

    # 初始化数据处理
    data_loader = DataHandler(_DATA_PATH, file_type='parquet')
    data_loader.preprocess_data(
        start_date=datetime(2020, 1, 1),
        end_date=datetime.strptime(
            pl.scan_parquet(_DATA_PATH).select(pl.col("date").max()).collect().item(),
            "%Y-%m-%d"
        )
    )

    strategies_to_test = [
        # (策略类型, 参数, 描述)
        ('EWMA', {'span': 30}, "EWMA策略(允许做空)"),
        ('EWMA_LONG_ONLY', {'span': 30}, "EWMA策略(仅做多)"),
        ('MACD', {'fast_period': 12, 'slow_period': 26, 'signal_period': 9}, "MACD策略"),
        ('DONCHIAN', {'channel_period': 20}, "唐奇安通道策略(20日)"),
        ('DONCHIAN', {'channel_period': 50}, "唐奇安通道策略(50日)"),
        ('BOLLINGER', {'bb_period': 20, 'bb_std': 2.0}, "布林带策略(2.0σ)"),
        ('BOLLINGER', {'bb_period': 20, 'bb_std': 1.5}, "布林带策略(1.5σ)"),
        ('RSI', {'rsi_period': 14, 'oversold_threshold': 30, 'overbought_threshold': 70}, "RSI均值回归策略"),
        ('TMA', {'tma_fast': 5, 'tma_medium': 20, 'tma_slow': 60}, "三均线趋势策略(5/20/60)"),
        ('TMA', {'tma_fast': 10, 'tma_medium': 30, 'tma_slow': 90}, "三均线趋势策略(10/30/90)"),
    ]

    results = []

    for strategy_type, params, description in strategies_to_test:
        print(f"\n{'='*60}")
        print(f"测试策略: {description}")
        print(f"策略类型: {strategy_type}")
        print(f"参数: {params}")
        print('='*60)

        try:
            # 初始化策略
            strategy = TradingStrategyCore(data_loader, strategy_type=strategy_type, **params)

            # 生成信号
            strategy.generate_signals()

            # 运行回测
            backtester = BacktestEngine(strategy)
            backtester.run_backtest()

            # 生成交易记录
            trade_record = backtester.generate_trading_records()

            # 计算基本统计
            if strategy.processed_data is not None:
                cumulative_return = strategy.processed_data['CumulativeReturn'][-1]
                trades_df = backtester.get_trades()
                total_trades = len(trades_df) if trades_df is not None else 0

                print(f"累计收益率: {cumulative_return - 1:.2%}")
                print(f"总交易次数: {total_trades}")

                results.append({
                    'strategy': description,
                    'type': strategy_type,
                    'cumulative_return': cumulative_return,
                    'total_trades': total_trades,
                    'success': True
                })
            else:
                print("错误: 没有生成处理数据")
                results.append({
                    'strategy': description,
                    'type': strategy_type,
                    'error': 'No processed data',
                    'success': False
                })

        except Exception as e:
            print(f"错误: {str(e)}")
            results.append({
                'strategy': description,
                'type': strategy_type,
                'error': str(e),
                'success': False
            })

    # 打印汇总结果
    print(f"\n{'='*60}")
    print("策略测试汇总")
    print('='*60)

    successful_results = [r for r in results if r['success']]
    if successful_results:
        # 按收益率排序
        successful_results.sort(key=lambda x: x['cumulative_return'], reverse=True)

        print("\n策略表现排名:")
        for i, result in enumerate(successful_results, 1):
            print(f"{i}. {result['strategy']}:")
            print(f"   累计收益率: {result['cumulative_return'] - 1:.2%}")
            print(f"   交易次数: {result['total_trades']}")

    # 显示失败策略
    failed_results = [r for r in results if not r['success']]
    if failed_results:
        print(f"\n失败策略 ({len(failed_results)}个):")
        for result in failed_results:
            print(f"- {result['strategy']}: {result.get('error', '未知错误')}")
        raise AssertionError(f"{len(failed_results)} 个策略测试失败")

def visualize_strategy(strategy_type='MACD', **kwargs):
    """可视化特定策略"""
    # 初始化数据处理
    data_loader = DataHandler(_DATA_PATH, file_type='parquet')
    data_loader.preprocess_data(
        start_date=datetime(2020, 1, 1),
        end_date=datetime.strptime(
            pl.scan_parquet(_DATA_PATH).select(pl.col("date").max()).collect().item(),
            "%Y-%m-%d"
        )
    )

    # 初始化策略
    strategy = TradingStrategyCore(data_loader, strategy_type=strategy_type, **kwargs)

    # 初始化其他模块
    backtester = BacktestEngine(strategy)
    visualizer = StrategyVisualizer(strategy, data_loader)

    # 执行流程
    strategy.generate_signals()
    backtester.run_backtest()
    trade_record = backtester.generate_trading_records()

    # 可视化结果
    visualizer.plot_results()

    return strategy

if __name__ == "__main__":
    print("开始测试所有交易策略...")
    test_all_strategies()

    # 可以选择可视化某个策略
    # print("\n可视化MACD策略...")
    # strategy = visualize_strategy('MACD', fast_period=12, slow_period=26, signal_period=9)
