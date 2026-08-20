import matplotlib.pyplot as plt

# processed_data 中不属于“指标序列”的固定字段
_NON_INDICATOR_KEYS = frozenset({
    'Date', 'Close', 'ExecutionPrice', 'TradingSignal',
    'Position', 'ActionStates', 'Return', 'StrategyReturn', 'CumulativeReturn',
})


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

    def _indicator_keys(self):
        """返回 processed_data 中所有指标序列的键名（主指标 + 附加带/均线等）。"""
        if self.strategy.processed_data is None:
            return []
        return [k for k in self.strategy.processed_data if k not in _NON_INDICATOR_KEYS]

    def _uses_secondary_indicator_axis(self):
        """RSI/MACD 的数值尺度与价格不同，应使用副坐标轴。"""
        return getattr(self.strategy, 'strategy_type', '') in {'RSI', 'MACD'}

    def plot_price_indicator(self, ax=None, title=None):
        """绘制价格、全部指标与买卖点。

        Args:
            ax: 可选，画到已有 Axes；为 None 时新建独立 figure。
            title: 可选标题前缀（策略名）。
        Returns:
            使用的 Axes；无数据时返回 None。
        """
        if self.strategy.processed_data is None:
            return None
        dates = self.data_handler.dates
        close_prices = self.strategy.processed_data['Close']
        action_states = self.strategy.processed_data['ActionStates']

        own_fig = ax is None
        if own_fig:
            plt.figure(figsize=(14, 7))
            ax = plt.gca()

        ax.plot(dates, close_prices, label='Price', color='black', linewidth=1)
        indicator_ax = ax.twinx() if self._uses_secondary_indicator_axis() else ax
        for key in self._indicator_keys():
            indicator_ax.plot(
                dates,
                self.strategy.processed_data[key],
                label=key,
                linewidth=2,
            )

        if indicator_ax is not ax:
            strategy_type = getattr(self.strategy, 'strategy_type', '')
            if strategy_type == 'RSI':
                indicator_ax.axhline(30, color='gray', linestyle=':', alpha=0.7)
                indicator_ax.axhline(70, color='gray', linestyle=':', alpha=0.7)
                indicator_ax.set_ylim(0, 100)
                indicator_ax.set_ylabel('RSI')
            else:
                indicator_ax.axhline(0, color='gray', linestyle=':', alpha=0.7)
                indicator_ax.set_ylabel('MACD')

        buy_mask = action_states == 'buy'
        sell_mask = action_states == 'sell'
        ax.scatter(dates[buy_mask], close_prices[buy_mask],
                   marker='^', color='green', s=100, label='Buy', zorder=5)
        ax.scatter(dates[sell_mask], close_prices[sell_mask],
                   marker='v', color='red', s=100, label='Sell', zorder=5)

        prefix = f'{title} - ' if title else ''
        ax.set_title(f'{prefix}Price and Indicators')
        if indicator_ax is ax:
            ax.legend()
        else:
            handles, labels = ax.get_legend_handles_labels()
            indicator_handles, indicator_labels = indicator_ax.get_legend_handles_labels()
            ax.legend(
                handles + indicator_handles,
                labels + indicator_labels,
                loc='upper left',
            )
        ax.grid(True, alpha=0.3)
        if own_fig:
            plt.tight_layout()
        return ax

    def plot_returns_signals(self, ax=None):
        """绘制累计收益曲线。

        Args:
            ax: 可选，画到已有 Axes；为 None 时新建独立 figure。
        Returns:
            使用的 Axes；无数据时返回 None。
        """
        if self.strategy.processed_data is None:
            return None
        dates = self.data_handler.dates
        action_states = self.strategy.processed_data['ActionStates']
        cumulative_returns = self.strategy.processed_data['CumulativeReturn']

        # 确保数据长度一致
        min_len = min(len(dates), len(cumulative_returns), len(action_states))
        dates = dates[:min_len]
        action_states = action_states[:min_len]
        cumulative_returns = cumulative_returns[:min_len]

        own_fig = ax is None
        if own_fig:
            plt.figure(figsize=(14, 7))
            ax = plt.gca()

        ax.plot(dates, cumulative_returns, label='Cumulative Return', color='blue', linewidth=2)
        buy_mask = action_states == 'buy'
        sell_mask = action_states == 'sell'
        ax.scatter(dates[buy_mask], cumulative_returns[buy_mask],
                   marker='o', color='red', s=30, label='Buy')
        ax.scatter(dates[sell_mask], cumulative_returns[sell_mask],
                   marker='o', color='lime', s=30, label='Sell')
        ax.axhline(y=1, color='gray', linestyle='--', alpha=0.5)
        ax.set_title('Cumulative Returns')
        ax.legend()
        ax.grid(True, alpha=0.3)
        if own_fig:
            plt.tight_layout()
        return ax

    def plot_positions(self, ax=None):
        """绘制持仓图（多头绿 / 空头红填充）。

        Args:
            ax: 可选，画到已有 Axes；为 None 时新建独立 figure。
        Returns:
            使用的 Axes；无数据时返回 None。
        """
        if self.strategy.processed_data is None:
            return None
        dates = self.data_handler.dates
        position = self.strategy.processed_data['Position']

        own_fig = ax is None
        if own_fig:
            plt.figure(figsize=(14, 7))
            ax = plt.gca()

        ax.fill_between(dates, 0, position, where=position >= 0,
                        color='green', alpha=0.3, label='Long')
        ax.fill_between(dates, 0, position, where=position < 0,
                        color='red', alpha=0.3, label='Short')
        ax.axhline(y=0, color='black', linewidth=0.5)
        ax.set_title('Position')
        ax.set_yticks([-1, 0, 1])
        ax.legend()
        ax.grid(True, alpha=0.3)
        if own_fig:
            plt.tight_layout()
        return ax

    def plot_results(self, save_path=None, show=True, title=None):
        """一次性绘制三连图：价格+指标、累计收益、持仓。

        Args:
            save_path: 若给定，保存到该路径（不弹窗也能落盘）。
            show: 是否调用 plt.show()；批跑保存时应为 False。
            title: 可选策略名，用于价格子图标题。
        """
        if self.strategy.processed_data is None:
            return

        fig, axes = plt.subplots(3, 1, figsize=(14, 12))
        self.plot_price_indicator(ax=axes[0], title=title)
        self.plot_returns_signals(ax=axes[1])
        self.plot_positions(ax=axes[2])
        plt.tight_layout()

        if save_path:
            fig.savefig(save_path, dpi=150, bbox_inches='tight')
        if show:
            plt.show()
        else:
            plt.close(fig)
