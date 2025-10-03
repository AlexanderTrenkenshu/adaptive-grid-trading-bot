# Milestone 3: Logging, Graceful Shutdown & Testnet Validation

**Duration:** 1 week (40 hours)
**Cost:** $2,000
**Objective:** Deliver production-grade logging, safe shutdown protocol, and validate entire Execution Engine

---

## Day-by-Day Breakdown

### Day 21: Structured JSON Logging System
**Hours:** 8h
**Tasks:**
- [ ] Design log event schema
  ```python
  class LogEvent:
      timestamp: str  # ISO 8601 format
      event_type: str  # TRADE_CLOSED, STATUS, ORDER_PLACED, etc.
      data: dict      # Event-specific payload
  ```
- [ ] Implement JSON log formatter
  ```python
  class JSONFormatter(logging.Formatter):
      def format(self, record):
          log_obj = {
              "timestamp": datetime.utcnow().isoformat() + "Z",
              "event_type": record.event_type,
              "level": record.levelname,
              **record.data
          }
          return json.dumps(log_obj)
  ```
- [ ] Configure daily rotating log files
  - Pattern: `logs/bot_YYYY-MM-DD.log`
  - Rotation at midnight UTC
  - Keep last 30 days
- [ ] Implement event loggers for core events:
  - `TRADE_CLOSED`
  - `STATUS`
  - `ORDER_PLACED`
  - `SHUTDOWN_INITIATED`
  - `SHUTDOWN_COMPLETE`
  - `STATE_RECOVERED`

**Deliverables:**
- `src/logging/event_logger.py`
- `src/logging/json_formatter.py`
- Log rotation configuration

**Testing:**
```python
# Test log output format
logger.log_trade_closed(trade)
# Expected output:
# {"timestamp": "2025-10-26T10:05:22.123Z", "event_type": "TRADE_CLOSED", ...}
```

---

### Day 22: Event Logger Implementation
**Hours:** 8h
**Tasks:**
- [ ] **TRADE_CLOSED Event Logger**
  ```python
  def log_trade_closed(trade: Trade):
      """
      Logs when a position is fully closed.
      Spec: Section 3.7, Example 1
      """
      log_event({
          "timestamp": datetime.utcnow().isoformat() + "Z",
          "event_type": "TRADE_CLOSED",
          "symbol": trade.symbol,
          "side": trade.side,
          "entry_time": trade.entry_time.isoformat() + "Z",
          "entry_price": trade.entry_price,
          "quantity": trade.quantity,
          "exit_time": trade.exit_time.isoformat() + "Z",
          "exit_price": trade.exit_price,
          "exit_reason": trade.exit_reason,  # "TP", "SL", "MANUAL"
          "realized_pnl": trade.realized_pnl,
          "fee_paid": trade.fee_paid,
          "funding_paid": trade.funding_paid
      })
  ```

- [ ] **STATUS Event Logger**
  ```python
  def log_status(portfolio_state: dict):
      """
      Logs bot status periodically (every 5 min) and on-demand.
      Spec: Section 3.7, Example 2
      """
      log_event({
          "timestamp": datetime.utcnow().isoformat() + "Z",
          "event_type": "STATUS",
          "bot_uptime": portfolio_state.uptime_seconds,
          "performance": {
              "realized_pnl": portfolio_state.realized_pnl,
              "unrealized_pnl": portfolio_state.unrealized_pnl,
              "total_fees_paid": portfolio_state.total_fees,
              "total_funding_paid": portfolio_state.total_funding
          },
          "equity": portfolio_state.equity,
          "bot_position": portfolio_state.internal_positions,
          "exchange_position": portfolio_state.exchange_positions
      })
  ```

- [ ] **ORDER_PLACED Event Logger**
  ```python
  def log_order_placed(order: Order, strategy_context: dict):
      """
      Logs every order placement with strategy context.
      Spec: Section 3.7, Example 3
      """
      log_event({
          "timestamp": datetime.utcnow().isoformat() + "Z",
          "event_type": "ORDER_PLACED",
          "symbol": order.symbol,
          "order_id": order.order_id,
          "side": order.side,
          "type": order.type,
          "quantity": order.quantity,
          "price": order.price,
          "strategy_context": {
              "long_conviction": strategy_context.get("long_conviction"),
              "short_conviction": strategy_context.get("short_conviction"),
              "calculated_atr": strategy_context.get("calculated_atr"),
              "calculated_long_spacing": strategy_context.get("long_spacing"),
              "calculated_order_size": strategy_context.get("order_size"),
              "current_imbalance": strategy_context.get("imbalance")
          }
      })
  ```

