# Milestone 2: Risk, PnL, State & Config Engine

**Duration:** 2 weeks (80 hours)
**Cost:** $4,000
**Objective:** Implement risk controls, accurate accounting, crash recovery, and external configuration

---

## Day-by-Day Breakdown

### Week 3: Risk Manager & PnL Engine

#### Day 11: Risk Manager Architecture
**Hours:** 8h
**Tasks:**
- [ ] Design Risk Manager module
  - Pre-trade check interface
  - Drawdown monitoring system
  - Risk event emission (observer pattern)
- [ ] Define risk data models
  ```python
  class RiskCheck:
      passed: bool
      reason: Optional[str]
      current_leverage: float
      proposed_leverage: float

  class RiskEvent:
      type: str  # DRAWDOWN_BREACH, LEVERAGE_EXCEEDED
      level: Optional[float]  # -0.05, -0.10, -0.15
      symbol: Optional[str]
      timestamp: datetime
  ```
- [ ] Implement leverage calculation
  ```python
  def calculate_portfolio_leverage(positions, equity):
      total_notional = sum(abs(pos.size * pos.mark_price) for pos in positions)
      return total_notional / equity if equity > 0 else 0
  ```

**Deliverables:**
- `risk_manager.py` interface
- Risk data models
- Leverage calculation logic

---

#### Day 12-13: Pre-Trade Risk Checks
**Hours:** 16h
**Tasks:**
- [ ] Implement `pre_trade_check()` method
  - Simulate order execution
  - Calculate new portfolio state
  - Check against `portfolio.leverage_cap`
  - Return `RiskCheck` object
- [ ] Per-symbol position limits (if configured)
- [ ] Margin requirement calculation
  - Account for cross-margin vs isolated margin
  - Consider unrealized PnL
- [ ] Integration with OMS
  - OMS must call `risk_manager.pre_trade_check()` before every order
  - Reject order immediately if check fails
- [ ] Unit tests for edge cases
  - At leverage cap
  - Just under leverage cap
  - Multiple concurrent orders

**Deliverables:**
- `pre_trade_check()` implementation
- OMS integration
- Unit test suite

**Testing:**
```python
# Set leverage_cap = 6.0
# Open position with 5.8x leverage
# Attempt new order that would push to 6.2x
risk_check = risk_manager.pre_trade_check(proposed_order)
assert risk_check.passed == False
assert "leverage cap" in risk_check.reason.lower()
```

---

#### Day 14-15: PnL & Fee Engine
**Hours:** 16h
**Tasks:**
- [ ] Define Trade and Position models
  ```python
  class Trade:
      id: str
      symbol: str
      side: str
      entry_price: float
      exit_price: Optional[float]
      quantity: float
      entry_time: datetime
      exit_time: Optional[datetime]
      fee_paid: float
      funding_paid: float
      realized_pnl: float
      status: str  # OPEN/CLOSED

  class Position:
      symbol: str
      size: float  # Positive for long, negative for short
      entry_price: float  # Volume-weighted average
      unrealized_pnl: float
      realized_pnl: float
      last_updated: datetime
  ```
- [ ] Implement trade lifecycle
  - **Open:** Create Trade on first fill
  - **Update:** Add to position on subsequent fills (same direction)
  - **Close:** Reduce position on opposite fills, calculate realized PnL
- [ ] Realized PnL calculation
  ```python
  # For closing a long position
  realized_pnl = (exit_price - entry_price) * quantity - fees - funding_paid
  ```
- [ ] Unrealized PnL calculation
  ```python
  # For open long position
  unrealized_pnl = (current_market_price - entry_price) * quantity
  ```
- [ ] Fee tracking
  - Capture from `executionReport` WebSocket event
  - Aggregate at trade level and portfolio level
- [ ] Funding rate tracking (Futures only)
  - Fetch from `/fapi/v1/fundingRate`
  - Calculate: `funding_payment = funding_rate * position_size`
  - Add to trade's `funding_paid` field

**Deliverables:**
- `pnl_engine.py` with Trade/Position models
- PnL calculation logic
- Fee and funding tracking

**Testing:**
```python
# KPI 2.2: Trade lifecycle
# 1. Open long 0.1 BTC @ $60,000
trade = pnl_engine.on_fill(order_buy)
assert trade.status == "OPEN"
assert trade.entry_price == 60000

# 2. Close long 0.1 BTC @ $60,500
trade = pnl_engine.on_fill(order_sell)
assert trade.status == "CLOSED"
assert trade.realized_pnl > 0  # Profitable trade
assert trade.fee_paid > 0
```

---

### Week 4: State Persistence & Configuration

#### Day 16-17: SQLite Database Schema
**Hours:** 16h
**Tasks:**
- [ ] Create database schema (see spec Section 3.5)
  - `app_state` table (key-value store)
  - `orders` table (order history)
  - `positions` table (current positions)
  - `strategy_state` table (JSON blob for strategy)
