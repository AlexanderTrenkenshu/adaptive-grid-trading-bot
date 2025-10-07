f# Milestone 1: Exchange Gateway & Core Order Management

**Duration:** 2 weeks (80 hours)
**Cost:** $4,000
**Objective:** Build robust Binance API integration with real-time data and order execution

---

## Day-by-Day Breakdown

### Week 1: Exchange Gateway & WebSocket Foundation

#### Day 1: Setup & Architecture Design
**Hours:** 8h
**Tasks:**
- [ ] Project structure setup
  - Create directory structure (`src/`, `tests/`, `config/`, `logs/`)
  - Initialize virtual environment
  - Create `requirements.txt`
- [ ] Design Exchange Gateway interface
  - Define abstract base class for exchange operations
  - Document required methods (REST + WebSocket)
- [ ] Select implementation approach
  - Decision: `python-binance` vs `ccxt` vs custom
  - Rationale documentation

**Deliverables:**
- Project skeleton
- `ExchangeGateway` interface design doc
- Initial `requirements.txt`

---

#### Day 2-3: REST API Implementation
**Hours:** 16h
**Tasks:**
- [ ] Implement Binance REST client
  - `get_exchange_info()` - Symbol filters
  - `get_ohlc_data()` - Historical candles
  - `get_exchange_instruments()` - 24hr tickers
  - `get_account_balance()` - Account info
  - `get_positions()` - Futures positions
  - `set_leverage()` - Leverage control
- [ ] Order execution methods
  - `submit_order()` - Place new order
  - `modify_order()` - Modify existing order
  - `cancel_order()` - Cancel order
  - `get_open_orders()` - Query active orders
- [ ] Error handling & retry logic
  - Exponential backoff for 5xx errors
  - Immediate fail for 4xx errors
  - Rate limit tracking (1200 weight/minute)
- [ ] Unit tests for REST methods (mocked responses)

**Deliverables:**
- `exchange_gateway.py` with all REST methods
- Error handling framework
- Unit test suite (>80% coverage)

**Testing:**
```python
# Testnet validation
gateway = ExchangeGateway(testnet=True)
info = gateway.get_exchange_info("BTCUSDT")
assert info['symbol'] == 'BTCUSDT'
assert 'filters' in info
```

---

#### Day 4-5: WebSocket Implementation
**Hours:** 16h
**Tasks:**
- [ ] Market data streams
  - `@trade` stream for tick data
  - `@kline_1m`, `@kline_15m`, `@kline_1h`, `@kline_1d` streams
  - `@bookTicker` for best bid/ask
- [ ] User data streams
  - Generate and manage `listenKey`
  - `executionReport` handler for order updates
  - `ACCOUNT_UPDATE` handler for balance/position changes
- [ ] Connection management
  - Auto-reconnect with exponential backoff (1s, 2s, 4s, 8s, ..., 120s max)
  - Re-subscription after reconnect
  - Ping/pong heartbeat monitoring
- [ ] ListenKey keep-alive (30-minute refresh for Futures)

**Deliverables:**
- `websocket_manager.py` with multi-stream support
- Reconnection logic
- Event-driven callback system

**Testing:**
```python
# KPI 1.1: 1-hour stable connection
ws_manager = WebSocketManager(testnet=True)
ws_manager.subscribe_kline("BTCUSDT", "1m", on_kline_update)
time.sleep(3600)  # Should maintain connection
assert ws_manager.is_connected()
```

---

### Week 2: Order Management System

#### Day 6-7: Order State Machine
**Hours:** 16h
**Tasks:**
- [ ] Define order data model
  ```python
  class Order:
      order_id: int
      symbol: str
      side: str  # BUY/SELL
      type: str  # LIMIT/MARKET
      status: str  # PENDING_NEW/NEW/FILLED/CANCELED/REJECTED
      price: float
      orig_qty: float
      executed_qty: float
      cummulative_quote_qty: float
      time_in_force: str
      created_at: datetime
      updated_at: datetime
  ```