- [ ] Integrate with existing modules
  - Hook into PnL Engine (TRADE_CLOSED)
  - Hook into OMS (ORDER_PLACED)
  - Create periodic STATUS task (every 5 minutes)

**Deliverables:**
- Complete event logging functions
- Integration points in OMS and PnL modules
- Periodic status logger (background thread)

**Testing:**
```python
# Verify log format matches spec exactly
with open('logs/bot_2025-10-26.log', 'r') as f:
    logs = [json.loads(line) for line in f]
    assert logs[0]['event_type'] in ['TRADE_CLOSED', 'STATUS', 'ORDER_PLACED']
```

---

### Day 23: Graceful Shutdown Implementation
**Hours:** 8h
**Tasks:**
- [ ] Signal handler for SIGINT (Ctrl+C)
  ```python
  import signal

  class TradingBot:
      def __init__(self):
          self.shutdown_requested = False
          signal.signal(signal.SIGINT, self._handle_shutdown)

      def _handle_shutdown(self, signum, frame):
          logger.info("Shutdown signal received (Ctrl+C)")
          self.shutdown_requested = True
  ```

- [ ] Shutdown sequence implementation (Spec: Section 4)
  1. **Log Shutdown Initiated**
     ```python
     log_event({
         "timestamp": datetime.utcnow().isoformat() + "Z",
         "event_type": "SHUTDOWN_INITIATED"
     })
     ```

  2. **Halt Trading**
     - Set `trading_enabled = False` flag
     - Strategy stops generating new signals
     - No new orders placed

  3. **Cancel All Open Limit Orders**
     ```python
     open_orders = oms.get_all_open_orders()
     for order in open_orders:
         try:
             oms.cancel_order(order.symbol, order.order_id)
             logger.info(f"Canceled order {order.order_id}")
         except Exception as e:
             logger.error(f"Failed to cancel {order.order_id}: {e}")
     ```

  4. **Close All Open Positions (Market Orders)**
     ```python
     open_positions = pnl_engine.get_open_positions()
     for position in open_positions:
         try:
             close_order = oms.submit_market_order(
                 symbol=position.symbol,
                 side="SELL" if position.size > 0 else "BUY",
                 quantity=abs(position.size)
             )
             logger.info(f"Closing position {position.symbol}")
         except Exception as e:
             logger.error(f"Failed to close {position.symbol}: {e}")

     # Wait for fills (max 30 seconds)
     timeout = 30
     start = time.time()
     while time.time() - start < timeout:
         if len(pnl_engine.get_open_positions()) == 0:
             break
         time.sleep(1)
     ```

  5. **Final State Save**
     ```python
     db_manager.save_all_state(
         orders=oms.get_all_orders(),
         positions=pnl_engine.get_all_positions(),
         strategy_state=strategy.get_state()
     )
     ```

  6. **Log Shutdown Complete**
     ```python
     log_event({
         "timestamp": datetime.utcnow().isoformat() + "Z",
         "event_type": "SHUTDOWN_COMPLETE",
         "final_equity": portfolio.equity,
         "positions_closed": len(closed_positions),
         "orders_canceled": len(canceled_orders)
     })
     ```

  7. **Exit Cleanly**
     ```python
     sys.exit(0)
     ```

- [ ] Timeout protection
  - If shutdown takes > 30 seconds, force exit with warning
  - Log any positions that couldn't be closed

**Deliverables:**
- `src/shutdown_manager.py`
- Integration with main event loop
- Comprehensive shutdown logging

**Testing:**
```python
# KPI 3.2: Graceful shutdown test
# 1. Start bot
# 2. Open 2 positions (1 long, 1 short)
# 3. Place 5 limit orders
# 4. Press Ctrl+C
# Expected:
# - All 5 orders canceled
# - Both positions closed via market orders
# - Exit within 30 seconds
# - Logs show SHUTDOWN_INITIATED and SHUTDOWN_COMPLETE
```

---

### Day 24-25: 48-Hour Testnet Validation Run
**Hours:** 16h (8h setup + 8h monitoring/analysis)

#### Setup Phase (Day 24, 8h)
**Tasks:**
- [ ] Configure bot for automated 48-hour run
  ```json
  {
    "exchange": {
      "testnet": true,
      "market_type": "futures"
    },
    "symbols": ["BTCUSDT"],
    "portfolio": {
      "leverage_cap": 3.0,  // Conservative for test
      "weights": {"BTCUSDT": 1.0}
    },
    "engine": {
      "utilization": 0.2,  // Lower utilization for test
      "max_orders_per_symbol": 10,
      "base_leverage": 2
    }
  }
  ```