- [ ] Implement database manager
  ```python
  class DatabaseManager:
      def __init__(self, db_path):
          self.conn = sqlite3.connect(db_path)
          self._create_tables()

      def save_order(self, order):
          # Insert or update order

      def save_position(self, position):
          # Insert or update position

      def save_strategy_state(self, symbol, state_dict):
          # Save as JSON blob

      def get_all_orders(self):
          # Return all orders

      def get_open_positions(self):
          # Return all open positions
  ```
- [ ] Persistence triggers
  - **Periodic:** Every 60 seconds (background thread)
  - **Event-based:** On order state change, position update
- [ ] Write-ahead logging (WAL) mode for SQLite
  - Prevents database locking issues
  - Better concurrency

**Deliverables:**
- SQLite schema creation scripts
- `database_manager.py`
- Persistence trigger system

---

#### Day 18: State Recovery Protocol
**Hours:** 8h
**Tasks:**
- [ ] Implement recovery on startup
  1. Load last saved state from DB
  2. Call `get_open_orders()` via REST API
  3. Call `get_open_positions()` via REST API (Futures)
  4. **Reconcile:**
     - If order in DB but not on exchange → Mark as CANCELED/REJECTED
     - If order on exchange but not in DB → Log as "stray order", cancel it
     - If position mismatch → Log error, use exchange as source of truth
- [ ] Handle edge cases
  - Empty database (first run)
  - Database corruption (backup strategy)
  - Exchange API unavailable during recovery
- [ ] Recovery logging
  - Emit `STATE_RECOVERED` event
  - Log discrepancies found during reconciliation

**Deliverables:**
- `recovery_manager.py`
- Reconciliation logic
- Error handling for recovery failures

**Testing:**
```python
# KPI 2.3: Crash recovery
# 1. Start bot, open position
# 2. Kill process (SIGKILL)
# 3. Restart bot
# 4. Verify position recovered
recovered_position = oms.get_position("BTCUSDT")
assert recovered_position.size == 0.1
assert "STATE_RECOVERED" in logs
```

---

#### Day 19: Configuration Manager
**Hours:** 8h
**Tasks:**
- [ ] JSON configuration file structure (see spec Section 3.6)
- [ ] Configuration validation
  ```python
  from pydantic import BaseModel, Field, validator

  class ExchangeConfig(BaseModel):
      api_key: str
      api_secret: str
      testnet: bool = True
      market_type: str = "futures"

      @validator('market_type')
      def validate_market_type(cls, v):
          if v not in ["spot", "futures"]:
              raise ValueError("market_type must be 'spot' or 'futures'")
          return v

  class Config(BaseModel):
      exchange: ExchangeConfig
      symbols: List[str]
      portfolio: PortfolioConfig
      # ... etc
  ```
- [ ] Runtime access to config
  - Singleton pattern for global access
  - Hot reload support (optional, for later)
- [ ] Default values and required fields
- [ ] Config file template generation

**Deliverables:**
- `config_manager.py`
- `config.json` template with all parameters
- Validation schema using Pydantic

---

#### Day 20: Integration & KPI Validation
**Hours:** 8h
**Tasks:**
- [ ] **KPI 2.1:** Drawdown detection
  - Manually set `peak_equity` in database
  - Adjust current equity to trigger -6% drawdown
  - Verify `DRAWDOWN_BREACH` event emitted
  - Check log format matches spec
- [ ] **KPI 2.2:** Accurate PnL calculation
  - Open long position at market price
  - Close position at different price
  - Verify `TRADE_CLOSED` log includes:
    - `fee_paid > 0`
    - `funding_paid` (if applicable)
    - `realized_pnl` (correct calculation)
- [ ] **KPI 2.3:** State recovery
  - Start bot with open position
  - Kill process (`kill -9` on Linux, Task Manager on Windows)
  - Restart bot
  - Verify position and orders recovered
  - Check `STATE_RECOVERED` in logs
- [ ] **KPI 2.4:** Config-based leverage change
  - Set `base_leverage: 5` in config
  - Start bot
  - Change to `base_leverage: 3`
  - Restart bot
  - Verify exchange leverage set to 3x (check Binance UI or log)

**Deliverables:**
- KPI validation report
- Test logs
- Bug fixes

---

## Module Structure

```
src/
├── risk/
│   ├── __init__.py
│   ├── risk_manager.py      # Pre-trade checks, drawdown monitoring
│   ├── risk_models.py        # RiskCheck, RiskEvent
│   └── leverage_calc.py      # Leverage calculations
├── pnl/
│   ├── __init__.py
│   ├── pnl_engine.py         # Trade lifecycle, PnL calculation
│   ├── pnl_models.py         # Trade, Position models
│   └── fee_tracker.py        # Fee and funding aggregation
├── persistence/
│   ├── __init__.py
│   ├── database_manager.py   # SQLite operations
│   ├── recovery_manager.py   # State recovery protocol
│   └── schema.sql            # Database schema
└── config/
    ├── __init__.py
    ├── config_manager.py     # Config loading & validation
    └── config_schema.py      # Pydantic models
```

