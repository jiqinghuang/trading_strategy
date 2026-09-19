import os
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
from data_handler import DataHandler
from strategy_core import TradingStrategyCore
from backtest_engine import BacktestEngine
from visualization import StrategyVisualizer

_BASE_DIR = Path(__file__).resolve().parent

# 批量回测的策略清单（单一数据源；demo_all_strategies.py 也从这里导入）。
# (策略类型, 结果命名, 参数, 展示名)
STRATEGIES = [
    ("EWMA", "EWMA_30", {"span": 30}, "EWMA Long-Short"),
    ("EWMA_LONG_ONLY", "EWMA_LONG_ONLY_30", {"span": 30}, "EWMA Long-Only"),
    ("MACD", "MACD_12_26_9", {"fast_period": 12, "slow_period": 26, "signal_period": 9}, "MACD"),
    ("DONCHIAN", "DONCHIAN_20", {"channel_period": 20}, "Donchian (20)"),
    ("DONCHIAN", "DONCHIAN_50", {"channel_period": 50}, "Donchian (50)"),
    ("BOLLINGER", "BOLLINGER_20_2", {"bb_period": 20, "bb_std": 2.0}, "Bollinger (20, 2.0)"),
    ("BOLLINGER", "BOLLINGER_20_1.5", {"bb_period": 20, "bb_std": 1.5}, "Bollinger (20, 1.5)"),
    ("RSI", "RSI_14_30_70", {"rsi_period": 14, "oversold_threshold": 30, "overbought_threshold": 70}, "RSI"),
    ("TMA", "TMA_5_20_60", {"tma_fast": 5, "tma_medium": 20, "tma_slow": 60}, "TMA (5/20/60)"),
    ("TMA", "TMA_10_30_90", {"tma_fast": 10, "tma_medium": 30, "tma_slow": 90}, "TMA (10/30/90)"),
]


