# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Session Startup (IMPORTANT)

At the start of EVERY session (including ACP/Zed sessions), you MUST:
1. Read `~/.claude/projects/C--Users-Jiqing-Desktop-trading-strategy/memory/MEMORY.md` to load cross-session memory
2. Read any referenced memory files listed in MEMORY.md for full context
3. This ensures continuity across sessions — do NOT skip this step

## Project Overview

This is a quantitative trading strategy system for Chinese commodity futures markets, focusing on precious metals (AU/AG T+D) and various commodity futures indices. The system implements EWMA (Exponentially Weighted Moving Average) crossover strategies with backtesting and visualization capabilities.

## Architecture

The system follows a modular pipeline architecture:

1. **Data Layer** (`excel_to_parquet.py`, `data_handler.py`)
   - `excel_to_parquet.py`: Fetches market data via Excel COM + Wind add-in WSD formula, saves to Parquet
   - `data_handler.py`: Loads and preprocesses data from CSV/Parquet files
   - Data stored in `data/` directory as Parquet files

2. **Strategy Layer** (`strategy_core.py`)
   - `TradingStrategyCore` class implements multiple trend-following strategies
   - Modular design with reusable components for signal generation and position management
   - Currently implements:
     - **EWMA Crossover**: Price crossing exponentially weighted moving average
       - `EWMA`: Long-short version (allows both buying and short selling)
       - `EWMA_LONG_ONLY`: Long-only version (buys only, sells to close positions)
     - **MACD**: Moving Average Convergence Divergence strategy
       - Uses fast/slow EMA difference and signal line crossover
       - Configurable periods: fast (default 12), slow (26), signal (9)
     - **Donchian Channels**: Breakout strategy using price channels
       - Buys when price breaks above previous upper channel, sells when breaks below previous lower channel
       - Uses prev-channel to avoid look-ahead bias
       - Configurable channel period (default 20)
     - **Bollinger Bands**: Volatility-based strategy
       - Uses moving average with standard deviation bands
       - Buys when price breaks above previous lower band, sells when breaks below previous upper band
       - Configurable: period (default 20), standard deviations (default 2.0)
     - **RSI**: Mean-reversion strategy
       - Buys when RSI crosses above oversold threshold, sells when crosses below overbought
       - Configurable: period (default 14), oversold (30), overbought (70)
     - **TMA (Triple Moving Average)**: Trend-following strategy
       - Bullish alignment (fast > medium > slow) → buy, bearish alignment → sell
       - Configurable: fast (default 5), medium (20), slow (60)

3. **Backtesting Layer** (`backtest_engine.py`)
   - `BacktestEngine` performs historical simulation
   - Calculates returns, cumulative returns, and trading records
   - Uses execution price (average of open and close) for realistic simulation

4. **Visualization Layer** (`visualization.py`)
   - `StrategyVisualizer` generates plots for price trends, signals, and performance
   - Three plot types: price/indicator, cumulative returns with signals, position holding

5. **Additional Tools**
   - `run_all_strategies.py`: Batch runner — executes all strategies, computes performance metrics, generates Excel + HTML reports
   - `update_local_website.py`: Syncs results (plots, HTML) to the local website repo (`jiqinghuang.github.io`)
   - `test_strategies.py`: Quick smoke test of all strategies with ranking

## Key Dependencies

- **numpy**: Numerical computations
- **polars**: Fast DataFrame operations (alternative to pandas)
- **matplotlib**: Plotting and visualization
- **pywin32 + Excel**: Windows COM automation to drive Wind add-in formula calculation (required for data fetching)

## Data Structure

Market data files in `data/` directory contain the following columns:
- `date`: Trading date (YYYY-MM-DD format)
- `open`, `high`, `low`, `close`: OHLC prices
- `settle`: Settlement price
- `volume`: Trading volume
- `oi`: Open interest
- `amt`: Trading amount

Supported symbols are listed in `指数代码编号.txt` and include:
- 60+ commodity futures indices (e.g., `AFI.WI`, `AGFI.WI`)
- Shanghai Gold Exchange T+D contracts (`AU(T+D).SGE`, `AG(T+D).SGE`)

## Common Development Tasks

### Running the Main Strategy
```bash
python main.py
```
This executes the complete pipeline: data loading → strategy signals → backtesting → visualization.

### Fetching Data from Wind (via Excel COM)
```bash
python excel_to_parquet.py --end 20260429        # Incremental update all symbols
python excel_to_parquet.py --end 20260429 --full  # Full refresh
python excel_to_parquet.py --end 20260429 -s AU(T+D).SGE  # Single symbol
```
Uses Windows COM automation to drive Excel with Wind add-in WSD formulas. Excel acts as a compute layer only — data is stored in `data/` as Parquet files.

