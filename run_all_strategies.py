import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from data_handler import DataHandler
from strategy_core import TradingStrategyCore
from backtest_engine import BacktestEngine
from visualization import StrategyVisualizer

class StrategyRunner:
    """运行所有策略并保存结果"""

    def __init__(self, data_path, output_dir="results"):
        self.data_path = data_path
        self.output_dir = output_dir
        self.results = []
        self.strategy_data = {}

        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(os.path.join(output_dir, "plots"), exist_ok=True)

    def load_data(self, years=5):
        """加载最近N年的数据"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=years*365)

        print(f"加载数据: {start_date.date()} 至 {end_date.date()}")

        data_loader = DataHandler(self.data_path, file_type='parquet')
        data_loader.preprocess_data(
            start_date=start_date,
            end_date=end_date
        )

        return data_loader

    def run_strategy(self, data_loader, strategy_type, strategy_name, **params):
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
                days = len(strategy.processed_data['Date'])
                years = days / 365
                annualized_return = cumulative_return ** (1/years) - 1 if years > 0 else 0

                # 计算最大回撤
                cumulative_returns = strategy.processed_data['CumulativeReturn']
                running_max = np.maximum.accumulate(cumulative_returns)
                drawdown = (cumulative_returns - running_max) / running_max
                max_drawdown = np.min(drawdown)

                # 计算交易次数（买卖各算一次）
                total_trades = sum(1 for action in strategy.processed_data['ActionStates']
                                  if action in ['buy', 'sell'])

                # 计算胜率、平均收益（配对 buy→sell 计算）
                if trade_df is not None and len(trade_df) > 0:
                    trades = []
                    entry_price = None
                    for i in range(len(trade_df)):
                        action = trade_df.iloc[i]['Action']
                        if action == 'buy' and entry_price is None:
                            entry_price = trade_df.iloc[i]['ExecutionPrice']
                            entry_date = trade_df.iloc[i]['Date']
                        elif action == 'sell' and entry_price is not None:
                            exit_price = trade_df.iloc[i]['ExecutionPrice']
                            exit_date = trade_df.iloc[i]['Date']
                            trade_return = (exit_price - entry_price) / entry_price
                            trades.append({
                                'entry_date': entry_date,
                                'exit_date': exit_date,
                                'return': trade_return
                            })
                            entry_price = None

                    if trades:
                        winning_trades = sum(1 for t in trades if t['return'] > 0)
                        win_rate = winning_trades / len(trades)
                        avg_return = np.mean([t['return'] for t in trades])
                    else:
                        win_rate = 0
                        avg_return = 0
                else:
                    win_rate = 0
                    avg_return = 0

                result = {
                    'strategy_name': strategy_name,
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
        adapter = type('_Adapter', (), {
            'processed_data': processed,
            'indicator_name': next(k for k in processed
                if k not in ('Date', 'Close', 'ExecutionPrice', 'TradingSignal',
                             'Position', 'ActionStates', 'Return', 'StrategyReturn',
                             'CumulativeReturn'))
        })()

        visualizer = StrategyVisualizer(adapter, data_loader)

        # 创建自定义图表
        fig, axes = plt.subplots(3, 1, figsize=(14, 12))

        # 1. 价格和指标图
        dates = data_loader.dates
        close_prices = data['processed_data']['Close']

        # 获取指标数据
        indicator_keys = [k for k in data['processed_data'].keys()
                         if k not in ['Date', 'Close', 'ExecutionPrice', 'TradingSignal',
                                     'Position', 'ActionStates', 'Return', 'StrategyReturn', 'CumulativeReturn']]

        ax1 = axes[0]
        ax1.plot(dates, close_prices, label='Price', color='black', linewidth=1)

        for key in indicator_keys:
            if key in data['processed_data']:
                ax1.plot(dates, data['processed_data'][key], label=key, linewidth=2)

        # 标记交易信号
        action_states = data['processed_data']['ActionStates']
        buy_mask = action_states == 'buy'
        sell_mask = action_states == 'sell'

        ax1.scatter(dates[buy_mask], close_prices[buy_mask],
                   marker='^', color='green', s=100, label='Buy', zorder=5)
        ax1.scatter(dates[sell_mask], close_prices[sell_mask],
                   marker='v', color='red', s=100, label='Sell', zorder=5)

        ax1.set_title(f'{strategy_name} - Price and Indicators')
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # 2. 累计收益图
        ax2 = axes[1]
        cumulative_returns = data['processed_data']['CumulativeReturn']
        ax2.plot(dates, cumulative_returns, label='Cumulative Return', color='blue', linewidth=2)
        ax2.axhline(y=1, color='gray', linestyle='--', alpha=0.5)
        ax2.set_title('Cumulative Returns')
        ax2.legend()
        ax2.grid(True, alpha=0.3)

        # 3. 持仓图
        ax3 = axes[2]
        position = data['processed_data']['Position']
        ax3.fill_between(dates, 0, position, where=position>=0,
                        color='green', alpha=0.3, label='Long')
        ax3.fill_between(dates, 0, position, where=position<0,
                        color='red', alpha=0.3, label='Short')
        ax3.axhline(y=0, color='black', linewidth=0.5)
        ax3.set_title('Position')
        ax3.legend()
        ax3.grid(True, alpha=0.3)

        plt.tight_layout()

        # 保存图片
        plot_path = os.path.join(self.output_dir, "plots", f"{strategy_name}.png")
        plt.savefig(plot_path, dpi=150, bbox_inches='tight')
        plt.close()

        print(f"  图表已保存: {plot_path}")

    def run_all_strategies(self, years=5):
        """运行所有策略"""
        print("=" * 60)
        print("开始运行所有策略")
        print("=" * 60)

        # 加载数据
        data_loader = self.load_data(years=years)

        # 定义要测试的策略
        strategies = [
            # (策略类型, 策略名称, 参数)
            ('EWMA', 'EWMA_30', {'span': 30}),
            ('EWMA_LONG_ONLY', 'EWMA_LONG_ONLY_30', {'span': 30}),
            ('MACD', 'MACD_12_26_9', {'fast_period': 12, 'slow_period': 26, 'signal_period': 9}),
            ('DONCHIAN', 'DONCHIAN_20', {'channel_period': 20}),
            ('DONCHIAN', 'DONCHIAN_50', {'channel_period': 50}),
            ('BOLLINGER', 'BOLLINGER_20_2', {'bb_period': 20, 'bb_std': 2.0}),
            ('BOLLINGER', 'BOLLINGER_20_1.5', {'bb_period': 20, 'bb_std': 1.5}),
            ('RSI', 'RSI_14_30_70', {'rsi_period': 14, 'oversold_threshold': 30, 'overbought_threshold': 70}),
            ('TMA', 'TMA_5_20_60', {'tma_fast': 5, 'tma_medium': 20, 'tma_slow': 60}),
            ('TMA', 'TMA_10_30_90', {'tma_fast': 10, 'tma_medium': 30, 'tma_slow': 90}),
        ]

        # 运行所有策略
        for strategy_type, strategy_name, params in strategies:
            result = self.run_strategy(data_loader, strategy_type, strategy_name, **params)
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
            'strategy_name', 'strategy_type', 'cumulative_return', 'annualized_return',
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
        html_path = os.path.join(self.output_dir, "strategy_report.html")

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
                <p>• 最佳累计收益率: {max(self.results, key=lambda r: r['cumulative_return'])['strategy_name']} ({max(self.results, key=lambda r: r['cumulative_return'])['cumulative_return'] - 1:.2%})</p>
                <p>• 最佳年化收益率: {max(self.results, key=lambda r: r['annualized_return'])['strategy_name']} ({max(self.results, key=lambda r: r['annualized_return'])['annualized_return']:.2%})</p>
                <p>• 图表保存位置: {os.path.join(self.output_dir, "plots")}</p>
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
        data_path="data/AUFI_WI.parquet",
        output_dir="results"
    )

    # 运行所有策略（最近5年）
    results = runner.run_all_strategies(years=5)

    if results:
        # 保存结果到Excel
        excel_path = runner.save_to_excel()

        print("\n" + "=" * 60)
        print("策略运行完成!")
        print("=" * 60)
        print(f"结果文件: {excel_path}")
        print(f"图表目录: {os.path.join('results', 'plots')}")
        print(f"HTML报告: {os.path.join('results', 'strategy_report.html')}")
    else:
        print("没有成功运行的策略")

if __name__ == "__main__":
    main()