- [ ] Set up monitoring
  - Real-time log tail: `tail -f logs/bot_2025-10-26.log`
  - Database query script for positions
  - Binance Testnet UI for cross-reference

- [ ] Create automated health check script
  ```python
  # health_check.py - Run every 30 minutes via cron
  import subprocess
  import json

  # Check if process is running
  result = subprocess.run(['pgrep', '-f', 'main.py'], capture_output=True)
  if result.returncode != 0:
      send_alert("Bot process died!")

  # Check last log timestamp
  with open('logs/bot_2025-10-26.log', 'r') as f:
      last_line = f.readlines()[-1]
      last_log = json.loads(last_line)
      last_time = datetime.fromisoformat(last_log['timestamp'].replace('Z', ''))
      if (datetime.utcnow() - last_time).seconds > 300:
          send_alert("No logs in last 5 minutes!")
  ```

- [ ] Start 48-hour run
  ```bash
  nohup python src/main.py --config config/testnet_48h.json > run.log 2>&1 &
  echo $! > bot.pid
  ```

**Monitoring Phase (Days 24-25, ongoing)**
- [ ] Monitor every 4-6 hours
  - Check process is running
  - Review logs for errors
  - Verify orders being placed
  - Cross-check positions with Binance UI

- [ ] Collect metrics
  ```python
  # analyze_run.py
  import json

  with open('logs/bot_2025-10-26.log', 'r') as f:
      logs = [json.loads(line) for line in f]

  order_placed_count = len([l for l in logs if l['event_type'] == 'ORDER_PLACED'])
  trade_closed_count = len([l for l in logs if l['event_type'] == 'TRADE_CLOSED'])
  status_count = len([l for l in logs if l['event_type'] == 'STATUS'])

  print(f"ORDER_PLACED: {order_placed_count}")
  print(f"TRADE_CLOSED: {trade_closed_count}")
  print(f"STATUS: {status_count}")
  ```

**Deliverables:**
- Complete 48-hour log file
- Metrics report
- Any bugs discovered + fixes

---

### Day 25 (Afternoon): KPI Validation & Reporting
**Hours:** 8h
**Tasks:**
- [ ] **KPI 3.1 Validation: Log Content Analysis**
  ```bash
  # Count event types
  cat logs/bot_2025-10-26.log | jq -r '.event_type' | sort | uniq -c

  # Expected:
  # ≥10 ORDER_PLACED
  # ≥5 TRADE_CLOSED
  # ≥10 STATUS (should be ~576 for 48 hours @ 5min intervals)
  ```
  - [ ] Verify counts meet minimum thresholds
  - [ ] Check all events have required fields
  - [ ] Validate JSON format (no malformed lines)

- [ ] **KPI 3.2 Validation: Graceful Shutdown**
  - [ ] While bot is running, press Ctrl+C
  - [ ] Verify shutdown sequence:
    ```bash
    cat logs/bot_2025-10-26.log | grep "SHUTDOWN"
    # Should see:
    # {"event_type": "SHUTDOWN_INITIATED", ...}
    # ... [order cancellations] ...
    # ... [position closures] ...
    # {"event_type": "SHUTDOWN_COMPLETE", ...}
    ```
  - [ ] Check all positions closed (query Binance UI)
  - [ ] Verify exit code is 0
  - [ ] Confirm shutdown took < 30 seconds

- [ ] **KPI 3.3 Validation: STATUS Accuracy**
  ```python
  # Compare STATUS log with Binance UI
  status_log = [l for l in logs if l['event_type'] == 'STATUS'][-1]

  # Manually check Binance Testnet UI:
  # - Wallet balance
  # - Open positions
  # - Unrealized PnL

  # All values should match within rounding error
  assert abs(status_log['equity'] - binance_ui_equity) < 0.01
  ```

- [ ] **KPI 3.4 Validation: strategy_context in ORDER_PLACED**
  ```python
  order_logs = [l for l in logs if l['event_type'] == 'ORDER_PLACED']

  for order_log in order_logs:
      assert 'strategy_context' in order_log
      assert 'long_conviction' in order_log['strategy_context']
      assert 'calculated_atr' in order_log['strategy_context']
      assert 'calculated_order_size' in order_log['strategy_context']
  ```

