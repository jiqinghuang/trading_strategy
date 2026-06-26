import numpy as np
import pandas as pd

class BacktestEngine:
    """Backtesting engine for evaluating trading strategies.

    Performs historical simulation of trading strategies and calculates performance
    metrics including returns, drawdowns, and trade statistics.

    Attributes:
        strategy: Reference to strategy core instance
        returns: Array of strategy returns
        cumulative_returns: Array of compounded returns
        trades: Array of trade records
    """
    def __init__(self, strategy_core):
        self.strategy = strategy_core
    
    def run_backtest(self):
        """执行回测"""
        if self.strategy.processed_data is None:
            return None
        #计算回测执行价格
        execution_price = self.strategy.processed_data['ExecutionPrice']  # 使用ExecutionPrice
        position = self.strategy.processed_data['Position']
        returns = execution_price[1:] / execution_price[:-1] - 1
        returns = np.append(returns, 0)
        #计算收益与累计收益
        strategy_returns = position * returns
        cumulative_returns = np.cumprod(1 + strategy_returns)
        # 返回执行价格与收益等数据
        self.strategy.processed_data.update({
            'Return': returns,
            'StrategyReturn': strategy_returns,
            'CumulativeReturn': cumulative_returns
        })
        return self.strategy.processed_data

    def generate_trading_records(self):
        """生成交易记录，获取所有行记录"""
        if self.strategy.processed_data is None:
            print("错误: 没有有效的数据，无法生成交易记录。")
            return None

        # 构建交易记录DataFrame（获取所有行）
        records = {
            'Date': self.strategy.processed_data['Date'],
            'Close': self.strategy.processed_data['Close'],
            'ExecutionPrice': self.strategy.processed_data['ExecutionPrice'],
            'TradingSignal': self.strategy.processed_data['TradingSignal'],
            'Action': self.strategy.processed_data['ActionStates'],
            'Position': self.strategy.processed_data['Position']
        }

        df = pd.DataFrame(records)
        with pd.option_context('display.max_rows', len(df)):
            print(df)
        return df

    def get_trades(self):
        """根据 ActionStates 产出逐笔配对交易记录。

        每笔交易包含开仓日期、平仓日期、方向（long/short）和收益率。
        回测结束时仍持仓的，用最后一天的执行价强制平仓。
        """
        if self.strategy.processed_data is None:
            return None

        dates = self.strategy.processed_data['Date']
        prices = self.strategy.processed_data['ExecutionPrice']
        actions = self.strategy.processed_data['ActionStates']
        positions = self.strategy.processed_data['Position']

        trades = []
        entry_price = None
        entry_date = None
        entry_type = None

        for i in range(len(actions)):
            action = actions[i]
            price = prices[i]
            date = dates[i]
            position = positions[i]

            if action == 'buy':
                # 若当前持有空单，先平空（反手）
                if entry_type == 'short' and entry_price is not None:
                    trades.append({
                        'entry_date': entry_date,
                        'exit_date': date,
                        'type': 'short',
                        'return': (entry_price - price) / entry_price
                    })
                    entry_price = None

                # 开多（positions[i] == 1 表示真实多头，而非仅做多的平仓）
                if position == 1:
                    entry_price = price
                    entry_date = date
                    entry_type = 'long'

            elif action == 'sell':
                # 若当前持有多单，先平多（反手）
                if entry_type == 'long' and entry_price is not None:
                    trades.append({
                        'entry_date': entry_date,
                        'exit_date': date,
                        'type': 'long',
                        'return': (price - entry_price) / entry_price
                    })
                    entry_price = None

                # 开空（仅允许做空时 positions[i] 才会是 -1）
                if position == -1:
                    entry_price = price
                    entry_date = date
                    entry_type = 'short'

        # 处理未平仓：回测结束时仍持仓，用最后一天执行价强制平仓
        if entry_price is not None:
            last_price = prices[-1]
            last_date = dates[-1]
            if entry_type == 'long':
                ret = (last_price - entry_price) / entry_price
            else:
                ret = (entry_price - last_price) / entry_price
            trades.append({
                'entry_date': entry_date,
                'exit_date': last_date,
                'type': entry_type,
                'return': ret
            })

        return pd.DataFrame(trades)
