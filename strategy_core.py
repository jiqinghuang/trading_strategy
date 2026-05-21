import numpy as np

class TradingStrategyCore:
    """Core trading strategy implementation module.

    Contains the main strategy logic including signal generation and technical
    indicators calculation. Implements multiple trend-following strategies.

    Attributes:
        dates: Array of trading dates
        prices: Array of price data (open, close)
        strategy_type: Type of strategy (default: 'EWMA')
        processed_data: Dictionary containing all processed strategy data
    """
    def __init__(self, data_handler, strategy_type='EWMA', **kwargs):
        self.dates = data_handler.dates
        self.open_prices = data_handler.open
        self.close_prices = data_handler.close
        self.high_prices = data_handler.high
        self.low_prices = data_handler.low
        self.strategy_type = strategy_type
        self.strategy_params = kwargs
        self.processed_data = None
        self.indicator_name = strategy_type

        # 策略参数设置
        if strategy_type in ['EWMA', 'EWMA_LONG_ONLY']:
            self.span = kwargs.get('span', 30)
            self.indicator_name = f'{strategy_type}_{self.span}'
        elif strategy_type == 'MACD':
            self.fast_period = kwargs.get('fast_period', 12)
            self.slow_period = kwargs.get('slow_period', 26)
            self.signal_period = kwargs.get('signal_period', 9)
            self.indicator_name = f'MACD_{self.fast_period}_{self.slow_period}_{self.signal_period}'
        elif strategy_type == 'DONCHIAN':
            self.channel_period = kwargs.get('channel_period', 20)
            self.indicator_name = f'DONCHIAN_{self.channel_period}'
        elif strategy_type == 'BOLLINGER':
            self.bb_period = kwargs.get('bb_period', 20)
            self.bb_std = kwargs.get('bb_std', 2.0)
            self.indicator_name = f'BOLLINGER_{self.bb_period}_{self.bb_std}'
        elif strategy_type == 'RSI':
            self.rsi_period = kwargs.get('rsi_period', 14)
            self.oversold_threshold = kwargs.get('oversold_threshold', 30)
            self.overbought_threshold = kwargs.get('overbought_threshold', 70)
            self.indicator_name = f'RSI_{self.rsi_period}_{self.oversold_threshold}_{self.overbought_threshold}'
        elif strategy_type == 'TMA':
            self.tma_fast = kwargs.get('tma_fast', 5)
            self.tma_medium = kwargs.get('tma_medium', 20)
            self.tma_slow = kwargs.get('tma_slow', 60)
            self.indicator_name = f'TMA_{self.tma_fast}_{self.tma_medium}_{self.tma_slow}'

    @staticmethod
    def _prev(arr, fill=np.nan):
        prev = np.roll(arr, 1)
        prev[0] = fill
        return prev

    def _generate_position_from_signals(self, trading_signal, allow_short=True):
        """根据交易信号生成持仓和行动状态"""
        n = len(trading_signal)
        position = np.zeros(n)
        action_states = np.full(n, 'hold')

        for i, signal in enumerate(trading_signal[:-1]):
            if signal == 1:  # 买入信号
                position[i+1] = 1
                action_states[i+1] = 'buy'
            elif signal == -1:  # 卖出信号
                if allow_short:
                    position[i+1] = -1
                else:
                    position[i+1] = 0  # 仅做多时卖出平仓
                action_states[i+1] = 'sell'
            else:
                position[i+1] = position[i]  # 保持原有持仓

        return position, action_states

    def _create_processed_data(self, indicator_values, trading_signal, position, action_states, **extra):
        execution_price = (self.open_prices + self.close_prices) / 2
        self.processed_data = {
            'Date': self.dates,
            'Close': self.close_prices,
            'ExecutionPrice': execution_price,
            self.indicator_name: indicator_values,
            'TradingSignal': trading_signal,
            'Position': position,
            'ActionStates': action_states,
            **extra
        }
        return self.processed_data

    def generate_signals(self):
        """策略信号生成入口"""
        # 构建策略方法名
        method_name = f'_generate_{self.strategy_type.lower()}_signals'
        # 检查方法是否存在
        if not hasattr(self, method_name):
            raise ValueError(f"不支持的策略类型: {self.strategy_type}")
        # 获取并执行策略方法
        strategy_method = getattr(self, method_name)
        return strategy_method()
    
    def _generate_ewma_signals(self, allow_short=True):
        """EWMA策略信号生成"""
        close_prices = self.close_prices
        ewma = self._calculate_ema(close_prices, self.span)
        prev_close = self._prev(close_prices)
        prev_ewma = self._prev(ewma)
        trading_signal = np.zeros_like(close_prices)
        trading_signal[(close_prices > ewma) & (prev_close < prev_ewma)] = 1
        trading_signal[(close_prices < ewma) & (prev_close > prev_ewma)] = -1
        position, action_states = self._generate_position_from_signals(trading_signal, allow_short=allow_short)
        return self._create_processed_data(ewma, trading_signal, position, action_states)

    def _generate_ewma_long_only_signals(self):
        return self._generate_ewma_signals(allow_short=False)

    def _calculate_ema(self, prices, period):
        """计算指数移动平均"""
        alpha = 2 / (period + 1)
        ema = np.zeros_like(prices)
        ema[0] = prices[0]
        for i in range(1, len(prices)):
            ema[i] = alpha * prices[i] + (1 - alpha) * ema[i-1]
        return ema

    def _generate_macd_signals(self):
        """MACD趋势策略信号生成"""
        close_prices = self.close_prices

        # 计算EMA
        ema_fast = self._calculate_ema(close_prices, self.fast_period)
        ema_slow = self._calculate_ema(close_prices, self.slow_period)

        # 计算MACD线和信号线
        macd_line = ema_fast - ema_slow
        signal_line = self._calculate_ema(macd_line, self.signal_period)
        histogram = macd_line - signal_line

        # 生成交易信号
        trading_signal = np.zeros_like(close_prices)
        prev_macd = self._prev(macd_line)
        prev_signal = self._prev(signal_line)

        # MACD上穿信号线为买入，下穿为卖出
        trading_signal[(macd_line > signal_line) & (prev_macd <= prev_signal)] = 1
        trading_signal[(macd_line < signal_line) & (prev_macd >= prev_signal)] = -1

        # 生成持仓和行动状态
        position, action_states = self._generate_position_from_signals(trading_signal, allow_short=True)
        return self._create_processed_data(macd_line, trading_signal, position, action_states,
                                           MACD_Signal=signal_line, MACD_Histogram=histogram)

    def _generate_donchian_signals(self):
        """唐奇安通道突破策略"""
        close_prices = self.close_prices
        high_prices = self.high_prices
        low_prices = self.low_prices

        # 计算唐奇安通道
        upper_band = np.zeros_like(close_prices)
        lower_band = np.zeros_like(close_prices)

        for i in range(len(close_prices)):
            start_idx = max(0, i - self.channel_period + 1)
            upper_band[i] = np.max(high_prices[start_idx:i+1])
            lower_band[i] = np.min(low_prices[start_idx:i+1])

        # 生成交易信号（使用前一期通道值做突破判断）
        trading_signal = np.zeros_like(close_prices)
        prev_close = self._prev(close_prices)
        prev_upper = self._prev(upper_band)
        prev_lower = self._prev(lower_band)

        # 上破上轨买入，下破下轨卖出
        # fix: 用 prev_upper/prev_lower 而非 upper_band/lower_band
        # upper_band[i] >= high[i] >= close[i]，导致条件永远不成立
        trading_signal[(close_prices > prev_upper) & (prev_close <= prev_upper)] = 1
        trading_signal[(close_prices < prev_lower) & (prev_close >= prev_lower)] = -1

        # 生成持仓和行动状态
        position, action_states = self._generate_position_from_signals(trading_signal, allow_short=True)
        return self._create_processed_data(upper_band, trading_signal, position, action_states,
                                           Donchian_Lower=lower_band)

    def _generate_bollinger_signals(self):
        """布林带策略"""
        close_prices = self.close_prices

        # 计算移动平均和标准差
        sma = np.zeros_like(close_prices)
        std = np.zeros_like(close_prices)

        for i in range(len(close_prices)):
            start_idx = max(0, i - self.bb_period + 1)
            window = close_prices[start_idx:i+1]
            sma[i] = np.mean(window)
            std[i] = np.std(window)

        # 计算布林带
        upper_band = sma + self.bb_std * std
        lower_band = sma - self.bb_std * std
        bandwidth = (upper_band - lower_band) / sma  # 带宽百分比

        # 生成交易信号（使用前一期band避免前视偏差）
        trading_signal = np.zeros_like(close_prices)
        prev_close = self._prev(close_prices)
        prev_lower = self._prev(lower_band)
        prev_upper = self._prev(upper_band)

        # 价格从前一期下轨向上突破买入，从前一期上轨向下跌破卖出
        trading_signal[(close_prices > prev_lower) & (prev_close <= prev_lower)] = 1
        trading_signal[(close_prices < prev_upper) & (prev_close >= prev_upper)] = -1

        # 生成持仓和行动状态
        position, action_states = self._generate_position_from_signals(trading_signal, allow_short=True)
        return self._create_processed_data(sma, trading_signal, position, action_states,
                                           Bollinger_Upper=upper_band, Bollinger_Lower=lower_band,
                                           Bollinger_Bandwidth=bandwidth)

    def _calculate_rsi(self, prices, period):
        """计算RSI指标"""
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.zeros_like(prices)
        avg_loss = np.zeros_like(prices)

        # 初始平滑平均值
        avg_gain[period] = np.mean(gains[:period])
        avg_loss[period] = np.mean(losses[:period])

        for i in range(period + 1, len(prices)):
            avg_gain[i] = (avg_gain[i-1] * (period - 1) + gains[i-1]) / period
            avg_loss[i] = (avg_loss[i-1] * (period - 1) + losses[i-1]) / period

        rs = np.divide(avg_gain, avg_loss, out=np.ones_like(avg_gain), where=avg_loss != 0)
        rsi = 100 - (100 / (1 + rs))
        # 前 period 个值设为 NaN
        rsi[:period] = np.nan
        return rsi

    def _generate_rsi_signals(self):
        """RSI均值回归策略
        超卖区域(低于阈值)买入，超买区域(高于阈值)卖出
        """
        close_prices = self.close_prices

        # 计算RSI
        rsi = self._calculate_rsi(close_prices, self.rsi_period)

        # 生成交易信号
        trading_signal = np.zeros_like(close_prices)
        prev_rsi = self._prev(rsi)

        # RSI从超卖区回升买入，从超买区回落卖出
        trading_signal[(rsi > self.oversold_threshold) & (prev_rsi <= self.oversold_threshold)] = 1
        trading_signal[(rsi < self.overbought_threshold) & (prev_rsi >= self.overbought_threshold)] = -1

        # 生成持仓和行动状态
        position, action_states = self._generate_position_from_signals(trading_signal, allow_short=True)

        # 创建处理后的数据
        return self._create_processed_data(rsi, trading_signal, position, action_states)

    def _generate_tma_signals(self):
        """三均线趋势策略(Triple Moving Average)
        快均线 > 中均线 > 慢均线 多头排列时买入
        快均线 < 中均线 < 慢均线 空头排列时卖出
        """
        close_prices = self.close_prices

        # 计算三条均线
        ma_fast = self._calculate_ema(close_prices, self.tma_fast)
        ma_medium = self._calculate_ema(close_prices, self.tma_medium)
        ma_slow = self._calculate_ema(close_prices, self.tma_slow)

        # 当前排列状态
        bullish_aligned = (ma_fast > ma_medium) & (ma_medium > ma_slow)
        bearish_aligned = (ma_fast < ma_medium) & (ma_medium < ma_slow)

        # 前一期排列状态
        prev_bullish = self._prev(bullish_aligned, fill=False)
        prev_bearish = self._prev(bearish_aligned, fill=False)

        # 生成交易信号
        trading_signal = np.zeros_like(close_prices)
        trading_signal[bullish_aligned & ~prev_bullish] = 1
        trading_signal[bearish_aligned & ~prev_bearish] = -1

        # 生成持仓和行动状态
        position, action_states = self._generate_position_from_signals(trading_signal, allow_short=True)
        return self._create_processed_data(ma_fast, trading_signal, position, action_states,
                                           MA_Medium=ma_medium, MA_Slow=ma_slow)