class StrategyRunner:
    """运行所有策略并保存结果"""

    def __init__(self, data_path, output_dir="results", fee_bps=0.0):
        self.data_path = Path(data_path).expanduser()
        if not self.data_path.is_absolute():
            self.data_path = _BASE_DIR / self.data_path
        self.data_path = self.data_path.resolve()

        self.output_dir = Path(output_dir).expanduser()
        if not self.output_dir.is_absolute():
            self.output_dir = _BASE_DIR / self.output_dir
        self.output_dir = self.output_dir.resolve()

        fee = float(fee_bps)
        if not np.isfinite(fee) or fee < 0:
            raise ValueError(f"fee_bps 必须是非负数，收到 {fee_bps!r}")
        self.fee_bps = fee

        self.results = []
        self.strategy_data = {}
        self.failures = []

        # 创建输出目录
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.output_dir / "plots", exist_ok=True)

    def load_data(self):
        """加载并校验回测数据（起始固定 2020-01-01，截止取最新交易日）。"""
        if not self.data_path.is_file():
            raise FileNotFoundError(f"找不到行情文件: {self.data_path}")

        data_loader = DataHandler.from_parquet(
            self.data_path, start_date=datetime(2020, 1, 1)
        )
        dates = data_loader.dates
        print(f"加载数据: {pd.Timestamp(dates[0]).date()} 至 {pd.Timestamp(dates[-1]).date()}")
        return data_loader

    def run_strategy(self, data_loader, strategy_type, strategy_name, display_name=None, **params):
        """运行单个策略；异常由批量入口统一汇总。"""
        print(f"\n运行策略: {strategy_name}")
        print(f"参数: {params}")

        strategy = TradingStrategyCore(
            data_loader, strategy_type=strategy_type, **params
        )
        strategy.generate_signals()

        backtester = BacktestEngine(strategy, fee_bps=self.fee_bps)
        backtester.run_backtest()
        trade_df = backtester.generate_trading_records()

        cumulative_return = strategy.processed_data["CumulativeReturn"][-1]
        if not np.isfinite(cumulative_return):
            raise ValueError(f"策略 {strategy_name} 的累计收益不是有限值")

        # cumulative_return 是权益乘数；年化使用实际日历跨度。
        first_date = strategy.processed_data["Date"][0]
        last_date = strategy.processed_data["Date"][-1]
        days = (last_date - first_date).astype("timedelta64[D]").astype(int)
        years = days / 365.25
        if years > 0 and cumulative_return > 0:
            annualized_return = cumulative_return ** (1 / years) - 1
        else:
            annualized_return = float("nan")

        cumulative_returns = np.asarray(
            strategy.processed_data["CumulativeReturn"], dtype=float
        )
        if not np.isfinite(cumulative_returns).all():
            raise ValueError(f"策略 {strategy_name} 的累计收益包含 NaN/Inf")
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
            max_drawdown = float("nan")

        # 风险调整指标基于策略日收益（含费用，若 fee_bps>0）。
        # 年化用 252 个交易日；日收益恒为 0（全程无持仓）时 Sharpe/波动率记为 NaN。
        strategy_returns = np.asarray(
            strategy.processed_data["StrategyReturn"], dtype=float
        )
        daily_std = float(np.std(strategy_returns, ddof=1)) if len(strategy_returns) > 1 else 0.0
        if daily_std > 0:
            annualized_volatility = daily_std * np.sqrt(252)
            sharpe_ratio = float(np.mean(strategy_returns)) / daily_std * np.sqrt(252)
        else:
            annualized_volatility = float("nan")
            sharpe_ratio = float("nan")

        # 统计基于配对后的 round trip，而不是 buy/sell 动作数量。
        trades_df = backtester.get_trades()
        if trades_df is not None and len(trades_df) > 0:
            total_trades = len(trades_df)
            winning_trades = (trades_df["return"] > 0).sum()
            win_rate = winning_trades / total_trades
            avg_return = trades_df["return"].mean()
        else:
            total_trades = 0
            win_rate = 0
            avg_return = 0

        result = {
            "strategy_name": strategy_name,
            "display_name": display_name or strategy_name,
            "strategy_type": strategy_type,
            "cumulative_return": cumulative_return,
            "annualized_return": annualized_return,
            "annualized_volatility": annualized_volatility,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": max_drawdown,
            "total_trades": total_trades,
            "win_rate": win_rate,
            "avg_trade_return": avg_return,
            "fee_bps": self.fee_bps,
            "parameters": str(params),
        }

        self.strategy_data[strategy_name] = {
            "processed_data": strategy.processed_data,
            "trade_df": trade_df,
            "result": result,
        }

        print(f"  累计收益率: {cumulative_return - 1:.2%}")
        print(f"  年化收益率: {annualized_return:.2%}")
        print(f"  年化波动率: {annualized_volatility:.2%}")
        print(f"  Sharpe 比率: {sharpe_ratio:.2f}")
        print(f"  最大回撤: {max_drawdown:.2%}")
        print(f"  总交易次数: {total_trades}")
        print(f"  胜率: {win_rate:.2%}")
        print(f"  平均交易收益: {avg_return:.2%}")
        if self.fee_bps > 0:
            print(f"  （以上收益均已扣除单边 {self.fee_bps:g} bps 交易成本）")
        return result

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
        """运行所有策略；任一策略失败都会以异常结束批量流程。"""
        # Runner 可以复用，但每次运行必须从干净状态开始。
        self.results.clear()
        self.strategy_data.clear()
        self.failures.clear()

        print("=" * 60)
        print("开始运行所有策略")
        print("=" * 60)

        data_loader = self.load_data()
        for strategy_type, strategy_name, params, display_name in STRATEGIES:
            try:
                result = self.run_strategy(
                    data_loader,
                    strategy_type,
                    strategy_name,
                    display_name=display_name,
                    **params,
                )
                self.results.append(result)
                self.create_visualization(strategy_name, data_loader)
            except Exception as exc:
                failure = {
                    "strategy_name": strategy_name,
                    "strategy_type": strategy_type,
                    "error": str(exc),
                }
                self.failures.append(failure)
                print(f"错误: {strategy_name}: {exc}")

        if self.failures:
            details = "; ".join(
                f"{item['strategy_name']}: {item['error']}"
                for item in self.failures
            )
            raise RuntimeError(
                f"{len(self.failures)}/{len(STRATEGIES)} 个策略运行失败；"
                f"未生成可发布的完整结果。{details}"
            )

        return self.results

    def save_to_excel(self):
        """保存结果到Excel文件。"""
        if getattr(self, "failures", None):
            raise RuntimeError("存在失败策略，拒绝导出不完整的结果")
        if not self.results:
            print("没有结果可保存")
            return

        # 创建DataFrame
        df = pd.DataFrame(self.results)

        # 列顺序；reindex 兼容旧结果缺新列（如 fee_bps）的情况，缺失填 NaN
        columns_order = [
            'strategy_name', 'display_name', 'strategy_type', 'cumulative_return',
            'annualized_return', 'annualized_volatility', 'sharpe_ratio',
            'max_drawdown', 'total_trades', 'win_rate', 'avg_trade_return',
            'fee_bps', 'parameters'
        ]
        df = df.reindex(columns=columns_order)

        # 格式化数值列（cumulative_return 是乘数，需减 1 转为收益率）
        percent_cols = ['annualized_return', 'annualized_volatility', 'max_drawdown', 'win_rate', 'avg_trade_return']
        for col in percent_cols:
            if col in df.columns:
                df[col] = df[col].apply(lambda x: f"{x:.2%}" if pd.notnull(x) else "")
        for col in ['sharpe_ratio']:
            if col in df.columns:
                df[col] = df[col].apply(lambda x: f"{x:.2f}" if pd.notnull(x) else "")
        if 'cumulative_return' in df.columns:
            df['cumulative_return'] = df['cumulative_return'].apply(lambda x: f"{x - 1:.2%}" if pd.notnull(x) else "")

        # 保存到Excel
        excel_path = self.output_dir / "strategy_results.xlsx"

        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            # 保存汇总结果
            df.to_excel(writer, sheet_name='Summary', index=False)

            # 保存每个策略的详细交易记录
            for strategy_name, data in self.strategy_data.items():
                if data['trade_df'] is not None:
                    trade_df = data['trade_df']
                    if isinstance(trade_df, pd.DataFrame) and len(trade_df) > 0:
                        # 使用副本导出，不能改变 strategy_data 中的原始 datetime。
                        export_trade_df = trade_df.copy()
                        if "Date" in export_trade_df.columns:
                            export_trade_df["Date"] = pd.to_datetime(
                                export_trade_df["Date"], errors="raise"
                            ).dt.strftime("%Y-%m-%d")

                        # 截断长名称以适应Excel工作表名称限制
                        sheet_name = strategy_name[:31]
                        export_trade_df.to_excel(
                            writer, sheet_name=sheet_name, index=False
                        )

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

        # 数据范围从任一策略的实际数据取（所有策略共用同一次 load_data）
        data_range_text = "N/A"
        if self.strategy_data:
            processed = next(iter(self.strategy_data.values())).get("processed_data") or {}
            dates = processed.get("Date")
            if dates is not None and len(dates) > 0:
                first = pd.Timestamp(dates[0]).date()
                last = pd.Timestamp(dates[-1]).date()
                data_range_text = f"{first} ~ {last}"

        def _best_text(key, fmt):
            """有限值中取 key 最大者拼成 "名称 (值)"；无可用结果时 N/A。"""
            best = max(
                (r for r in self.results if np.isfinite(r[key])),
                key=lambda r: r[key],
                default=None,
            )
            return f"{best['strategy_name']} ({fmt(best[key])})" if best else "N/A"

        fee_note = (
            f"（收益已扣除单边 {self.fee_bps:g} bps 交易成本）"
            if self.fee_bps > 0 else ""
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
            <p>数据范围: {data_range_text}{fee_note}</p>

            <h2>策略性能汇总</h2>
            {df.to_html(index=False, classes='dataframe')}

            <div class="summary">
                <h2>报告摘要</h2>
                <p>• 测试策略总数: {len(self.results)}</p>
                <p>• 最佳累计收益率: {_best_text('cumulative_return', lambda v: f'{v - 1:.2%}')}</p>
                <p>• 最佳年化收益率: {_best_text('annualized_return', lambda v: f'{v:.2%}')}</p>
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

    # 运行所有策略（2020-01-01 起至最新交易日）
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
