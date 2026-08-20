import os
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import polars as pl
from data_handler import DataHandler
from strategy_core import TradingStrategyCore
from backtest_engine import BacktestEngine
from visualization import StrategyVisualizer

_BASE_DIR = Path(__file__).resolve().parent


class StrategyRunner:
    """运行所有策略并保存结果"""

    def __init__(self, data_path, output_dir="results"):
        self.data_path = Path(data_path).expanduser()
        if not self.data_path.is_absolute():
            self.data_path = _BASE_DIR / self.data_path
        self.data_path = self.data_path.resolve()

        self.output_dir = Path(output_dir).expanduser()
        if not self.output_dir.is_absolute():
            self.output_dir = _BASE_DIR / self.output_dir
        self.output_dir = self.output_dir.resolve()

        self.results = []
        self.strategy_data = {}

        # 创建输出目录
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.output_dir / "plots", exist_ok=True)

    def load_data(self):
        """加载最近N年的数据"""
        max_date_str = pl.scan_parquet(self.data_path).select(
            pl.col("date").max()
        ).collect().item()
        end_date = datetime.strptime(max_date_str, "%Y-%m-%d")
        start_date = datetime(2020, 1, 1)

        print(f"加载数据: {start_date.date()} 至 {end_date.date()}")

        data_loader = DataHandler(self.data_path, file_type='parquet')
        data_loader.preprocess_data(
            start_date=start_date,
            end_date=end_date
        )

        return data_loader

    def run_strategy(self, data_loader, strategy_type, strategy_name, display_name=None, **params):
        """运行单个策略"""
        print(f"\n运行策略: {strategy_name}")
        print(f"参数: {params}")

        try:
            # 初始化策略
            strategy = TradingStrategyCore(data_loader, strategy_type=strategy_type, **params)

            # 生成信号
            strategy.generate_signals()

            # 运行回测
            backtester = BacktestEngine(strategy)
            backtester.run_backtest()

            # 生成交易记录
            trade_df = backtester.generate_trading_records()

            if strategy.processed_data is not None:
                # 计算性能指标
                cumulative_return = strategy.processed_data['CumulativeReturn'][-1]

                # 计算年化收益率（cumulative_return 已是乘数，如 1.5 = +50%，0.8 = -20%）
                # 用日期跨度而非交易天数，避免少算年数拉高年化
                # 权益乘数 ≤ 0 时（空头单日亏超 100% 等）幂运算会出复数，记为 NaN
                first_date = strategy.processed_data['Date'][0]
                last_date = strategy.processed_data['Date'][-1]
                days = (last_date - first_date).astype('timedelta64[D]').astype(int)
                years = days / 365.25
                if years > 0 and cumulative_return > 0:
                    annualized_return = cumulative_return ** (1 / years) - 1
                else:
                    annualized_return = float('nan')

                # 计算最大回撤；峰值 ≤ 0 时跳过除法，避免 -inf/NaN 污染
                cumulative_returns = strategy.processed_data['CumulativeReturn']
                running_max = np.maximum.accumulate(cumulative_returns)
                valid_peak = running_max > 0
                if np.any(valid_peak):
                    drawdown = np.full(len(cumulative_returns), np.nan, dtype=float)
                    drawdown[valid_peak] = (
                        (cumulative_returns[valid_peak] - running_max[valid_peak])
                        / running_max[valid_peak]
                    )
                    max_drawdown = float(np.nanmin(drawdown))
                else:
                    max_drawdown = float('nan')

                # 计算交易次数、胜率、平均收益（统一基于配对交易 round trip）
                trades_df = backtester.get_trades()
                if trades_df is not None and len(trades_df) > 0:
                    total_trades = len(trades_df)
                    winning_trades = (trades_df['return'] > 0).sum()
                    win_rate = winning_trades / total_trades
                    avg_return = trades_df['return'].mean()
                else:
                    total_trades = 0
                    win_rate = 0
                    avg_return = 0

                result = {
                    'strategy_name': strategy_name,
                    'display_name': display_name or strategy_name,
                    'strategy_type': strategy_type,
                    'cumulative_return': cumulative_return,
                    'annualized_return': annualized_return,
                    'max_drawdown': max_drawdown,
                    'total_trades': total_trades,
                    'win_rate': win_rate,
                    'avg_trade_return': avg_return,
                    'parameters': str(params)
                }

                # 保存策略数据
                self.strategy_data[strategy_name] = {
                    'processed_data': strategy.processed_data,
                    'trade_df': trade_df,
                    'result': result
                }

                print(f"  累计收益率: {cumulative_return - 1:.2%}")
                print(f"  年化收益率: {annualized_return:.2%}")
                print(f"  最大回撤: {max_drawdown:.2%}")
                print(f"  总交易次数: {total_trades}")
                print(f"  胜率: {win_rate:.2%}")
                print(f"  平均交易收益: {avg_return:.2%}")

                return result
            else:
                print("错误: 没有生成处理数据")
                return None

        except Exception as e:
            print(f"错误: {str(e)}")
            return None

    def create_visualization(self, strategy_name, data_loader):
        if strategy_name not in self.strategy_data:
            return

        data = self.strategy_data[strategy_name]
        processed = data['processed_data']
        # Provide data and strategy type for indicator-axis handling.
        from types import SimpleNamespace
        adapter = SimpleNamespace(
            processed_data=processed,
            strategy_type=data['result']['strategy_type'],
        )

        visualizer = StrategyVisualizer(adapter, data_loader)
        plot_path = self.output_dir / "plots" / f"{strategy_name}.png"
        visualizer.plot_results(save_path=plot_path, show=False, title=strategy_name)
        print(f"  图表已保存: {plot_path}")

    def run_all_strategies(self):
        """运行所有策略"""
        print("=" * 60)
        print("开始运行所有策略")
        print("=" * 60)

        # 加载数据
        data_loader = self.load_data()

        # 定义要测试的策略
        strategies = [
            # (策略类型, 策略名称, 参数, 显示名称)
            ('EWMA', 'EWMA_30', {'span': 30}, 'EWMA Long-Short'),
            ('EWMA_LONG_ONLY', 'EWMA_LONG_ONLY_30', {'span': 30}, 'EWMA Long-Only'),
            ('MACD', 'MACD_12_26_9', {'fast_period': 12, 'slow_period': 26, 'signal_period': 9}, 'MACD'),
            ('DONCHIAN', 'DONCHIAN_20', {'channel_period': 20}, 'Donchian (20)'),
            ('DONCHIAN', 'DONCHIAN_50', {'channel_period': 50}, 'Donchian (50)'),
            ('BOLLINGER', 'BOLLINGER_20_2', {'bb_period': 20, 'bb_std': 2.0}, 'Bollinger (20, 2.0)'),
            ('BOLLINGER', 'BOLLINGER_20_1.5', {'bb_period': 20, 'bb_std': 1.5}, 'Bollinger (20, 1.5)'),
            ('RSI', 'RSI_14_30_70', {'rsi_period': 14, 'oversold_threshold': 30, 'overbought_threshold': 70}, 'RSI'),
            ('TMA', 'TMA_5_20_60', {'tma_fast': 5, 'tma_medium': 20, 'tma_slow': 60}, 'TMA (5/20/60)'),
            ('TMA', 'TMA_10_30_90', {'tma_fast': 10, 'tma_medium': 30, 'tma_slow': 90}, 'TMA (10/30/90)'),
        ]

        # 运行所有策略
        for strategy_type, strategy_name, params, display_name in strategies:
            result = self.run_strategy(data_loader, strategy_type, strategy_name, display_name=display_name, **params)
            if result:
                self.results.append(result)
                # 创建可视化
                self.create_visualization(strategy_name, data_loader)

        return self.results

    def save_to_excel(self):
        """保存结果到Excel文件"""
        if not self.results:
            print("没有结果可保存")
            return

        # 创建DataFrame
        df = pd.DataFrame(self.results)

        # 重新排列列顺序
        columns_order = [
            'strategy_name', 'display_name', 'strategy_type', 'cumulative_return', 'annualized_return',
            'max_drawdown', 'total_trades', 'win_rate', 'avg_trade_return', 'parameters'
        ]
        df = df[columns_order]

        # 格式化数值列（cumulative_return 是乘数，需减 1 转为收益率）
        numeric_cols = ['annualized_return', 'max_drawdown', 'win_rate', 'avg_trade_return']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = df[col].apply(lambda x: f"{x:.2%}" if pd.notnull(x) else "")
        if 'cumulative_return' in df.columns:
            df['cumulative_return'] = df['cumulative_return'].apply(lambda x: f"{x - 1:.2%}" if pd.notnull(x) else "")

        # 保存到Excel
        excel_path = os.path.join(self.output_dir, "strategy_results.xlsx")

        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            # 保存汇总结果
            df.to_excel(writer, sheet_name='Summary', index=False)

            # 保存每个策略的详细交易记录
            for strategy_name, data in self.strategy_data.items():
                if data['trade_df'] is not None:
                    trade_df = data['trade_df']
                    if isinstance(trade_df, pd.DataFrame) and len(trade_df) > 0:
                        # 格式化日期列
                        if 'Date' in trade_df.columns:
                            trade_df['Date'] = trade_df['Date'].dt.strftime('%Y-%m-%d')

                        # 截断长名称以适应Excel工作表名称限制
                        sheet_name = strategy_name[:31]  # Excel工作表名称最多31字符
                        trade_df.to_excel(writer, sheet_name=sheet_name, index=False)

        print(f"\n结果已保存到Excel: {excel_path}")

        # 创建HTML格式的汇总报告
        self.create_html_report(df)

        return excel_path

    def create_html_report(self, df):
        """创建HTML格式的报告"""
        html_path = self.output_dir / "strategy_report.html"
        plot_dir = self.output_dir / "plots"
        try:
            plot_dir_display = plot_dir.relative_to(_BASE_DIR).as_posix()
        except ValueError:
            plot_dir_display = plot_dir.name + "/"

        finite_cumulative = [
            result for result in self.results
            if np.isfinite(result['cumulative_return'])
        ]
        best_cumulative = max(
            finite_cumulative,
            key=lambda result: result['cumulative_return'],
            default=None,
        )
        best_cumulative_text = (
            f"{best_cumulative['strategy_name']} "
            f"({best_cumulative['cumulative_return'] - 1:.2%})"
            if best_cumulative is not None else "N/A"
        )

        finite_annualized = [
            result for result in self.results
            if np.isfinite(result['annualized_return'])
        ]
        best_annualized = max(
            finite_annualized,
            key=lambda result: result['annualized_return'],
            default=None,
        )
        best_annualized_text = (
            f"{best_annualized['strategy_name']} "
            f"({best_annualized['annualized_return']:.2%})"
            if best_annualized is not None else "N/A"
        )

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>策略回测报告</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                h1 {{ color: #333; }}
                table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
                th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
                tr:nth-child(even) {{ background-color: #f9f9f9; }}
                .positive {{ color: green; font-weight: bold; }}
                .negative {{ color: red; font-weight: bold; }}
                .summary {{ margin-top: 30px; padding: 20px; background-color: #f5f5f5; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <h1>策略回测报告</h1>
            <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p>数据范围: 最近5年</p>

            <h2>策略性能汇总</h2>
            {df.to_html(index=False, classes='dataframe')}

            <div class="summary">
                <h2>报告摘要</h2>
                <p>• 测试策略总数: {len(self.results)}</p>
                <p>• 最佳累计收益率: {best_cumulative_text}</p>
                <p>• 最佳年化收益率: {best_annualized_text}</p>
                <p>• 图表保存位置: {plot_dir_display}</p>
            </div>
        </body>
        </html>
        """

        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        print(f"HTML报告已保存: {html_path}")

def main():
    """主函数"""
    # 设置中文字体支持
    plt.rcParams['font.sans-serif'] = ['SimHei']
    plt.rcParams['axes.unicode_minus'] = False

    # 创建策略运行器
    runner = StrategyRunner(
        data_path=_BASE_DIR / "data" / "AUFI_WI.parquet",
        output_dir=_BASE_DIR / "results"
    )

    # 运行所有策略（最近5年）
    results = runner.run_all_strategies()

    if results:
        # 保存结果到Excel
        excel_path = runner.save_to_excel()

        print("\n" + "=" * 60)
        print("策略运行完成!")
        print("=" * 60)
        print(f"结果文件: {excel_path}")
        print(f"图表目录: {runner.output_dir / 'plots'}")
        print(f"HTML报告: {runner.output_dir / 'strategy_report.html'}")
    else:
        print("没有成功运行的策略")

if __name__ == "__main__":
    main()
