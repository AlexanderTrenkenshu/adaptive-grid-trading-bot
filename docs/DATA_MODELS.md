# Data Models Documentation

This document describes the normalized data models used throughout the bot for both REST API and WebSocket data.

## Design Principles

1. **Unified Models**: Same data structures for REST API and WebSocket streams
2. **Minimal & Essential**: Only fields necessary for trading decisions
3. **Exchange-Agnostic**: Models work across different exchanges (Binance, Bybit, OKX, etc.)
4. **Type Safety**: All prices/quantities use `Decimal` for precision

---

## Market Data Models

### Candle (OHLCV)

Candlestick data for technical analysis.

**Fields:**
- `symbol`: str - Trading pair (e.g., "BTC/USDT")
- `interval`: str - Timeframe ("1m", "5m", "15m", "1h", "4h", "1d")
- `open_time`: datetime - Candle open timestamp
- `close_time`: datetime - Candle close timestamp
- `open`: Decimal - Open price
- `high`: Decimal - High price
- `low`: Decimal - Low price
- `close`: Decimal - Close price
- `volume`: Decimal - Base asset volume

**Usage:**
```python
# From REST API
candles = await gateway.get_ohlc_data("BTC/USDT", "1h", limit=100)

# From WebSocket (closed candles only)
def on_candle(candle: Candle):
    print(f"Closed 1m candle: {candle.close}")

await gateway.subscribe_kline("BTC/USDT", "1m", on_candle)
```

**Notes:**
- WebSocket streams emit **only closed candles** (when `x: true` in raw data)
- A 1-minute candle arrives **once per minute** when the candle closes
- No partial/incomplete candles are emitted

---

### Trade

Individual trade execution (tick data).

**Fields:**
- `symbol`: str - Trading pair
- `price`: Decimal - Trade price
- `quantity`: Decimal - Trade quantity
- `time`: datetime - Trade timestamp

**Usage:**
```python
# From WebSocket only (real-time trades)
def on_trade(trade: Trade):
    print(f"Trade: {trade.quantity} @ {trade.price}")

await gateway.subscribe_trade("BTC/USDT", on_trade)
```

**Notes:**
- Very high frequency on liquid pairs (hundreds per second for BTC/USDT)
- Use for real-time price updates and volume analysis

---

### Ticker

Best bid/ask prices (order book top).

**Fields:**
- `symbol`: str - Trading pair
- `last_price`: Decimal - Last trade price
- `bid_price`: Decimal - Best bid price
- `ask_price`: Decimal - Best ask price
- `bid_qty`: Decimal - Quantity at best bid
- `ask_qty`: Decimal - Quantity at best ask
- `timestamp`: datetime - Update timestamp

**Usage:**
```python
# From REST API
ticker = await gateway.get_ticker_24hr("BTC/USDT")
print(f"Bid: {ticker.bid_price}, Ask: {ticker.ask_price}")

# From WebSocket (real-time updates)
def on_ticker(ticker: Ticker):
    spread = ticker.ask_price - ticker.bid_price
    print(f"Spread: {spread}")

await gateway.subscribe_book_ticker("BTC/USDT", on_ticker)
```

---

## Order Models

### Order

Order placement and execution tracking.

**Fields:**
- `order_id`: str - Exchange order ID
- `client_order_id`: str - Client-provided order ID
- `symbol`: str - Trading pair
- `side`: str - "BUY" or "SELL"
- `order_type`: str - "LIMIT" or "MARKET"
- `status`: str - "NEW", "FILLED", "CANCELED", "REJECTED"
- `quantity`: Decimal - Order quantity
- `price`: Optional[Decimal] - Limit price (None for MARKET orders)
- `average_fill_price`: Decimal - Average execution price (0 if not filled)
- `commission`: Decimal - Trading fee paid
- `commission_asset`: str - Fee currency (e.g., "USDT")

**Order Type Behavior:**

#### MARKET Orders
```python
order = Order(
    order_id="12345",
    client_order_id="my_order_1",
    symbol="BTC/USDT",
    side="BUY",
    order_type="MARKET",
    status="FILLED",
    quantity=Decimal("0.001"),
    price=None,                              # ← No limit price
    average_fill_price=Decimal("50000.5"),   # ← Actual fill price
    commission=Decimal("0.05"),
    commission_asset="USDT"
)
```

**Key Points:**
- `price` is **None** for MARKET orders
- `average_fill_price` contains the actual execution price
- Usually fills immediately at current market price

