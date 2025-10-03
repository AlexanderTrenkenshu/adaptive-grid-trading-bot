# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Adaptive Multi-System Grid Trading Bot** - A sophisticated Python trading bot for Binance Spot/Futures markets featuring:
- Three-system ensemble strategy (UP/DOWN/NEUTRAL)
- Adaptive learning with weekly weight updates
- Dynamic parameter adjustment (order size, grid spacing, TP/SL)
- Multi-level risk management with drawdown brakes
- Full state persistence and crash recovery
- Graceful shutdown with position closing

## Development Environment

### Virtual Environment
```bash
# Windows
.venv\Scripts\activate

# Unix/MacOS
source .venv/bin/activate
```

### Common Commands

**Run the bot:**
```bash
python src/main.py --config config/config.json
```

**Run on Testnet (default):**
```bash
# Ensure config.json has "testnet": true
python src/main.py
```

**Graceful shutdown:**
```
Ctrl+C (bot will close all positions and exit cleanly)
```

**Install dependencies:**
```bash
pip install -r requirements.txt
```

**Run tests:**
```bash
# All tests
pytest

# Unit tests only
pytest tests/unit/

# Integration tests (requires Testnet credentials)
pytest tests/integration/

# Specific test
pytest tests/unit/test_exchange_gateway.py::test_order_placement
```

**Linting:**
```bash
flake8 src/ --max-line-length=120
```

**Type checking:**
```bash
mypy src/ --ignore-missing-imports
```

## Architecture Overview

### Core Modules (from spec)

1. **Exchange Gateway** (`src/exchange/`)
   - Binance REST API + WebSocket integration
   - Auto-reconnection with exponential backoff
   - Rate limit management (1200 weight/minute)
   - Supports Spot and Futures markets

2. **Order Management System (OMS)** (`src/oms/`)
   - Order state machine (PENDING_NEW → NEW → FILLED/CANCELED)
   - Partial fill handling
   - Retry logic for transient errors (5xx, timeouts)
   - Order modification via cancelReplace API

3. **Risk Manager** (`src/risk/`)
   - Pre-trade leverage check (enforces `portfolio.leverage_cap`)
   - Drawdown monitoring at -5%, -10%, -15%
   - Risk event emission (observer pattern)

4. **PnL & Fee Engine** (`src/pnl/`)
   - Volume-weighted entry price calculation
   - Realized/Unrealized PnL tracking
   - Fee aggregation (maker/taker)
   - Funding rate tracking (Futures only)

5. **State Persistence** (`src/persistence/`)
   - SQLite database with WAL mode
   - Periodic saves (every 60s) + event-based triggers
   - State recovery protocol on startup
   - Order/position reconciliation with exchange

6. **Configuration Manager** (`src/config/`)
   - JSON-based external configuration
   - Pydantic validation schema
   - All parameters in spec Section 3.6 & "Parameter Glossary"

7. **Logging & Reporting** (`src/logging/`)
   - Structured JSON logs (one per line)
   - Event types: TRADE_CLOSED, STATUS, ORDER_PLACED
   - Daily rotating log files (`logs/bot_2025-10-26.log`)

8. **Strategy Engine** (`src/strategy/`)
   - **UP System:** Bullish continuation (higher highs, EMA slope, volume)
   - **DOWN System:** Bearish continuation (lower lows, negative slope)
   - **NEUTRAL System:** Mean reversion (Bollinger Bands, RSI, autocorrelation)
   - **Ensemble:** Long conviction (L) and Short conviction (S)
   - **Adaptive Learning:** Weekly feature/system weight updates

## Key Implementation Details

### 1. Order Execution Priority
- Use **LIMIT orders** wherever possible to minimize fees
- Market orders only for:
  - Graceful shutdown (closing positions)
  - Stop-loss triggers (when conviction flips)
  - Initial position entry (if configured)

### 2. Dynamic Parameter Formulas (from spec Section 5.4)
```python
# Volatility factor
volatility_factor = ATR(14)[1h] / ATR(14)[1h]_SMA(100)

# Dynamic order size
long_size = base_order_size * (1 + size_mult * L + imb_mult * imbalance) / (1 + vol_mult * volatility_factor)
# Clamp: [0.25 * base, 3.0 * base]

# Dynamic grid spacing
long_spacing = baseline_spacing * (1 + vol_mult * vol_factor) / (1 + 0.5 * L + 0.4 * imbalance)
# Clamp: [spacing_clamp_min * ATR, spacing_clamp_max * ATR]

# Dynamic take-profit
tp_distance = long_spacing * (1 + tp_conviction_mult * L)
# Cap: tp_cap_multiplier * initial_tp_distance
```

### 3. Order Re-centering Logic (spec Section 5.2.4)
- **Trigger:** Every 1m candle close
- **Condition:** Order price > 4 * ATR away from market
- **Action:** Modify order to new price within threshold
- **Fallback:** Cancel + replace if modify fails

