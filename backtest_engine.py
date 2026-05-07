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