#### LIMIT Orders
```python
# When placing order
order = Order(
    order_id="12346",
    client_order_id="my_limit_1",
    symbol="BTC/USDT",
    side="BUY",
    order_type="LIMIT",
    status="NEW",
    quantity=Decimal("0.001"),
    price=Decimal("49000.0"),                # ← Limit price we set
    average_fill_price=Decimal("0"),         # ← Not filled yet
    commission=Decimal("0"),
    commission_asset="USDT"
)

# After order fills
order.status = "FILLED"
order.average_fill_price = Decimal("49000.0")  # ← Actual fill price
order.commission = Decimal("0.049")
```

**Key Points:**
- `price` is the **limit price** we specify when placing the order
- `average_fill_price` is **0** until order starts filling
- Once filled, `average_fill_price` contains the actual execution price
- For high-liquidity markets, `average_fill_price` usually equals `price`

**Usage:**
```python
# Place MARKET order
order = await gateway.submit_order(
    symbol="BTC/USDT",
    side=OrderSide.BUY,
    order_type=OrderType.MARKET,
    quantity=0.001
)
print(f"Filled at: {order.average_fill_price}")

# Place LIMIT order
order = await gateway.submit_order(
    symbol="BTC/USDT",
    side=OrderSide.BUY,
    order_type=OrderType.LIMIT,
    quantity=0.001,
    price=49000.0
)
print(f"Limit order placed at: {order.price}")

# WebSocket order updates
def on_order_update(order: Order):
    if order.status == "FILLED":
        print(f"Order {order.order_id} filled at {order.average_fill_price}")
    elif order.status == "CANCELED":
        print(f"Order {order.order_id} canceled")

await gateway.subscribe_user_data(on_order_update)
```

---

## Account Models

### REST API Models

#### Balance (REST API)

Account balance from REST API endpoint.

**Fields:**
- `asset`: str - Asset symbol (e.g., "USDT", "BTC")
- `free`: Decimal - Available balance
- `locked`: Decimal - Balance locked in orders
- `total`: Decimal - Total balance (free + locked)

**Usage:**
```python
# From REST API only
balances = await gateway.get_account_balance()
for balance in balances:
    if balance.asset == "USDT":
        print(f"USDT: {balance.free} free, {balance.locked} locked")
```

---

#### Position (REST API)

Open position from REST API endpoint.

**Fields:**
- `symbol`: str - Trading pair
- `side`: PositionSide - Position side (LONG/SHORT/BOTH)
- `quantity`: Decimal - Position size (absolute value)
- `entry_price`: Decimal - Average entry price
- `mark_price`: Decimal - Current mark price
- `unrealized_pnl`: Decimal - Unrealized profit/loss
- `leverage`: int - Leverage multiplier
- `liquidation_price`: Optional[Decimal] - Liquidation price
- `margin`: Optional[Decimal] - Position margin

**Usage:**
```python
# From REST API only
positions = await gateway.get_positions()
for pos in positions:
    if pos.quantity > 0:
        print(f"{pos.symbol}: {pos.quantity} @ {pos.entry_price}")
        print(f"PnL: {pos.unrealized_pnl}, Leverage: {pos.leverage}x")
```

---

### WebSocket Models

#### AccountBalance (WebSocket)

Balance data from WebSocket account updates.

**Fields:**
- `asset`: str - Asset symbol
- `wallet_balance`: Decimal - Total wallet balance
- `cross_wallet_balance`: Decimal - Cross margin balance (Futures)

**Usage:**
```python
# From WebSocket account updates only
def on_account_update(update: AccountUpdate):
    for balance in update.balances:
        print(f"{balance.asset}: {balance.wallet_balance}")
```

**Note:** Different from REST `Balance` model - WebSocket provides wallet balance, not free/locked breakdown.

---

#### AccountPosition (WebSocket)

Position data from WebSocket account updates.

**Fields:**
- `symbol`: str - Trading pair
- `position_amount`: Decimal - Position size (negative for short)
- `entry_price`: Decimal - Average entry price
- `unrealized_pnl`: Decimal - Unrealized profit/loss
- `position_side`: str - "BOTH", "LONG", or "SHORT"

**Usage:**
```python
# From WebSocket account updates only
def on_account_update(update: AccountUpdate):
    for position in update.positions:
        if position.position_amount != 0:
            print(f"{position.symbol} PnL: {position.unrealized_pnl}")
```

**Note:** Different from REST `Position` model - WebSocket provides signed amount (negative for short), not absolute quantity with side.

---

#### AccountUpdate (WebSocket)

