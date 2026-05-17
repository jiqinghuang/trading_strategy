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
       - Buys when price breaks above upper channel (N-period high)
       - Sells when price breaks below lower channel (N-period low)
       - Configurable channel period (default 20)
     - **Bollinger Bands**: Volatility-based strategy
       - Uses moving average with standard deviation bands
       - Buys when price breaks above lower band, sells when breaks below upper band
       - Configurable: period (default 20), standard deviations (default 2.0)

3. **Backtesting Layer** (`backtest_engine.py`)
   - `BacktestEngine` performs historical simulation
   - Calculates returns, cumulative returns, and trading records
   - Uses execution price (average of open and close) for realistic simulation

4. **Visualization Layer** (`visualization.py`)
   - `StrategyVisualizer` generates plots for price trends, signals, and performance
   - Three plot types: price/indicator, cumulative returns with signals, position holding

5. **Additional Tools** (`l1_filter.py`)
   - Implements L1 trend filtering using ADMM algorithm for signal smoothing
   - Useful for noise reduction in price series

## Key Dependencies

- **numpy**: Numerical computations
- **polars**: Fast DataFrame operations (alternative to pandas)
- **matplotlib**: Plotting and visualization
- **tqdm**: Progress bars for iterative algorithms
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

### Testing L1 Trend Filter
```bash
python l1_filter.py
```
Runs L1 trend filtering on AG(T+D) data with different lambda parameters.

### Testing All Strategies
```bash
python test_strategies.py
```
Runs all implemented strategies and displays performance comparison including cumulative returns and trade counts.

### Quick Strategy Test
```bash
python test_strategies.py
```
Quick performance test showing key metrics for all strategies.

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

Based on backtesting AU(T+D) data from 2020-2026:
- **EWMA_LONG_ONLY**: Highest cumulative return (~212%) with 164 trades
- **EWMA**: Good performance (~131%) with same trade count
- **MACD**: Moderate performance (~100%) with fewer trades (126)
- **Donchian**: May require parameter tuning (default settings produced no signals)
- **Bollinger**: Lower performance (~35%) with conservative signal generation

## Testing and Optimization Tools

### `test_strategies.py`
- Comprehensive testing of all strategies
- Displays detailed trade records and performance metrics
- Ranks strategies by cumulative return

### `test_strategies.py`
- Comprehensive strategy testing with performance comparison
- Quick test showing key metrics: cumulative return, trade count, parameters

## Extension Points

1. **New trend-following strategies**: Add RSI, ATR-based, or momentum strategies
2. **Parameter optimization**: Implement grid search or genetic algorithms for parameter tuning
3. **Risk management**: Add stop-loss, take-profit, position sizing logic
4. **Multi-timeframe analysis**: Combine signals from different time periods
5. **Machine learning integration**: Use ML models for signal filtering or prediction
6. **Performance analytics**: Add Sharpe ratio, maximum drawdown, win rate calculations
7. **Walk-forward testing**: Implement robust out-of-sample testing methodology
8. **Strategy combination**: Create meta-strategies that combine multiple signals