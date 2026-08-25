import numpy as np
import pandas as pd


class BacktestEngine:
    """Backtesting engine for evaluating trading strategies.

    Performs historical simulation of trading strategies and calculates performance
    metrics including returns, drawdowns, and trade statistics.
    """

    _TRADE_RECORD_COLUMNS = [
        "entry_date", "exit_date", "type", "return",
    ]

    def __init__(self, strategy_core):
        self.strategy = strategy_core

    def _validated_arrays(self):
        processed = self.strategy.processed_data
        if processed is None:
            raise ValueError("策略尚未生成 processed_data")

        required = {"ExecutionPrice", "Position"}
        missing = required - set(processed)
        if missing:
            raise ValueError(f"processed_data 缺少字段: {sorted(missing)}")

        execution_price = np.asarray(processed["ExecutionPrice"], dtype=float)
        position = np.asarray(processed["Position"], dtype=float)
        if execution_price.ndim != 1 or position.ndim != 1:
            raise ValueError("ExecutionPrice 和 Position 必须是一维数组")
        if len(execution_price) == 0:
            raise ValueError("回测数据为空")
        if len(execution_price) != len(position):
            raise ValueError("ExecutionPrice 和 Position 长度不一致")
        if not np.isfinite(execution_price).all():
            raise ValueError("ExecutionPrice 包含 NaN 或无穷值")
        if (execution_price <= 0).any():
            raise ValueError("ExecutionPrice 必须全部大于 0")
        if not np.isfinite(position).all():
            raise ValueError("Position 包含 NaN 或无穷值")
        return execution_price, position

    def run_backtest(self):
        """执行回测。

        Position[i] 表示从 ExecutionPrice[i] 到 ExecutionPrice[i+1]
        这一段的持仓。当前策略约定为 T 日收盘出信号、T+1 日开盘成交，
        因此 ExecutionPrice 使用开盘价，收益按开盘到开盘计算。
        """
        if self.strategy.processed_data is None:
            return None

        execution_price, position = self._validated_arrays()
        returns = np.zeros_like(execution_price, dtype=float)
        returns[:-1] = execution_price[1:] / execution_price[:-1] - 1
        strategy_returns = position * returns
        cumulative_returns = np.cumprod(1 + strategy_returns)

        self.strategy.processed_data.update({
            "Return": returns,
            "StrategyReturn": strategy_returns,
            "CumulativeReturn": cumulative_returns,
        })
        return self.strategy.processed_data

    def generate_trading_records(self, verbose=False):
        """生成逐日交易记录。

        Args:
            verbose: 为 True 时打印完整日频表；批跑默认 False。
        """
        if self.strategy.processed_data is None:
            print("错误: 没有有效的数据，无法生成交易记录。")
            return None

        records = {
            "Date": self.strategy.processed_data["Date"],
            "Close": self.strategy.processed_data["Close"],
            "ExecutionPrice": self.strategy.processed_data["ExecutionPrice"],
            "TradingSignal": self.strategy.processed_data["TradingSignal"],
            "Action": self.strategy.processed_data["ActionStates"],
            "Position": self.strategy.processed_data["Position"],
        }
        df = pd.DataFrame(records)
        if verbose:
            with pd.option_context("display.max_rows", len(df)):
                print(df)
        return df

    def get_trades(self):
        """根据 ActionStates 产出逐笔配对交易记录。

        每笔交易包含开仓日期、平仓日期、方向（long/short）和收益率。
        回测结束时仍持仓的，用最后一天的执行价强制平仓。
        """
        if self.strategy.processed_data is None:
            return None

        execution_price, positions = self._validated_arrays()
        processed = self.strategy.processed_data
        dates = np.asarray(processed["Date"])
        actions = np.asarray(processed["ActionStates"])
        if len(dates) != len(execution_price) or len(actions) != len(execution_price):
            raise ValueError("Date/ActionStates 与价格数据长度不一致")

        trades = []
        entry_price = None
        entry_date = None
        entry_type = None

        for i, action in enumerate(actions):
            price = execution_price[i]
            date = dates[i]
            position = positions[i]

            if action == "buy":
                if entry_type == "short" and entry_price is not None:
                    trades.append({
                        "entry_date": entry_date,
                        "exit_date": date,
                        "type": "short",
                        "return": (entry_price - price) / entry_price,
                    })
                    entry_price = None
                    entry_date = None
                    entry_type = None

                if position == 1:
                    entry_price = price
                    entry_date = date
                    entry_type = "long"

            elif action == "sell":
                if entry_type == "long" and entry_price is not None:
                    trades.append({
                        "entry_date": entry_date,
                        "exit_date": date,
                        "type": "long",
                        "return": (price - entry_price) / entry_price,
                    })
                    entry_price = None
                    entry_date = None
                    entry_type = None

                if position == -1:
                    entry_price = price
                    entry_date = date
                    entry_type = "short"

        if entry_price is not None:
            last_price = execution_price[-1]
            last_date = dates[-1]
            if entry_type == "long":
                ret = (last_price - entry_price) / entry_price
            else:
                ret = (entry_price - last_price) / entry_price
            trades.append({
                "entry_date": entry_date,
                "exit_date": last_date,
                "type": entry_type,
                "return": ret,
            })

        return pd.DataFrame(trades, columns=self._TRADE_RECORD_COLUMNS)