Complete account state update from WebSocket.

**Fields:**
- `event_time`: datetime - Event timestamp
- `transaction_time`: datetime - Transaction timestamp
- `balances`: List[AccountBalance] - Updated balances
- `positions`: List[AccountPosition] - Updated positions
- `reason`: str - Update reason (e.g., "ORDER", "FUNDING_FEE")

**Usage:**
```python
def on_account_update(update: AccountUpdate):
    print(f"Account update at {update.event_time}")
    print(f"Reason: {update.reason}")

    # Check balances
    for balance in update.balances:
        if balance.asset == "USDT":
            print(f"USDT balance: {balance.wallet_balance}")

    # Check positions
    for position in update.positions:
        if position.position_amount != 0:
            print(f"{position.symbol}: {position.unrealized_pnl} PnL")

await gateway.subscribe_user_data(on_account_update)
```

---

## Model Comparison: REST vs WebSocket

### Why Different Models?

Exchanges send different data structures for REST API vs WebSocket:

**Balance:**
- REST: Provides `free` and `locked` breakdown
- WebSocket: Provides only `wallet_balance` total

**Position:**
- REST: Provides `side` (enum) and `quantity` (absolute), plus `leverage`, `mark_price`
- WebSocket: Provides `position_amount` (signed: negative for short), minimal fields

This design maintains accuracy to what exchanges actually send.

---

## Data Flow Examples

### Real-Time Trading Flow

```python
# 1. Subscribe to market data
def on_kline(candle: Candle):
    """Receive closed 1m candles once per minute"""
    if should_enter_trade(candle):
        place_order(candle.close)

await gateway.subscribe_kline("BTC/USDT", "1m", on_kline)

# 2. Subscribe to order updates
def on_order_update(order: Order):
    """Receive order status updates"""
    if order.status == "FILLED":
        print(f"Order filled at {order.average_fill_price}")
        print(f"Commission: {order.commission} {order.commission_asset}")

await gateway.subscribe_user_data(on_order_update)

# 3. Place order
order = await gateway.submit_order(
    symbol="BTC/USDT",
    side=OrderSide.BUY,
    order_type=OrderType.LIMIT,
    quantity=0.001,
    price=50000.0  # Limit price
)

# 4. Monitor execution
# WebSocket will call on_order_update when order fills
```

---

## Important Notes

### Partial Fills

**Design Decision:** For high-liquidity markets (BTC/USDT, ETH/USDT), we assume orders fill completely or not at all.

- MARKET orders: Fill immediately at current price
- LIMIT orders: Either fill completely at limit price or remain open

The simplified `Order` model focuses on:
- `average_fill_price` for filled orders
- No tracking of partial fills (not needed for liquid markets)

### WebSocket Data Filtering

**Kline streams:** Only closed candles are emitted
- Raw WebSocket sends updates every second while candle is forming
- Our parser **filters** and only emits when candle closes (`x: true`)
- Result: One `Candle` object per interval (e.g., once per minute for "1m")

**Order updates:** All status changes are emitted
- NEW → order accepted
- FILLED → order executed
- CANCELED → order canceled
- REJECTED → order rejected by exchange

### Price Precision

All price and quantity fields use `Decimal` for exact precision:
```python
# ✓ Correct
price = Decimal("50000.12345678")

# ✗ Avoid (float rounding errors)
price = 50000.12345678
```

---

## Migration Guide

If you're updating existing code:

### Old Ticker → New Ticker
```python
# Old (had many 24h fields)
ticker.volume_24h
ticker.price_change_24h
ticker.high_24h

# New (minimal, essential)
ticker.bid_price
ticker.ask_price
ticker.bid_qty
ticker.ask_qty
```

### Old Candle → New Candle
```python
# Old (had extra fields)
candle.quote_volume
candle.trades
candle.taker_buy_base_volume

# New (minimal, essential)
# Only: open, high, low, close, volume
candle.volume  # Base asset volume only
```

### Old Order → New Order
```python
# Old (complex, many fields)
order.executed_qty
order.remaining_qty
order.cumulative_quote_qty
order.stop_price

# New (focused on filled orders)
order.quantity               # Original quantity
order.price                  # Limit price (None for MARKET)
order.average_fill_price     # Actual fill price
order.commission             # Fee paid
```

---

## Questions?

If you need additional fields or have questions about model usage, refer to:
- Source code: `src/exchange/models.py`
- Tests: `tests/unit/test_binance_gateway.py`
- Integration tests: `tests/integration/test_binance_integration.py`
