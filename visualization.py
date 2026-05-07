import matplotlib.pyplot as plt

class StrategyVisualizer:
    """Visualization module for trading strategy results.

    Generates plots showing price series, technical indicators, trading signals,
    and performance metrics. Uses matplotlib for rendering.

    Attributes:
        strategy: Reference to strategy core instance
        dates: Array of dates for x-axis
        prices: Array of price data for plotting
        signals: Array of trading signals
    """
    def __init__(self, strategy_core, data_handler):
        self.strategy = strategy_core
        self.data_handler = data_handler

    def plot_price_indicator(self):
        """绘制价格和指标趋势图"""
        if self.strategy.processed_data is None:
            return
        dates = self.data_handler.dates
        close_prices = self.strategy.processed_data['Close']
        ewma = self.strategy.processed_data[self.strategy.indicator_name]
        plt.figure(figsize=(14, 7))
        plt.plot(dates, close_prices, label='Price')
        plt.plot(dates, ewma, label=self.strategy.indicator_name)
        plt.title(f'Price and {self.strategy.indicator_name} Trend')
        plt.legend()
        plt.tight_layout()
        plt.show()

    def plot_returns_signals(self):
        """绘制收益和交易信号图"""
        if self.strategy.processed_data is None:
            return
        dates = self.data_handler.dates
        action_states = self.strategy.processed_data['ActionStates']
        cumulative_returns = self.strategy.processed_data['CumulativeReturn']
        
        # 确保数据长度一致
        min_len = min(len(dates), len(cumulative_returns), len(action_states))
        dates = dates[:min_len]
        cumulative_returns = cumulative_returns[:min_len]
        action_states = action_states[:min_len]
        
        plt.figure(figsize=(14, 7))
        plt.plot(dates, cumulative_returns, label='Strategy Returns', color='green')
        buy_mask = action_states == 'buy'
        sell_mask = action_states == 'sell'
        plt.scatter(dates[buy_mask], cumulative_returns[buy_mask],
                   marker='o', color='red', s=30, label='Buy')
        plt.scatter(dates[sell_mask], cumulative_returns[sell_mask],
                   marker='o', color='lime', s=30, label='Sell')
        plt.title('Cumulative Returns with Trading Signals')
        plt.legend()
        plt.tight_layout()
        plt.show()

    def plot_positions(self):
        """绘制持仓图"""
        if self.strategy.processed_data is None:
            return
        dates = self.data_handler.dates
        position = self.strategy.processed_data['Position']
        plt.figure(figsize=(14, 7))
        plt.scatter(dates, position, label='Position', color='blue', s=1)
        plt.axhline(0, color='gray', linestyle='--')
        plt.title('Position Holding')
        plt.legend()
        plt.grid(axis='y')
        plt.yticks([-1, 0, 1])
        plt.tight_layout()
        plt.show()

    def plot_results(self):
        """一次性绘制所有图表"""
        self.plot_price_indicator()
        self.plot_returns_signals()
        self.plot_positions()
