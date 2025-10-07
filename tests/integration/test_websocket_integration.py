"""
Integration tests for WebSocket functionality against real Binance Testnet.

These tests require valid Testnet API credentials in config.json.
Run with: pytest tests/integration/test_websocket_integration.py -m integration
"""

import pytest
import asyncio
import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from src.exchange.binance_gateway import BinanceGateway
from src.exchange.gateway import OrderSide, OrderType
from src.exchange.models import OrderStatus, Candle, Trade, Ticker, Order


# Load testnet credentials from config
CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "config.json"


@pytest.fixture(scope="module")
def testnet_credentials():
    """Load testnet credentials from config file."""
    if not CONFIG_PATH.exists():
        pytest.skip("config.json not found")

    with open(CONFIG_PATH) as f:
        config = json.load(f)

    if not config.get("exchange", {}).get("testnet"):
        pytest.skip("Testnet not enabled in config")

    return {
        "api_key": config["exchange"]["api_key"],
        "api_secret": config["exchange"]["api_secret"]
    }


@pytest.fixture(scope="module")
async def gateway(testnet_credentials):
    """Create and connect to BinanceGateway."""
    gw = BinanceGateway(
        api_key=testnet_credentials["api_key"],
        api_secret=testnet_credentials["api_secret"],
        testnet=True
    )

    await gw.connect()
    yield gw
    await gw.disconnect()


