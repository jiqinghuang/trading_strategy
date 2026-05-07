# Code Wiki - 量化交易策略系统

> 项目路径: `c:\Users\Jiqing\Desktop\trading_strategy`
> 文档生成日期: 2026-05-07

---

## 1. 项目概述

本项目是一个面向中国商品期货市场的量化交易策略回测系统，核心聚焦于贵金属（AU/AG T+D）及多个商品期货指数。系统采用模块化流水线架构，涵盖数据获取、预处理、策略信号生成、回测引擎与可视化输出，支持多种经典趋势跟踪与均值回归策略的快速迭代与对比分析。

### 1.1 核心特性
- **多策略支持**: EWMA、MACD、唐奇安通道、布林带、RSI、三均线(TMA)
- **灵活持仓模式**: 支持多空双向与仅做多两种模式
- **Wind 数据接入**: 通过 Excel COM 自动化调用 Wind 金融终端 WSD 公式获取行情
- **高性能数据处理**: 使用 Polars 进行 DataFrame 操作，NumPy 进行数值计算
- **批量回测与报告**: 一键运行多策略对比，自动生成 Excel 汇总与 HTML 报告

---

## 2. 项目结构

```
trading_strategy/
├── data/                          # 行情数据目录 (Parquet 格式)
│   ├── AU_T_D__SGE.parquet
│   ├── AG_T_D__SGE.parquet
│   ├── AFI_WI.parquet
│   └── ... (60+ 品种)
├── results/                       # 回测结果输出
│   ├── plots/                     # 策略图表 (PNG)
│   ├── strategy_results.xlsx      # Excel 汇总报告
│   └── strategy_report.html       # HTML 可视化报告
├── main.py                        # 主入口: 单策略流水线演示
├── data_handler.py                # 数据加载与预处理模块
├── strategy_core.py               # 策略核心: 信号生成与指标计算
├── backtest_engine.py             # 回测引擎: 收益计算与交易记录
├── visualization.py               # 可视化模块: Matplotlib 图表
├── excel_to_parquet.py            # Wind 数据获取: Excel COM 管道
├── test_strategies.py             # 策略测试: 多策略快速对比
├── run_all_strategies.py          # 批量运行: 全策略回测与报告生成
├── 指数代码编号.txt               # 品种列表配置
└── CLAUDE.md                      # 项目开发指南 (Claude Code 上下文)
```

---

## 3. 架构设计

系统采用清晰的四层流水线架构，各层职责单一、接口明确：