- [ ] Generate validation report
  ```markdown
  # Milestone 3 KPI Validation Report

  ## KPI 3.1: Log Event Counts
  - ORDER_PLACED: 45 ✅ (≥10 required)
  - TRADE_CLOSED: 12 ✅ (≥5 required)
  - STATUS: 576 ✅ (≥10 required)

  ## KPI 3.2: Graceful Shutdown
  - Shutdown initiated: ✅
  - All orders canceled: ✅ (5 orders)
  - All positions closed: ✅ (2 positions)
  - Shutdown time: 18 seconds ✅ (<30s required)
  - Exit code: 0 ✅

  ## KPI 3.3: STATUS Accuracy
  - Equity match: ✅ (bot: $10,245.67, exchange: $10,245.66)
  - Position match: ✅
  - Unrealized PnL match: ✅

  ## KPI 3.4: strategy_context Present
  - All ORDER_PLACED events contain strategy_context: ✅
  - Required fields present: ✅

  ## Bugs Found
  1. [Bug #1]: WebSocket disconnected after 36 hours (auto-reconnected)
  2. [Bug #2]: Minor: Status log equity precision issue (fixed)

  ## Overall Assessment
  ✅ ALL KPIs PASSED
  Ready for Milestone 4
  ```

- [ ] Bug fix session (if any issues found)

**Deliverables:**
- KPI validation report
- 48-hour log file archive
- Bug fixes (if needed)
- Milestone 3 approval request

---

## Module Structure

```
src/
├── logging/
│   ├── __init__.py
│   ├── event_logger.py       # TRADE_CLOSED, STATUS, ORDER_PLACED loggers
│   ├── json_formatter.py     # JSON log formatting
│   └── log_config.py         # Rotation, file handling
├── shutdown_manager.py       # Graceful shutdown logic
└── main.py                   # Updated with shutdown handler

tests/
├── unit/
│   └── test_logging.py       # Log format validation
└── integration/
    └── test_shutdown.py      # End-to-end shutdown test

scripts/
├── health_check.py           # Monitoring script
└── analyze_logs.py           # Log analysis utilities
```

---

## Configuration (Milestone 3 Additions)

```json
{
  "logging": {
    "level": "INFO",           // DEBUG, INFO, WARNING, ERROR
    "path": "logs",            // Log directory
    "rotation": "daily",       // Rotation frequency
    "retention_days": 30       // Keep last 30 days
  },
  "monitoring": {
    "status_interval_seconds": 300,  // Log STATUS every 5 minutes
    "health_check_enabled": true
  }
}
```

---

## Testing Checklist

### Unit Tests
- [ ] JSON formatter produces valid JSON
- [ ] Event loggers include all required fields
- [ ] Log rotation triggers at midnight UTC
- [ ] Shutdown handler catches SIGINT

### Integration Tests
- [ ] ORDER_PLACED logged when order submitted
- [ ] TRADE_CLOSED logged when position fully closed
- [ ] STATUS logged every 5 minutes
- [ ] Shutdown sequence cancels orders and closes positions

### System Tests (48-Hour Run)
- [ ] Bot runs continuously for 48 hours
- [ ] ≥10 ORDER_PLACED events
- [ ] ≥5 TRADE_CLOSED events
- [ ] ≥10 STATUS events (should be ~576)
- [ ] No crashes or unhandled exceptions
- [ ] Graceful shutdown works within 30 seconds

### KPI Validation
- [ ] KPI 3.1: Log counts verified
- [ ] KPI 3.2: Shutdown closes all positions
- [ ] KPI 3.3: STATUS matches Binance UI
- [ ] KPI 3.4: strategy_context present

---

## Risk & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| 48-hour run crashes | Milestone delay | Health check script, auto-restart |
| Testnet API instability | Incomplete logs | Use spot market as fallback |
| Shutdown timeout (>30s) | KPI failure | Implement force-exit after 30s |
| Log file too large | Disk space | Compression, rotation, retention policy |

---

## Dependencies

**External:**
- Binance Testnet account funded with USDT
- Server/VM with 99%+ uptime for 48-hour run

**Libraries:**
- `logging` (stdlib) - Log rotation
- Existing modules from Milestones 1-2

---

## Approval Criteria

✅ All 4 KPIs passed
✅ 48-hour run completed without crashes
✅ Logs are valid JSON and parseable
✅ Graceful shutdown closes all positions
✅ STATUS accuracy verified against exchange

**Sign-off Required By:** Client Stakeholder
**Next Milestone Start:** Upon written approval

---

## Notes & Assumptions

1. **Log Volume:** Expect ~500KB - 2MB per day of logs (depends on trading activity)
2. **48-Hour Window:** Schedule run over weekend for more monitoring availability
3. **Testnet Limitations:** Testnet may have limited liquidity; focus on system stability, not trading performance
4. **Exit Code:** Always 0 for graceful shutdown, non-zero for errors

---

**Milestone Owner:** [Lead Developer]
**Status:** Not Started
**Last Updated:** 2025-10-02