---

## Key Implementation Details

### 1. Drawdown Monitoring
```python
class RiskManager:
    def __init__(self, config):
        self.peak_equity = self._load_peak_equity()
        self.drawdown_levels = config.risk.drawdown_levels  # [-0.05, -0.10, -0.15]
        self.breached_levels = set()

    def on_equity_update(self, current_equity):
        # Update peak if new high
        if current_equity > self.peak_equity * 1.01:
            self.peak_equity = current_equity
            self.breached_levels.clear()

        # Calculate drawdown
        drawdown = (self.peak_equity - current_equity) / self.peak_equity

        # Check for breaches
        for level in self.drawdown_levels:
            if drawdown >= abs(level) and level not in self.breached_levels:
                self._emit_risk_event(RiskEvent(
                    type="DRAWDOWN_BREACH",
                    level=level,
                    symbol=None,
                    timestamp=datetime.utcnow()
                ))
                self.breached_levels.add(level)
```

### 2. Volume-Weighted Entry Price
```python
class Position:
    def add_fill(self, price, quantity):
        """Update position with new fill (averaging entry price)"""
        total_value = self.entry_price * self.size + price * quantity
        self.size += quantity
        self.entry_price = total_value / self.size if self.size != 0 else 0
```

### 3. State Recovery
```python
class RecoveryManager:
    async def recover_state(self):
        logger.info("Starting state recovery...")

        # Load from DB
        db_orders = self.db.get_all_orders()
        db_positions = self.db.get_open_positions()

        # Fetch from exchange
        exchange_orders = await self.exchange.get_open_orders()
        exchange_positions = await self.exchange.get_positions()

        # Reconcile orders
        for db_order in db_orders:
            if db_order.status in ["NEW", "PARTIALLY_FILLED"]:
                if not self._find_order(db_order.order_id, exchange_orders):
                    logger.warning(f"Order {db_order.order_id} not on exchange, marking CANCELED")
                    db_order.status = "CANCELED"
                    self.db.save_order(db_order)

        # Check for stray orders
        for ex_order in exchange_orders:
            if not self._find_order(ex_order.order_id, db_orders):
                logger.error(f"Stray order {ex_order.order_id} found, canceling...")
                await self.exchange.cancel_order(ex_order.symbol, ex_order.order_id)

        # Reconcile positions
        for ex_pos in exchange_positions:
            db_pos = self._find_position(ex_pos.symbol, db_positions)
            if not db_pos or db_pos.size != ex_pos.size:
                logger.warning(f"Position mismatch for {ex_pos.symbol}, using exchange data")
                self.db.save_position(ex_pos)

        logger.info("State recovery complete")
```

---

## Configuration (Milestone 2 Additions)

```json
{
  "portfolio": {
    "leverage_cap": 6.0,
    "weights": {
      "BTCUSDT": 0.45,
      "ETHUSDT": 0.35,
      "SOLUSDT": 0.20
    }
  },
  "engine": {
    "base_leverage": 5
  },
  "risk": {
    "drawdown_levels": [-0.05, -0.10, -0.15]
  },
  "database": {
    "path": "bot_state.db"
  }
}
```

---

## Testing Checklist

### Unit Tests
- [ ] Leverage calculation
- [ ] Pre-trade check logic
- [ ] PnL calculation (long/short)
- [ ] Fee aggregation
- [ ] Config validation
- [ ] Database CRUD operations

### Integration Tests
- [ ] Full trade lifecycle (open → close)
- [ ] Position averaging on multiple fills
- [ ] State persistence triggers
- [ ] Recovery from empty/corrupted DB
- [ ] Config reload

### KPI Validation
- [ ] KPI 2.1: Drawdown event at -6%
- [ ] KPI 2.2: Accurate TRADE_CLOSED log
- [ ] KPI 2.3: Crash recovery
- [ ] KPI 2.4: Leverage change via config

---

## Risk & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Database lock during concurrent writes | Medium | Use WAL mode, serialize writes |
| Funding rate API unavailable | Low | Cache last known rate, log warning |
| Exchange position mismatch on recovery | High | Trust exchange, log discrepancy |
| Config file corruption | Medium | Validate on load, keep backup |

---

## Dependencies

**External:**
- Funded Testnet account (USDT)
- Access to Binance Futures API

**Libraries:**
- `pydantic==2.4.0` (config validation)
- Existing from Milestone 1

---

## Approval Criteria

✅ All 4 KPIs passed
✅ PnL calculation accuracy verified (manual check)
✅ State recovery tested with forced shutdown
✅ Config validation prevents invalid values
✅ No data loss during crash

**Sign-off Required By:** Client Stakeholder
**Next Milestone Start:** Upon written approval

---

**Milestone Owner:** [Lead Developer]
**Status:** Not Started
**Last Updated:** 2025-10-02