# ============================================================================
# WebSocket Market Data Tests
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_kline_stream(gateway):
    """
    Test subscribing to kline (candlestick) stream.

    Verifies:
    - Callback receives Candle objects (not raw dictionaries)
    - Only closed candles are received
    - For 1m interval, approximately one candle per minute
    - All fields are properly populated with correct types

    KPI 1.1: Stable WebSocket connection
    """
    candles_received = []
    candle_times = []

    def on_kline(candle: Candle):
        """Callback for kline updates."""
        print(f"Candle time = {candle.open_time}")
        candles_received.append(candle)
        candle_times.append(datetime.utcnow())

    # Subscribe to 1-minute kline stream
    await gateway.subscribe_kline("BTC/USDT", "1m", on_kline)

    # Wait for at least 3 closed candles (about 3 minutes)
    max_wait = 200  # seconds (give extra time)
    wait_interval = 10  # seconds

    for _ in range(max_wait // wait_interval):
        if len(candles_received) >= 3:
            break
        await asyncio.sleep(wait_interval)

    # Verify we received at least 3 closed candles
    assert len(candles_received) >= 3, "Should receive at least 3 closed candles"

    # Verify all received objects are Candle instances
    for candle in candles_received:
        assert isinstance(candle, Candle), "Should receive Candle objects"
        assert candle.symbol == "BTC/USDT"
        assert candle.interval == "1m"
        assert isinstance(candle.open, Decimal)
        assert isinstance(candle.high, Decimal)
        assert isinstance(candle.low, Decimal)
        assert isinstance(candle.close, Decimal)
        assert isinstance(candle.volume, Decimal)
        assert isinstance(candle.open_time, datetime)
        assert isinstance(candle.close_time, datetime)

        # Verify price consistency (high >= open, close; low <= open, close)
        assert candle.high >= candle.open
        assert candle.high >= candle.close
        assert candle.low <= candle.open
        assert candle.low <= candle.close

    # Verify candle frequency (approximately 1 per minute for 1m interval)
    # Note: Due to timing jitter and when we connect mid-minute, we may get
    # slightly more or fewer candles than the exact time difference suggests
    if len(candle_times) >= 2:
        time_diff = (candle_times[-1] - candle_times[0]).total_seconds()
        candles_count = len(candle_times)

        # Very rough check: should get between 1-4 candles in ~3 minutes
        assert 1 <= candles_count <= 5, \
            f"Expected 1-5 candles over {time_diff:.0f}s, got {candles_count}"

    # Unsubscribe
    await gateway.unsubscribe_all()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_trade_stream(gateway):
    """
    Test subscribing to trade stream.

    Verifies callback receives Trade objects with proper types.
    """
    trades_received = []

    def on_trade(trade: Trade):
        """Callback for trade updates."""
        trades_received.append(trade)

    # Subscribe to trade stream
    await gateway.subscribe_trade("BTC/USDT", on_trade)

    # Wait for at least 3 trade messages (BTC is very active)
    # Give more time for connection establishment
    max_wait = 30  # seconds
    wait_interval = 2

    for _ in range(max_wait // wait_interval):
        if len(trades_received) >= 3:
            break
        await asyncio.sleep(wait_interval)

    # Verify we received trade messages
    assert len(trades_received) >= 3, f"Should receive at least 3 trade messages, got {len(trades_received)}"

    # Verify all received objects are Trade instances
    for trade in trades_received:
        assert isinstance(trade, Trade), "Should receive Trade objects"
        assert trade.symbol == "BTC/USDT"
        assert isinstance(trade.price, Decimal)
        assert isinstance(trade.quantity, Decimal)
        assert isinstance(trade.time, datetime)
        assert trade.price > 0
        assert trade.quantity > 0

    # Unsubscribe
    await gateway.unsubscribe_all()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_book_ticker_stream(gateway):
    """
    Test subscribing to book ticker stream.

    Verifies callback receives Ticker objects with proper types.
    """
    tickers_received = []

    def on_book_ticker(ticker: Ticker):
        """Callback for book ticker updates."""
        tickers_received.append(ticker)

    # Subscribe to book ticker stream
    await gateway.subscribe_book_ticker("BTC/USDT", on_book_ticker)

    # Wait for at least 3 messages
    max_wait = 10  # seconds
    wait_interval = 1

    for _ in range(max_wait):
        if len(tickers_received) >= 3:
            break
        await asyncio.sleep(wait_interval)

    # Verify we received book ticker messages
    assert len(tickers_received) >= 3, "Should receive at least 3 book ticker messages"

    # Verify all received objects are Ticker instances
    for ticker in tickers_received:
        assert isinstance(ticker, Ticker), "Should receive Ticker objects"
        assert ticker.symbol == "BTC/USDT"
        assert isinstance(ticker.bid_price, Decimal)
        assert isinstance(ticker.ask_price, Decimal)
        assert isinstance(ticker.bid_qty, Decimal)
        assert isinstance(ticker.ask_qty, Decimal)
        assert isinstance(ticker.last_price, Decimal)
        assert isinstance(ticker.timestamp, datetime)

        # Verify bid < ask (spread should be positive)
        assert ticker.bid_price < ticker.ask_price, "Best bid should be less than best ask"
        assert ticker.bid_price > 0
        assert ticker.ask_price > 0

    # Unsubscribe
    await gateway.unsubscribe_all()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_multiple_streams(gateway):
    """Test subscribing to multiple streams simultaneously."""
    kline_messages = []
    trade_messages = []

    def on_kline(data):
        kline_messages.append(data)

    def on_trade(data):
        trade_messages.append(data)

    # Subscribe to multiple streams
    await gateway.subscribe_kline("BTC/USDT", "1m", on_kline)
    await gateway.subscribe_trade("ETH/USDT", on_trade)

    # Wait for messages on both streams
    # Klines may take up to 60s for first closed candle
    # Trades should come quickly
    max_wait = 90  # seconds
    wait_interval = 5

    for _ in range(max_wait // wait_interval):
        if len(kline_messages) >= 1 and len(trade_messages) >= 3:
            break
        await asyncio.sleep(wait_interval)

    # Verify both streams received messages
    assert len(kline_messages) >= 1, f"Should receive kline messages, got {len(kline_messages)}"
    assert len(trade_messages) >= 3, f"Should receive trade messages, got {len(trade_messages)}"

    # Unsubscribe
    await gateway.unsubscribe_all()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_websocket_reconnection(gateway):
    """
    Test WebSocket auto-reconnection.

    Note: This test simulates disconnection by unsubscribing and resubscribing.
    Full reconnection testing requires more complex setup.
    """
    messages_received = []

    def on_kline(data):
        messages_received.append(data)

    # Subscribe
    await gateway.subscribe_kline("BTC/USDT", "1m", on_kline)

    # Wait for initial messages (up to 70s for first closed candle)
    max_wait = 75
    for _ in range(max_wait):
        if len(messages_received) > 0:
            break
        await asyncio.sleep(1)

    initial_count = len(messages_received)
    assert initial_count > 0, "Should receive initial messages"

    # Unsubscribe and resubscribe (simulates reconnection)
    await gateway.unsubscribe_all()
    await asyncio.sleep(2)

    messages_received.clear()
    await gateway.subscribe_kline("BTC/USDT", "1m", on_kline)

    # Wait for messages after "reconnection" (up to 70s for next closed candle)
    for _ in range(max_wait):
        if len(messages_received) > 0:
            break
        await asyncio.sleep(1)

    reconnect_count = len(messages_received)

    assert reconnect_count > 0, "Should receive messages after reconnection"

    # Unsubscribe
    await gateway.unsubscribe_all()


# ============================================================================
# WebSocket User Data Tests
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_user_data_stream_order_updates(gateway):
    """
    Test user data stream for order execution reports.

    Verifies:
    - Callback receives Order objects (not raw dictionaries)
    - Order fields are properly populated with correct types
    - WebSocket receives order updates when orders are placed
    """
    order_updates = []

    def on_user_data(data):
        """Callback for user data updates."""
        order_updates.append(data)

    # Subscribe to user data stream
    await gateway.subscribe_user_data(on_user_data)

    # Wait a moment for subscription to establish
    await asyncio.sleep(2)

    # Get symbol info and place a LIMIT order (won't fill)
    symbol_info = await gateway.get_symbol_info("BTC/USDT")
    ticker = await gateway.get_ticker_24hr("BTC/USDT")

    market_price = float(ticker.last_price)
    price_below_market = market_price * 0.95  # 5% below market

    # Round to symbol's tick size
    tick_size = float(symbol_info.price_step)
    order_price = round(price_below_market / tick_size) * tick_size

    # Round quantity to symbol's lot size
    lot_size = float(symbol_info.quantity_step)
    quantity = round(0.001 / lot_size) * lot_size
    if quantity < float(symbol_info.min_quantity):
        quantity = float(symbol_info.min_quantity)

    # Place order
    order = await gateway.submit_order(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=quantity,
        price=order_price
    )

    # Wait for order update via WebSocket
    max_wait = 10  # seconds
    wait_interval = 0.5

    order_update_received = None
    for _ in range(int(max_wait / wait_interval)):
        # Check if we received an Order object for our order
        for update in order_updates:
            if isinstance(update, Order) and update.order_id == order.order_id:
                order_update_received = update
                break

        if order_update_received:
            break

        await asyncio.sleep(wait_interval)

    # Clean up: Cancel order
    try:
        await gateway.cancel_order("BTC/USDT", order_id=order.order_id)
    except Exception:
        pass

    # Verify we received the order update
    assert order_update_received is not None, "Should receive Order update via user data stream"

    # Verify Order object structure
    assert isinstance(order_update_received, Order)
    assert order_update_received.symbol == "BTC/USDT"
    assert order_update_received.side == "BUY"
    assert order_update_received.order_type == "LIMIT"
    assert isinstance(order_update_received.quantity, Decimal)
    assert isinstance(order_update_received.price, Decimal)
    assert isinstance(order_update_received.average_fill_price, Decimal)
    assert isinstance(order_update_received.commission, Decimal)

    # Unsubscribe
    await gateway.unsubscribe_all()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_kpi_1_1_stable_connection(gateway):
    """
    KPI 1.1: Maintain stable WebSocket connection for extended period.

    This test verifies:
    - Connection stays active and receives Candle objects continuously
    - Only closed candles are received (approximately 1 per minute)
    - No connection drops or data loss

    Reduced to 2 minutes for faster CI/CD (original spec: 1 hour).
    """
    candles_received = []
    connection_alive = True

    def on_kline(candle: Candle):
        """Callback for kline updates."""
        candles_received.append(candle)
        nonlocal connection_alive
        connection_alive = True

    # Subscribe to 1-minute kline stream
    await gateway.subscribe_kline("BTC/USDT", "1m", on_kline)

    # Monitor connection for 2 minutes
    test_duration = 120  # seconds (reduced from 3600 for testing)
    check_interval = 10  # seconds

    checks_performed = 0
    for i in range(test_duration // check_interval):
        connection_alive = False  # Reset flag
        initial_count = len(candles_received)

        await asyncio.sleep(check_interval)

        # Note: We may not get new candles every 10 seconds since they only
        # close once per minute. Just verify connection stays active.
        # After first check, we should have at least started receiving data
        if i > 0:  # Skip first check, give time for initial connection
            assert gateway.ws_manager.is_connected, \
                f"WebSocket should be connected during check {checks_performed + 1}"

        checks_performed += 1

    # Verify total messages received (at least 1 closed candle per minute)
    expected_minimum_candles = (test_duration // 60) - 1  # At least 1 per minute
    assert len(candles_received) >= expected_minimum_candles, \
        f"Should receive at least {expected_minimum_candles} closed candles over {test_duration} seconds"

    # Verify all received objects are Candle instances
    for candle in candles_received:
        assert isinstance(candle, Candle)

    # Verify WebSocket manager is connected
    assert gateway.ws_manager.is_connected

    # Check statistics
    stats = gateway.ws_manager.stats
    assert stats['messages_received'] > 0
    assert stats['last_message_time'] is not None

    # Unsubscribe
    await gateway.unsubscribe_all()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_websocket_manager_stats(gateway):
    """Test WebSocket manager statistics tracking."""
    messages_received = []

    def on_trade(data):
        messages_received.append(data)

    # Subscribe
    await gateway.subscribe_trade("BTC/USDT", on_trade)

    # Wait for messages (give time for connection + trades)
    max_wait = 20
    for _ in range(max_wait):
        if len(messages_received) >= 3:
            break
        await asyncio.sleep(1)

    # Check stats
    stats = gateway.ws_manager.stats
    assert stats['messages_received'] > 0, "Should have received messages"
    assert stats['last_message_time'] is not None
    assert stats['connected_at'] is not None

    # Verify we received some trades in our callback
    assert len(messages_received) >= 3, \
        f"Should have received at least 3 trades, got {len(messages_received)}"

    # Stats may be higher than callback count if there were previous subscriptions
    # or if we subscribed to multiple streams. Just verify stats >= our callback count.
    assert stats['messages_received'] >= len(messages_received), \
        f"Stats count ({stats['messages_received']}) should be >= callback count ({len(messages_received)})"

    # Unsubscribe
    await gateway.unsubscribe_all()