- [ ] Implement state machine transitions
  - `PENDING_NEW` → `NEW` (order accepted)
  - `NEW` → `PARTIALLY_FILLED` → `FILLED`
  - `NEW` → `PENDING_CANCEL` → `CANCELED`
  - `PENDING_NEW` → `REJECTED`
- [ ] Order tracking & reconciliation
  - In-memory order book
  - WebSocket update integration
  - REST API sync on startup

**Deliverables:**
- `order_management.py` with state machine
- Order tracking system
- Unit tests for state transitions

---

#### Day 8: Partial Fill Handling
**Hours:** 8h
**Tasks:**
- [ ] Partial fill detection from `executionReport`
- [ ] Update `executed_qty` and `cummulative_quote_qty`
- [ ] Trigger PnL calculation for filled portion (stub for now)
- [ ] Expose partial fill status to strategy
- [ ] Logging for partial fills

**Deliverables:**
- Partial fill handler
- Integration with OMS state machine

**Testing:**
```python
# Place LIMIT order that partially fills
order = oms.submit_order("BTCUSDT", "BUY", "LIMIT", 0.1, 60000)
# Simulate partial fill via WebSocket event
assert order.status == "PARTIALLY_FILLED"
assert order.executed_qty < order.orig_qty
```

---

#### Day 9: Retry Logic & Error Handling
**Hours:** 8h
**Tasks:**
- [ ] Transient error retry (5xx, timeouts)
  - Exponential backoff: 1s, 2s, 4s, 8s
  - Max 3 retry attempts
  - Preserve original order intent
- [ ] Permanent error handling (4xx)
  - Log error details
  - Emit alert to strategy/risk system
  - Handle specific errors:
    - `API_ORDER_MIN_NOTIONAL`
    - `INSUFFICIENT_BALANCE`
    - `INVALID_LEVERAGE`
- [ ] Rate limit management
  - Track API weight usage
  - Implement request queuing if needed
  - Backoff if approaching limit

**Deliverables:**
- Retry framework
- Error classification system
- Rate limit tracker

---

#### Day 10: Integration Testing & KPI Validation
**Hours:** 8h
**Tasks:**
- [ ] **KPI 1.1:** 1-hour WebSocket stability test
  - Connect to Testnet
  - Subscribe to BTCUSDT streams
  - Monitor for 1 hour
  - Verify no disconnections or manual intervention
- [ ] **KPI 1.2:** 5 market orders (3 long, 2 short)
  - Execute via console command or script
  - Verify all filled
  - Check logs for ORDER_PLACED events
- [ ] **KPI 1.3:** Order modification & cancellation
  - Place 3 LIMIT orders
  - Modify 2 orders (change price)
  - Cancel 1 order
  - Verify logs show ORDER_MODIFIED and ORDER_CANCELED
- [ ] **KPI 1.4:** Network failure simulation
  - Disconnect WiFi/network
  - Wait 30 seconds
  - Reconnect network
  - Verify bot reconnects within 60 seconds
  - Check stream re-subscription

**Deliverables:**
- KPI validation report
- Test logs
- Bug fixes (if any)

---

## Module Structure

```
src/
├── exchange/
│   ├── __init__.py
│   ├── gateway.py           # Abstract base class
│   ├── binance_gateway.py   # Binance implementation
│   ├── websocket_manager.py # WebSocket handling
│   └── rate_limiter.py      # Rate limit tracking
├── oms/
│   ├── __init__.py
│   ├── order_manager.py     # Order state machine
│   ├── order_models.py      # Data models
│   └── order_tracker.py     # Order tracking
└── utils/
    ├── __init__.py
    ├── retry.py             # Retry decorators
    └── logger.py            # Logging setup
```

---

## Key Implementation Details