### Running Full Backtest & Report
```bash
python run_all_strategies.py
```
Runs all 10 strategy configurations, generates performance metrics (cumulative return, annualized return, max drawdown, win rate), saves Excel + HTML reports to `results/`.

### Quick Strategy Smoke Test
```bash
python test_strategies.py
```
Runs all strategies and prints cumulative return ranking — quicker, no file output.

### Syncing to Local Website
```bash
python update_local_website.py
```
Runs strategies → copies plots to website repo → updates `projects.html` with latest results.

### Adding New Strategies
1. Add strategy parameter handling in `__init__` method
2. Create strategy method following pattern `_generate_<strategy_name>_signals()`
3. Use helper methods: `_calculate_ema()`, `_prev()`, `_generate_position_from_signals()`, `_create_processed_data()`
4. Populate `self.processed_data` with required fields
5. Update indicator name in `self.indicator_name`

### Strategy Parameters
- **EWMA/EWMA_LONG_ONLY**: `span` (default 30)
- **MACD**: `fast_period` (12), `slow_period` (26), `signal_period` (9)
- **Donchian**: `channel_period` (20)
- **Bollinger**: `bb_period` (20), `bb_std` (2.0)
- **RSI**: `rsi_period` (14), `oversold_threshold` (30), `overbought_threshold` (70)
- **TMA**: `tma_fast` (5), `tma_medium` (20), `tma_slow` (60)
- **Execution price**: Default is `(open + close) / 2`, can be modified in strategy methods

### Code Structure for New Strategies
```python
def _generate_new_strategy_signals(self):
    # 1. Calculate indicators
    indicator = self._calculate_ema(self.close_prices, period)
    
    # 2. Generate trading signals (1=buy, -1=sell, 0=hold)
    trading_signal = np.zeros_like(self.close_prices)
    # ... signal logic ...
    
    # 3. Generate positions and action states
    position, action_states = self._generate_position_from_signals(
        trading_signal, allow_short=True/False
    )
    
    # 4. Create processed data structure
    return self._create_processed_data(indicator, trading_signal, position, action_states)
```

## Code Conventions

- **Chinese comments**: Most comments and variable names are in Chinese
- **Modular design**: Each component has clear separation of concerns
- **Method naming**: Strategy methods follow `_generate_<strategy>_signals()` pattern
- **Data handling**: Uses polars DataFrames for performance, converts to numpy arrays for computation

## Important Notes

1. **Wind Excel add-in required**: `excel_to_parquet.py` requires Windows, Excel, and Wind Financial Terminal add-in installed
2. **Data preprocessing**: `data_handler.py` handles missing values with forward/backward filling
3. **Backtest assumptions**: Uses next-day execution for trades (signal at day t, position at day t+1)
4. **Visualization**: Plots are displayed using matplotlib's interactive mode

## File Organization

- Core modules in root directory
- Data files in `data/` subdirectory
- Cache files in `__pycache__/` (auto-generated)
- Vercel configuration in `.vercel/` (likely for deployment)

## Strategy Performance Notes

Based on backtesting AUFI.WI (Gold Futures Index) over the last 5 years:
- **TMA**: Top performer — TMA (5/20/60) ~158% cumulative return, ~21% annualized
- **Donchian**: Strong and consistent — Donchian (50) ~108%, Donchian (20) ~90%
- **EWMA_LONG_ONLY**: Solid ~107% with low drawdown
- **EWMA**: Moderate ~68% (long-short underperforms long-only in strong bull trend)
- **MACD**: Positive but lower returns ~8%
- **RSI / Bollinger**: Negative returns in trending gold market — mean-reversion struggles

## Testing and Optimization Tools

### `run_all_strategies.py`
- Batch runs all 10 strategy configurations
- Generates performance metrics: cumulative/annualized return, max drawdown, win rate, avg trade return
- Outputs Excel summary, per-strategy trade sheets, HTML report, and PNG charts

### `test_strategies.py`
- Quick smoke test of all strategies
- Prints cumulative return ranking in terminal — no file output

## Extension Points

1. **New strategies**: Add ATR-based, momentum, or machine learning strategies
2. **Parameter optimization**: Implement grid search or genetic algorithms for parameter tuning
3. **Risk management**: Add stop-loss, take-profit, position sizing logic
4. **Multi-timeframe analysis**: Combine signals from different time periods
5. **Sharpe ratio**: Add risk-adjusted return metrics
6. **Walk-forward testing**: Implement robust out-of-sample testing methodology
7. **Strategy combination**: Create meta-strategies that combine multiple signals