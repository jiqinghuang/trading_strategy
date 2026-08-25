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
    _SUPPORTED_STRATEGIES = frozenset({
        "EWMA", "EWMA_LONG_ONLY", "MACD", "DONCHIAN",
        "BOLLINGER", "RSI", "TMA",
    })

    @staticmethod
    def _as_float_array(values, name):
        if values is None:
            raise ValueError(f"{name} 数据尚未预处理")
        try:
            arr = np.asarray(values, dtype=float)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} 无法转换为一维浮点数组") from exc
        if arr.ndim != 1:
            raise ValueError(f"{name} 必须是一维数组，收到 ndim={arr.ndim}")
        if arr.size == 0:
            raise ValueError("行情数据为空，无法生成策略信号")
        if not np.isfinite(arr).all():
            raise ValueError(f"{name} 包含 NaN 或无穷值")
        return arr

    @staticmethod
    def _positive_int(value, name):
        if isinstance(value, bool):
            raise ValueError(f"{name} 必须是正整数，收到 {value!r}")
        try:
            integer = int(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{name} 必须是正整数，收到 {value!r}") from exc
        if integer <= 0 or integer != value:
            raise ValueError(f"{name} 必须是正整数，收到 {value!r}")
        return integer

    @staticmethod
    def _positive_float(value, name):
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{name} 必须是正数，收到 {value!r}") from exc
        if not np.isfinite(number) or number <= 0:
            raise ValueError(f"{name} 必须是正数，收到 {value!r}")
        return number

    def __init__(self, data_handler, strategy_type="EWMA", **kwargs):
        if strategy_type not in self._SUPPORTED_STRATEGIES:
            raise ValueError(f"不支持的策略类型: {strategy_type}")

        self.dates = np.asarray(getattr(data_handler, "dates", None))
        if self.dates.ndim != 1 or self.dates.size == 0:
            raise ValueError("日期数据为空或不是一维数组")

        self.open_prices = self._as_float_array(
            getattr(data_handler, "open", None), "open"
        )
        self.close_prices = self._as_float_array(
            getattr(data_handler, "close", None), "close"
        )
        self.high_prices = self._as_float_array(
            getattr(data_handler, "high", None), "high"
        )
        self.low_prices = self._as_float_array(
            getattr(data_handler, "low", None), "low"
        )

        lengths = {
            len(self.dates),
            len(self.open_prices),
            len(self.close_prices),
            len(self.high_prices),
            len(self.low_prices),
        }
        if len(lengths) != 1:
            raise ValueError("日期与 OHLC 数据长度不一致")

        for name, prices in (
            ("open", self.open_prices),
            ("high", self.high_prices),
            ("low", self.low_prices),
            ("close", self.close_prices),
        ):
            if (prices <= 0).any():
                raise ValueError(f"{name} 价格必须全部大于 0")

        self.strategy_type = strategy_type
        self.strategy_params = dict(kwargs)
        self.processed_data = None
        self.indicator_name = strategy_type

        if strategy_type in ["EWMA", "EWMA_LONG_ONLY"]:
            self.span = self._positive_int(kwargs.get("span", 30), "span")
            self.indicator_name = f"{strategy_type}_{self.span}"
        elif strategy_type == "MACD":
            self.fast_period = self._positive_int(
                kwargs.get("fast_period", 12), "fast_period"
            )
            self.slow_period = self._positive_int(
                kwargs.get("slow_period", 26), "slow_period"
            )
            self.signal_period = self._positive_int(
                kwargs.get("signal_period", 9), "signal_period"
            )
            if self.fast_period >= self.slow_period:
                raise ValueError("fast_period 必须小于 slow_period")
            self.indicator_name = (
                f"MACD_{self.fast_period}_{self.slow_period}_{self.signal_period}"
            )
        elif strategy_type == "DONCHIAN":
            self.channel_period = self._positive_int(
                kwargs.get("channel_period", 20), "channel_period"
            )
            self.indicator_name = f"DONCHIAN_{self.channel_period}"
        elif strategy_type == "BOLLINGER":
            self.bb_period = self._positive_int(
                kwargs.get("bb_period", 20), "bb_period"
            )
            self.bb_std = self._positive_float(
                kwargs.get("bb_std", 2.0), "bb_std"
            )
            self.indicator_name = f"BOLLINGER_{self.bb_period}_{self.bb_std}"
        elif strategy_type == "RSI":
            self.rsi_period = self._positive_int(
                kwargs.get("rsi_period", 14), "rsi_period"
            )
            self.oversold_threshold = float(
                kwargs.get("oversold_threshold", 30)
            )
            self.overbought_threshold = float(
                kwargs.get("overbought_threshold", 70)
            )
            if not (
                np.isfinite(self.oversold_threshold)
                and np.isfinite(self.overbought_threshold)
                and 0 <= self.oversold_threshold
                < self.overbought_threshold <= 100
            ):
                raise ValueError(
                    "RSI 阈值必须满足 0 <= oversold < overbought <= 100"
                )
            self.indicator_name = (
                f"RSI_{self.rsi_period}_{self.oversold_threshold:g}_"
                f"{self.overbought_threshold:g}"
            )
        elif strategy_type == "TMA":
            self.tma_fast = self._positive_int(
                kwargs.get("tma_fast", 5), "tma_fast"
            )
            self.tma_medium = self._positive_int(
                kwargs.get("tma_medium", 20), "tma_medium"
            )
            self.tma_slow = self._positive_int(
                kwargs.get("tma_slow", 60), "tma_slow"
            )
            if not self.tma_fast < self.tma_medium < self.tma_slow:
                raise ValueError("TMA 周期必须满足 fast < medium < slow")
            self.indicator_name = (
                f"TMA_{self.tma_fast}_{self.tma_medium}_{self.tma_slow}"
            )

    @staticmethod
    def _prev(arr, fill=np.nan):
        arr = np.asarray(arr)
        prev = np.roll(arr, 1)
        try:
            prev[0] = fill
        except (TypeError, ValueError):
            prev = prev.astype(float)
            prev[0] = fill
        return prev

    def _generate_position_from_signals(self, trading_signal, allow_short=True):
        """根据交易信号生成持仓和行动状态

        信号语义：+1 表示进入多头，-1 表示进入空头（仅做多模式下平多）。
        若新信号与当前仓位方向相同（如强趋势中连续上破），仓位不发生变化，
        此时不写入 buy/sell 标签——避免统计出无实际仓位变动的"幻影交易"。
        """
        n = len(trading_signal)
        position = np.zeros(n)
        action_states = np.full(n, 'hold')

        for i, signal in enumerate(trading_signal[:-1]):
            if signal == 1:  # 买入信号 -> 目标多头
                target = 1
                action = 'buy'
            elif signal == -1:  # 卖出信号 -> 目标空头(多空)或平仓(仅做多)
                target = -1 if allow_short else 0
                action = 'sell'
            else:
                position[i+1] = position[i]  # 保持原有持仓
                continue

            # 仅当仓位实际变化时才记录交易动作，否则视为重复信号忽略
            if position[i] != target:
                position[i+1] = target
                action_states[i+1] = action
            else:
                position[i+1] = position[i]

        return position, action_states

    def _create_processed_data(self, indicator_values, trading_signal, position, action_states, **extra):
        # T 日收盘出信号，T+1 日开盘成交，避免使用未来收盘价。
        execution_price = self.open_prices.copy()
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
        trading_signal = np.zeros(len(close_prices), dtype=float)
        trading_signal[(close_prices > ewma) & (prev_close < prev_ewma)] = 1
        trading_signal[(close_prices < ewma) & (prev_close > prev_ewma)] = -1
        position, action_states = self._generate_position_from_signals(trading_signal, allow_short=allow_short)
        return self._create_processed_data(ewma, trading_signal, position, action_states)

    def _generate_ewma_long_only_signals(self):
        return self._generate_ewma_signals(allow_short=False)

    def _calculate_ema(self, prices, period):
        """计算指数移动平均"""
        period = self._positive_int(period, "EMA period")
        prices = np.asarray(prices, dtype=float)
        if prices.ndim != 1 or len(prices) == 0:
            raise ValueError("EMA 输入必须是非空一维数组")
        alpha = 2 / (period + 1)
        ema = np.zeros(len(prices), dtype=float)
        ema[0] = prices[0]
        for i in range(1, len(prices)):
            ema[i] = alpha * prices[i] + (1 - alpha) * ema[i - 1]
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
        trading_signal = np.zeros(len(close_prices), dtype=float)
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
        upper_band = np.zeros(len(close_prices), dtype=float)
        lower_band = np.zeros(len(close_prices), dtype=float)

        for i in range(len(close_prices)):
            start_idx = max(0, i - self.channel_period + 1)
            upper_band[i] = np.max(high_prices[start_idx:i+1])
            lower_band[i] = np.min(low_prices[start_idx:i+1])

        # 生成交易信号（使用前一期通道值做突破判断）
        trading_signal = np.zeros(len(close_prices), dtype=float)
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
        sma = np.zeros(len(close_prices), dtype=float)
        std = np.zeros(len(close_prices), dtype=float)

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
        trading_signal = np.zeros(len(close_prices), dtype=float)
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
        """计算 RSI 指标。"""
        period = self._positive_int(period, "RSI period")
        prices = np.asarray(prices, dtype=float)
        if prices.ndim != 1:
            raise ValueError("RSI 输入必须是一维数组")
        if len(prices) <= period:
            raise ValueError(
                f"RSI 计算需要至少 {period + 1} 个价格点（周期 {period} + 1），"
                f"当前数据仅 {len(prices)} 个，请放宽日期范围或缩短周期"
            )

        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.zeros(len(prices), dtype=float)
        avg_loss = np.zeros(len(prices), dtype=float)
        avg_gain[period] = np.mean(gains[:period])
        avg_loss[period] = np.mean(losses[:period])

        for i in range(period + 1, len(prices)):
            avg_gain[i] = (
                avg_gain[i - 1] * (period - 1) + gains[i - 1]
            ) / period
            avg_loss[i] = (
                avg_loss[i - 1] * (period - 1) + losses[i - 1]
            ) / period

        # avg_loss=0 且存在上涨时 RSI 应为 100；完全横盘时约定为 50。
        rs = np.full(len(prices), np.nan, dtype=float)
        np.divide(avg_gain, avg_loss, out=rs, where=avg_loss != 0)
        lossless = (avg_loss == 0) & (avg_gain > 0)
        flat = (avg_loss == 0) & (avg_gain == 0)
        rs[lossless] = np.inf
        rs[flat] = 1.0

        rsi = 100 - (100 / (1 + rs))
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
        trading_signal = np.zeros(len(close_prices), dtype=float)
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
        trading_signal = np.zeros(len(close_prices), dtype=float)
        trading_signal[bullish_aligned & ~prev_bullish] = 1
        trading_signal[bearish_aligned & ~prev_bearish] = -1

        # 生成持仓和行动状态
        position, action_states = self._generate_position_from_signals(trading_signal, allow_short=True)
        return self._create_processed_data(ma_fast, trading_signal, position, action_states,
                                           MA_Medium=ma_medium, MA_Slow=ma_slow)