```
┌─────────────────────────────────────────────────────────────┐
│                    数据层 (Data Layer)                       │
│  excel_to_parquet.py  →  data_handler.py                    │
│  Wind/Excel COM 获取      Parquet/CSV 加载与预处理           │
└─────────────────────────────┬───────────────────────────────┘
                              │ NumPy Arrays
┌─────────────────────────────▼───────────────────────────────┐
│                   策略层 (Strategy Layer)                    │
│              strategy_core.py                                │
│  EWMA | MACD | Donchian | Bollinger | RSI | TMA             │
└─────────────────────────────┬───────────────────────────────┘
                              │ Processed Data Dict
┌─────────────────────────────▼───────────────────────────────┐
│                 回测层 (Backtest Layer)                      │
│              backtest_engine.py                              │
│  收益计算 · 累计收益 · 交易记录生成                           │
└─────────────────────────────┬───────────────────────────────┘
                              │ Results / Records
┌─────────────────────────────▼───────────────────────────────┐
│              可视化/报告层 (Visualization Layer)             │
│  visualization.py | run_all_strategies.py                    │
│  Matplotlib 图表 · Excel 汇总 · HTML 报告                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. 模块详解

### 4.1 数据层

#### `excel_to_parquet.py` — Wind 数据获取管道

通过 Windows COM 自动化驱动 Excel，利用 Wind 金融终端插件的 `WSD` 公式批量获取历史行情，并保存为 Parquet 格式。

**关键配置:**

| 配置项 | 说明 |
|--------|------|
| `DATA_DIR` | 数据输出目录 (`./data`) |
| `SYMBOLS` | 68 个品种代码列表 (商品期货指数 + 上海金交所 T+D) |
| `FIELD_NAMES` | 获取字段: `open`, `high`, `low`, `close`, `settle`, `volume`, `oi`, `amt` |
| `DEFAULT_START_DATE` | 默认起始日期 `1990-01-01` |

**核心函数:**

| 函数 | 职责 |
|------|------|
| `get_parquet_path(symbol)` | 将品种代码转换为安全的文件名 |
| `get_last_date(symbol)` | 查询已有 Parquet 文件的最大日期，用于增量更新 |
| `build_workbook(excel, symbol, start, end)` | 创建 Excel Workbook，写入 WSD 公式 |
| `read_data_range(ws)` | 从 Excel 读取 A7:I{last_row} 的溢出数据，过滤非日期行 |
| `merge_and_save(symbol, new_df, existing)` | 合并新旧数据，按日期去重后保存 |
| `main()` | CLI 入口，支持 `--end`, `--full`, `-s/--symbol` 参数 |

**CLI 用法:**
```bash
python excel_to_parquet.py --end 20260430           # 增量更新全部品种
python excel_to_parquet.py --end 20260430 --full    # 全量刷新
python excel_to_parquet.py --end 20260430 -s AU(T+D).SGE  # 单品种更新
```

**交互按键:**
- `Enter` = 读取/保存
- `ESC` = 跳过
- `Q` = 退出整个流水线

---

#### `data_handler.py` — 数据加载与预处理

使用 **Polars** 高效读取 CSV/Parquet，提供缺失值处理与日期筛选，最终转换为 NumPy 数组供策略层使用。

**类: `DataHandler`**

| 属性 | 类型 | 说明 |
|------|------|------|
| `raw_data` | `pl.DataFrame` | 原始行情数据 |
| `dates` | `np.ndarray` | 交易日期数组 |
| `open` / `high` / `low` / `close` | `np.ndarray` | OHLC 价格 |
| `settle` | `np.ndarray` | 结算价 |
| `volume` | `np.ndarray` | 成交量 |

| 方法 | 说明 |
|------|------|
| `__init__(data_path, file_type='csv')` | 加载 CSV 或 Parquet |
| `preprocess_data(start_date, end_date)` | 缺失值处理(前向/后向填充)、日期筛选、转 NumPy |

**缺失值处理策略:**
1. `NaN` → `None`
2. 前向填充 (`forward`)
3. 后向填充 (`backward`)
4. 剩余填充为 `0`

---

### 4.2 策略层

#### `strategy_core.py` — 策略信号生成核心

系统的核心模块，实现了 **6 种交易策略**，采用统一的信号生成框架。

**类: `TradingStrategyCore`**

| 属性 | 说明 |
|------|------|
| `dates` | 日期数组 |
| `open_prices` / `close_prices` / `high_prices` / `low_prices` | OHLC 价格 |
| `strategy_type` | 策略类型标识 |
| `strategy_params` | 策略参数字典 |
| `processed_data` | 处理后的完整数据字典 |
| `indicator_name` | 指标名称 (用于图表标注) |

**统一信号约定:**
- `TradingSignal`: `1` = 买入, `-1` = 卖出, `0` = 持有
- `Position`: `1` = 多头, `-1` = 空头, `0` = 空仓
- `ActionStates`: `'buy'` / `'sell'` / `'hold'`
- **执行价格**: `(open + close) / 2`
- **交易延迟**: 信号产生于 T 日，仓位生效于 T+1 日

**核心方法:**

| 方法 | 职责 |
|------|------|
| `generate_signals()` | 策略入口，根据 `strategy_type` 动态分发到对应方法 |
| `_generate_position_from_signals(trading_signal, allow_short)` | 将离散信号转换为连续持仓序列 |
| `_create_processed_data(...)` | 组装标准格式的 `processed_data` 字典 |
| `_calculate_ema(prices, period)` | 指数移动平均计算 |
| `_calculate_rsi(prices, period)` | RSI 指标计算 |
| `_prev(arr, fill)` | 数组移位，获取前一期值 |

**支持的策略:**

| 策略 | 类型 | 核心逻辑 | 参数 |
|------|------|---------|------|
| `EWMA` | 趋势跟踪 | 价格上穿/下穿 EWMA 均线产生买卖信号 | `span` (默认 30) |
| `EWMA_LONG_ONLY` | 趋势跟踪 | EWMA 逻辑，但仅做多，卖出仅平仓 | `span` (默认 30) |
| `MACD` | 趋势跟踪 | MACD 线上穿/下穿信号线产生信号 | `fast=12`, `slow=26`, `signal=9` |
| `DONCHIAN` | 突破策略 | 价格上破 N 日高点买入，下破 N 日低点卖出 | `channel_period` (默认 20) |
| `BOLLINGER` | 波动率策略 | 价格从下轨向上突破买入，从上轨向下跌破卖出 | `bb_period=20`, `bb_std=2.0` |
| `RSI` | 均值回归 | RSI 从超卖区回升买入，从超买区回落卖出 | `rsi_period=14`, `oversold=30`, `overbought=70` |
| `TMA` | 趋势跟踪 | 快/中/慢三均线多头排列买入，空头排列卖出 | `tma_fast=5`, `tma_medium=20`, `tma_slow=60` |

---

### 4.3 回测层

#### `backtest_engine.py` — 回测引擎

基于策略生成的持仓序列，计算每日收益、累计收益，并输出交易记录。

**类: `BacktestEngine`**

| 属性 | 说明 |
|------|------|
| `strategy` | 关联的 `TradingStrategyCore` 实例 |

| 方法 | 说明 |
|------|------|
| `run_backtest()` | 执行回测，计算日收益、策略收益、累计收益 |
| `generate_trading_records()` | 生成交易记录 DataFrame 并打印 |

**收益计算逻辑:**
```
returns = execution_price[1:] / execution_price[:-1] - 1
strategy_returns = position * returns
cumulative_returns = cumprod(1 + strategy_returns)
```

---

### 4.4 可视化层

#### `visualization.py` — 策略可视化

基于 Matplotlib 绘制三类图表，支持交互式显示。

**类: `StrategyVisualizer`**

| 方法 | 说明 |
|------|------|
| `plot_price_indicator()` | 价格 + 技术指标趋势图 |
| `plot_returns_signals()` | 累计收益曲线 + 买卖信号标注 |
| `plot_positions()` | 持仓状态散点图 |
| `plot_results()` | 依次调用以上三个方法 |

---

#### `run_all_strategies.py` — 批量策略运行器

自动化运行多组策略参数，计算高级绩效指标，输出图表、Excel 与 HTML 报告。

**类: `StrategyRunner`**

| 方法 | 说明 |
|------|------|
| `load_data(years=5)` | 加载最近 N 年数据 |
| `run_strategy(...)` | 运行单个策略，计算累计收益、年化收益、最大回撤、胜率等 |
| `create_visualization(...)` | 生成三合一图表并保存为 PNG |
| `run_all_strategies(years=5)` | 批量运行预定义策略列表 |
| `save_to_excel()` | 保存汇总结果与详细交易记录到 Excel |
| `create_html_report(df)` | 生成 HTML 格式报告 |

**输出绩效指标:**
- 累计收益率 (`cumulative_return`)
- 年化收益率 (`annualized_return`)
- 最大回撤 (`max_drawdown`)
- 总交易次数 (`total_trades`)
- 胜率 (`win_rate`)
- 平均交易收益 (`avg_trade_return`)

---

#### `test_strategies.py` — 策略快速测试

用于开发调试阶段快速验证所有策略的基本表现。

| 函数 | 说明 |
|------|------|
| `test_all_strategies()` | 遍历运行所有策略，打印累计收益与交易次数，按收益排名 |
| `visualize_strategy(strategy_type, **kwargs)` | 可视化单个策略结果 |

---

## 5. 依赖关系

### 5.1 模块依赖图

```
main.py
├── data_handler.py
├── strategy_core.py
│   └── numpy
├── backtest_engine.py
│   ├── numpy
│   └── pandas
└── visualization.py
    └── matplotlib