### 1. WebSocket Reconnection Logic
```python
class WebSocketManager:
    def __init__(self, max_reconnect_delay=120):
        self.max_reconnect_delay = max_reconnect_delay
        self.reconnect_attempt = 0

    async def _reconnect(self):
        delay = min(2 ** self.reconnect_attempt, self.max_reconnect_delay)
        logger.warning(f"Reconnecting in {delay}s (attempt {self.reconnect_attempt})")
        await asyncio.sleep(delay)
        await self._connect()
        await self._resubscribe_all()
        self.reconnect_attempt = 0  # Reset on success
```

### 2. Order State Machine
```python
class OrderStateMachine:
    TRANSITIONS = {
        "PENDING_NEW": ["NEW", "REJECTED"],
        "NEW": ["PARTIALLY_FILLED", "FILLED", "PENDING_CANCEL"],
        "PARTIALLY_FILLED": ["FILLED", "PENDING_CANCEL"],
        "PENDING_CANCEL": ["CANCELED"]
    }

    def transition(self, order, new_status):
        if new_status not in self.TRANSITIONS.get(order.status, []):
            raise InvalidTransitionError(f"{order.status} -> {new_status}")
        order.status = new_status
        order.updated_at = datetime.utcnow()
        self._persist(order)
```

### 3. Retry Decorator
```python
def retry_on_transient_error(max_attempts=3):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except TransientError as e:
                    if attempt == max_attempts - 1:
                        raise
                    delay = 2 ** attempt
                    logger.warning(f"Retry {attempt+1}/{max_attempts} after {delay}s: {e}")
                    await asyncio.sleep(delay)
        return wrapper
    return decorator
```

---

## Configuration (Milestone 1 Subset)

```json
{
  "exchange": {
    "api_key": "your_testnet_api_key",
    "api_secret": "your_testnet_api_secret",
    "testnet": true,
    "market_type": "futures"
  },
  "websocket": {
    "reconnect_max_delay": 120,
    "ping_interval": 20
  },
  "oms": {
    "retry_attempts": 3,
    "retry_backoff_base": 2
  }
}
```

---

## Testing Checklist

### Unit Tests
- [ ] REST API methods (mocked)
- [ ] WebSocket message parsing
- [ ] Order state transitions
- [ ] Retry logic
- [ ] Error classification

### Integration Tests
- [ ] Real Testnet REST calls
- [ ] WebSocket subscription & data flow
- [ ] Order placement end-to-end
- [ ] Reconnection after disconnect

### KPI Validation
- [ ] KPI 1.1: 1-hour stable WebSocket
- [ ] KPI 1.2: 5 market orders executed
- [ ] KPI 1.3: 2 modifications + 1 cancellation
- [ ] KPI 1.4: Auto-reconnect within 60s

---

## Risk & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Testnet API instability | Medium | Use mainnet for connectivity tests (no orders) |
| WebSocket message format changes | Medium | Version check, fallback to REST polling |
| Rate limit violations | Low | Pre-calculate request weight, implement queuing |
| Order modification not supported | Medium | Fallback to cancel+replace |

---

## Dependencies

**External:**
- Binance Testnet account with API credentials
- Internet connection
- Python 3.9+

**Libraries:**
- `python-binance==1.0.17` (or latest stable)
- `websocket-client==1.6.1`
- `requests==2.31.0`
- `pytest==7.4.0` (testing)

---

## Approval Criteria

✅ All 4 KPIs passed
✅ Code review completed
✅ Unit test coverage > 80%
✅ Documentation updated
✅ No critical bugs in Testnet

**Sign-off Required By:** Client Stakeholder
**Next Milestone Start:** Upon written approval

---

## Notes & Assumptions

1. **Testnet Limitations:** Binance Testnet may have limited liquidity. Some LIMIT orders may not fill immediately.
2. **API Key Permissions:** Ensure API key has "Enable Trading" permission for Futures.
3. **Time Synchronization:** System clock must be within 1 second of Binance server time (use NTP).
4. **Windows Compatibility:** WebSocket client tested on Windows, Linux, and macOS.

---

**Milestone Owner:** [Lead Developer]
**Status:** Not Started
**Last Updated:** 2025-10-02