### 4. Conviction-Based Entry Filter (spec Section 5.3.1)
```python
# Only place order if conviction exceeds dynamic threshold
min_entry_conviction = percentile(last_1440_convictions, 80)  # 80th percentile
if L < min_entry_conviction:
    # Skip order placement
```

### 5. Drawdown Brakes (spec Section 5.5.4)
```python
# -5% drawdown
if current_drawdown >= 0.05:
    base_order_size *= 0.5
    tp_distance *= 0.7

# -10% drawdown
if current_drawdown >= 0.10:
    base_leverage *= 0.6
    conviction_percentile_threshold = 70

# -15% drawdown (Safe Mode)
if current_drawdown >= 0.15:
    conviction_percentile_threshold = 85
    base_leverage *= 0.5  # Further reduction
    min_entry_conviction = 0.8  # Hard gate
    tp_distance *= 0.5  # Aggressive profit-taking
```

## Configuration

### Critical Parameters (config.json)
```json
{
  "exchange": {
    "testnet": true,           // ALWAYS true for development
    "market_type": "futures"   // "spot" or "futures"
  },
  "portfolio": {
    "leverage_cap": 6.0,       // Hard limit enforced by Risk Manager
    "weights": {               // Symbol allocation
      "BTCUSDT": 0.45,
      "ETHUSDT": 0.35,
      "SOLUSDT": 0.20
    }
  },
  "engine": {
    "utilization": 0.3,        // Fraction of equity in resting orders
    "max_orders_per_symbol": 25,
    "base_leverage": 5
  },
  "risk": {
    "drawdown_levels": [-0.05, -0.10, -0.15]
  }
}
```

**Full parameter reference:** See spec "Parameter Glossary" (pages 10-20)

## Development Workflow

### Adding a New Feature
1. Read relevant section in `Technical Specification_ Adaptive Multi-System Grid Trading Bot_Updated.pdf`
2. Update module in `src/`
3. Add unit tests in `tests/unit/`
4. Add integration test in `tests/integration/` (if needed)
5. Update CHANGELOG.md
6. Test on Testnet before PR

### Debugging
1. Check logs in `logs/bot_YYYY-MM-DD.log`
2. Use `jq` for JSON log parsing:
   ```bash
   cat logs/bot_2025-10-26.log | jq 'select(.event_type == "TRADE_CLOSED")'
   ```
3. Query database for state:
   ```bash
   sqlite3 bot_state.db "SELECT * FROM positions;"
   ```

### Common Issues

**WebSocket disconnects frequently:**
- Check network stability
- Verify exponential backoff is working (`websocket_manager.py:_reconnect()`)
- Ensure listenKey is refreshed every 30 minutes (Futures)

**Orders rejected by exchange:**
- Check symbol filters via `get_exchange_info()`
- Verify order quantity meets `minQty` and `stepSize`
- Ensure notional value exceeds `MIN_NOTIONAL`

**Leverage cap exceeded:**
- Bug in `risk_manager.py:pre_trade_check()`
- Ensure OMS calls risk check BEFORE every order
- Check if unrealized PnL is included in leverage calculation

**State recovery fails:**
- Database corruption → restore from backup
- Stray orders on exchange → bot should cancel automatically
- Position mismatch → trust exchange, log discrepancy

## Testing Strategy

### Unit Tests
- Mock all external APIs (Binance)
- Test pure functions (calculations, state machine)
- Coverage target: >80%

### Integration Tests
- Use Binance Testnet (requires credentials)
- Test end-to-end workflows (place → fill → close)
- Validate WebSocket reconnection

### System Tests
- 48-hour Testnet run (Milestone 3)
- 72-hour Testnet run (Milestone 6)
- Monitor for memory leaks, crashes

## Important Constraints

### Exchange-Specific
- **Rate Limits:** 1200 weight/minute (REST), managed by `rate_limiter.py`
- **WebSocket Limits:** 300 connections/IP, 10 streams/connection
- **Order Limits:** 200 open orders/account (Binance)
- **Time Sync:** System clock must be within 1 second of Binance server time

### Bot-Specific
- **No Naked Positions:** Always have TP/SL orders for open positions
- **Graceful Shutdown Only:** Never kill without closing positions
- **Testnet First:** All development on Testnet, production requires explicit flag change

## File References

- **Project Plan:** `PROJECT_PLAN.md`
- **Milestone 1:** `MILESTONE_1_PLAN.md`
- **Milestone 2:** `MILESTONE_2_PLAN.md`
- **Milestones 3-6:** `MILESTONE_3_TO_6_SUMMARY.md`
- **Roadmap:** `DEVELOPMENT_ROADMAP.md`
- **Specification:** `Technical Specification_ Adaptive Multi-System Grid Trading Bot_Updated.pdf`

## Contact

**Project Manager:** [TBD]
**Lead Developer:** [TBD]
**Documentation:** See `docs/` directory after Milestone 6 completion


If you don't know the answer just tell "I don't know". Don't lie