excel_to_parquet.py
├── polars
└── win32com.client (pywin32)

test_strategies.py
├── data_handler.py
├── strategy_core.py
├── backtest_engine.py
└── visualization.py

run_all_strategies.py
├── data_handler.py
├── strategy_core.py
├── backtest_engine.py
├── visualization.py
├── pandas
├── numpy
└── matplotlib
```

### 5.2 外部依赖

| 包名 | 用途 | 必需性 |
|------|------|--------|
| `numpy` | 数值计算、数组操作 | 必需 |
| `polars` | 高性能 DataFrame 读写 | 必需 |
| `pandas` | 交易记录 DataFrame、Excel 输出 | 必需 |
| `matplotlib` | 图表绘制 | 必需 |
| `pywin32` | Excel COM 自动化 (Wind 数据获取) | 仅数据获取 |
| `tqdm` | 进度条 (L1 filter 等扩展) | 可选 |

### 5.3 环境依赖

- **操作系统**: Windows (因 `excel_to_parquet.py` 依赖 Excel COM)
- **Excel**: 安装 Wind 金融终端插件
- **Wind 终端**: 需登录以驱动 WSD 公式计算

---

## 6. 运行方式

### 6.1 单策略演示

```bash
python main.py
```

默认流程:
1. 加载 `data/AU_T_D__SGE.parquet` (2020-01-01 至 2026-04-30)
2. 使用 `EWMA_LONG_ONLY` 策略 (span=30)
3. 生成交易信号
4. 执行回测
5. 打印交易记录
6. 显示价格/收益/持仓三张图表

### 6.2 策略快速测试

```bash
python test_strategies.py
```

运行所有 7 种策略，输出累计收益率与交易次数排名。

### 6.3 批量回测与报告

```bash
python run_all_strategies.py
```

运行 10 组策略参数，自动生成:
- `results/plots/*.png` — 各策略图表
- `results/strategy_results.xlsx` — Excel 汇总与交易明细
- `results/strategy_report.html` — HTML 可视化报告

### 6.4 数据更新

```bash
# 增量更新全部品种
python excel_to_parquet.py --end 20260430

# 全量刷新
python excel_to_parquet.py --end 20260430 --full

# 单品种更新
python excel_to_parquet.py --end 20260430 -s AU(T+D).SGE
```

---

## 7. 数据格式

### 7.1 Parquet 文件结构

| 列名 | 类型 | 说明 |
|------|------|------|
| `date` | `str` / `datetime` | 交易日期 (YYYY-MM-DD) |
| `open` | `f64` | 开盘价 |
| `high` | `f64` | 最高价 |
| `low` | `f64` | 最低价 |
| `close` | `f64` | 收盘价 |
| `settle` | `f64` | 结算价 |
| `volume` | `f64` | 成交量 |
| `oi` | `f64` | 持仓量 |
| `amt` | `f64` | 成交额 |

### 7.2 processed_data 字典结构

策略核心生成的标准数据结构:

```python
{
    'Date': np.ndarray,           # 日期
    'Close': np.ndarray,          # 收盘价
    'ExecutionPrice': np.ndarray, # 执行价格 (open+close)/2
    '<IndicatorName>': np.ndarray, # 指标值 (如 EWMA_30)
    'TradingSignal': np.ndarray,  # 交易信号 (1/-1/0)
    'Position': np.ndarray,       # 持仓状态 (1/-1/0)
    'ActionStates': np.ndarray,   # 行动状态 ('buy'/'sell'/'hold')
    'Return': np.ndarray,         # 日收益率 (回测引擎注入)
    'StrategyReturn': np.ndarray, # 策略日收益率
    'CumulativeReturn': np.ndarray, # 累计收益率
    # 额外指标 (策略特定):
    # MACD: MACD_Signal, MACD_Histogram
    # Donchian: Donchian_Lower
    # Bollinger: Bollinger_Upper, Bollinger_Lower, Bollinger_Bandwidth
    # TMA: MA_Medium, MA_Slow
}
```

---

## 8. 扩展指南

### 8.1 添加新策略

遵循以下步骤在 `strategy_core.py` 中扩展:

1. **在 `__init__` 中解析参数:**
```python
elif strategy_type == 'MY_STRATEGY':
    self.my_param = kwargs.get('my_param', 10)
    self.indicator_name = f'MY_STRATEGY_{self.my_param}'
```

2. **实现信号生成方法:**
```python
def _generate_my_strategy_signals(self):
    close_prices = self.close_prices
    # 1. 计算指标
    indicator = self._calculate_some_indicator(close_prices, self.my_param)
    # 2. 生成信号
    trading_signal = np.zeros_like(close_prices)
    prev_indicator = self._prev(indicator)
    # ... 信号逻辑 ...
    # 3. 生成持仓
    position, action_states = self._generate_position_from_signals(
        trading_signal, allow_short=True
    )
    # 4. 返回数据
    return self._create_processed_data(indicator, trading_signal, position, action_states)
```

3. **在测试文件中加入策略配置:**
```python
('MY_STRATEGY', {'my_param': 10}, "我的新策略")
```

### 8.2 添加新数据字段

如需在回测中使用更多字段 (如 `oi`, `amt`):
1. 在 `DataHandler.preprocess_data()` 中导出对应 NumPy 数组
2. 在 `TradingStrategyCore.__init__()` 中接收新字段
3. 在策略方法中使用

---

## 9. 关键设计决策

| 决策 | 说明 |
|------|------|
| **Polars 替代 Pandas** | 数据加载层使用 Polars 以获得更快的 IO 性能；策略计算层使用 NumPy 数组避免 DataFrame 开销 |
| **执行价格 = (open+close)/2** | 模拟日内平均成交价格，比仅用 close 更贴近真实交易成本 |
| **T 日信号 → T+1 日持仓** | 避免未来函数 (look-ahead bias)，确保回测真实性 |
| **Excel 作为计算层** | 利用 Wind Excel 插件的 WSD 公式能力，不依赖 Wind Python API |
| **Parquet 作为存储格式** | 相比 CSV 具有更好的压缩率与读写性能，支持增量更新 |

---

## 10. 注意事项

1. **Windows 依赖**: `excel_to_parquet.py` 只能在 Windows 环境下运行，且需要安装 Excel 与 Wind 插件
2. **中文环境**: 可视化模块已配置 `SimHei` 字体支持中文标签
3. **日期越界处理**: `DataHandler.preprocess_data()` 会自动将超出数据实际范围的日期裁剪为 `None`
4. **品种代码安全转换**: `excel_to_parquet.py` 使用正则替换将品种代码中的特殊字符转为下划线生成文件名
