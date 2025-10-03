"""
Integration tests for BinanceGateway against real Binance Testnet.

These tests require valid Testnet API credentials in config.json.
Run with: pytest tests/integration/ -m integration
"""

import pytest
import asyncio
import json
from pathlib import Path
from decimal import Decimal

from src.exchange.binance_gateway import BinanceGateway
from src.exchange.gateway import OrderSide, OrderType, TimeInForce, PositionMode
from src.exchange.models import OrderStatus
from src.exchange.exceptions import InvalidOrderError


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


async def ensure_position_mode(gateway, mode: PositionMode):
    """Helper to ensure position mode is set correctly."""
    try:
        current_mode = await gateway.get_position_mode()
        if current_mode != mode:
            await gateway.set_position_mode(mode)
            await asyncio.sleep(1)  # Wait for mode change to propagate
    except Exception as e:
        if "position" in str(e).lower():
            pytest.skip(f"Cannot set {mode.value} mode: {str(e)}")
        raise


async def ensure_one_way_mode(gateway):
    """Helper to ensure position mode is ONE_WAY for order tests."""
    await ensure_position_mode(gateway, PositionMode.ONE_WAY)


async def ensure_hedge_mode(gateway):
    """Helper to ensure position mode is HEDGE for order tests."""
    await ensure_position_mode(gateway, PositionMode.HEDGE)


async def submit_market_order_and_wait(
    gateway,
    symbol: str,
    side: OrderSide,
    quantity: float,
    position_side: str = None,
    max_wait_seconds: int = 2
):
    """
    Submit a market order and wait for it to fill.

    Args:
        gateway: Gateway instance
        symbol: Trading symbol
        side: Order side (BUY/SELL)
        quantity: Order quantity
        position_side: Position side for HEDGE mode (LONG/SHORT)
        max_wait_seconds: Maximum time to wait for fill

    Returns:
        Filled Order object
    """
    kwargs = {}
    if position_side:
        kwargs['positionSide'] = position_side

    order = await gateway.submit_order(
        symbol=symbol,
        side=side,
        order_type=OrderType.MARKET,
        quantity=quantity,
        **kwargs
    )

    # Market orders may take a moment to fill on Testnet
    if order.status != OrderStatus.FILLED:
        await asyncio.sleep(max_wait_seconds)
        order = await gateway.get_order_status(symbol, order_id=order.order_id)

    return order


def round_to_precision(value: float, step_size: Decimal) -> float:
    """Round value to exchange precision based on step size."""
    # Convert step size to decimal places
    step_str = str(step_size).rstrip('0')
    if '.' in step_str:
        decimals = len(step_str.split('.')[1])
    else:
        decimals = 0
    return round(value, decimals)


# ============================================================================
# Connection Tests
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_testnet_connection(gateway):
    """Test connection to Binance Testnet."""
    assert gateway.is_connected is True


# ============================================================================
# Market Data Tests
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_exchange_info_integration(gateway):
    """Test getting exchange info from Testnet."""
    info = await gateway.get_exchange_info("BTC/USDT")

    assert info is not None
    assert info['symbol'] == 'BTCUSDT'
    assert 'filters' in info


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_symbol_info_integration(gateway):
    """Test getting normalized symbol info from Testnet."""
    symbol_info = await gateway.get_symbol_info("BTC/USDT")

    assert symbol_info.symbol == "BTC/USDT"
    assert symbol_info.base_asset == "BTC"
    assert symbol_info.quote_asset == "USDT"
    assert symbol_info.is_futures is True
    assert symbol_info.is_trading is True

    # Verify trading constraints exist
    assert symbol_info.min_quantity > 0
    assert symbol_info.min_price > 0
    assert symbol_info.price_step > 0
    assert symbol_info.quantity_step > 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_ohlc_data_integration(gateway):
    """Test getting OHLC data from Testnet."""
    candles = await gateway.get_ohlc_data(
        symbol="BTC/USDT",
        interval="1h",
        limit=10
    )

    assert len(candles) <= 10
    assert all(c.symbol == "BTC/USDT" for c in candles)
    assert all(c.interval == "1h" for c in candles)

    # Verify OHLC relationships
    for candle in candles:
        assert candle.high >= max(candle.open, candle.close)
        assert candle.low <= min(candle.open, candle.close)
        assert candle.volume >= 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_ticker_24hr_integration(gateway):
    """Test getting 24hr ticker from Testnet."""
    ticker = await gateway.get_ticker_24hr("BTC/USDT")

    assert ticker.symbol == "BTC/USDT"
    assert ticker.last_price > 0
    assert ticker.bid_price > 0
    assert ticker.ask_price > 0
    assert ticker.bid_price < ticker.ask_price  # Bid must be less than ask


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_order_book_integration(gateway):
    """Test getting order book from Testnet."""
    order_book = await gateway.get_order_book("BTC/USDT", limit=20)

    assert order_book.symbol == "BTC/USDT"
    assert len(order_book.bids) > 0
    assert len(order_book.asks) > 0

    # Verify spread is positive
    assert order_book.best_bid < order_book.best_ask
    assert order_book.spread > 0

    # Verify bid/ask ordering
    for i in range(len(order_book.bids) - 1):
        assert order_book.bids[i][0] >= order_book.bids[i + 1][0]  # Descending

    for i in range(len(order_book.asks) - 1):
        assert order_book.asks[i][0] <= order_book.asks[i + 1][0]  # Ascending


# ============================================================================
# Account Tests
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_account_balance_integration(gateway):
    """Test getting account balance from Testnet."""
    balances = await gateway.get_account_balance()

    assert isinstance(balances, list)

    # Verify balance structure
    for balance in balances:
        assert balance.asset is not None
        assert balance.free >= 0
        assert balance.locked >= 0
        assert balance.total == balance.free + balance.locked


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_positions_integration(gateway):
    """Test getting positions from Testnet."""
    positions = await gateway.get_positions()

    assert isinstance(positions, list)

    # Verify position structure
    for position in positions:
        assert position.symbol is not None
        assert position.quantity > 0
        assert position.leverage > 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_set_leverage_integration(gateway):
    """Test setting leverage on Testnet."""
    result = await gateway.set_leverage("BTC/USDT", 5)

    assert result is not None
    assert 'leverage' in result


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_position_mode_integration(gateway):
    """Test getting position mode from Testnet."""
    mode = await gateway.get_position_mode()

    assert mode in (PositionMode.ONE_WAY, PositionMode.HEDGE)
    assert isinstance(mode, PositionMode)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_set_position_mode_integration(gateway):
    """Test setting position mode on Testnet."""
    current_mode = await gateway.get_position_mode()

    # Try to set to ONE_WAY mode
    try:
        result = await gateway.set_position_mode(PositionMode.ONE_WAY)
        assert result is not None

        # Verify it was set
        new_mode = await gateway.get_position_mode()
        assert new_mode == PositionMode.ONE_WAY

    except Exception as e:
        # Expected if positions are open or mode already set
        if "No need to change" in str(e) or "position" in str(e).lower():
            pytest.skip(f"Cannot change position mode: {str(e)}")
        raise


# ============================================================================
# Order Tests
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_place_limit_order_integration(gateway):
    """
    Test placing a LIMIT order on Testnet.

    Places order at 5% below market to avoid immediate fill.
    """
    await ensure_one_way_mode(gateway)

    # Get symbol constraints and market price
    symbol_info = await gateway.get_symbol_info("BTC/USDT")
    ticker = await gateway.get_ticker_24hr("BTC/USDT")

    market_price = float(ticker.last_price)

    # Order 5% below market
    order_price = round_to_precision(market_price * 0.95, symbol_info.price_step)

    # Use fixed small quantity (adjust if needed for min_notional)
    quantity = round_to_precision(0.002, symbol_info.quantity_step)

    order = await gateway.submit_order(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=quantity,
        price=order_price,
        time_in_force=TimeInForce.GTC
    )

    try:
        # Verify order was placed
        assert order.order_id is not None
        assert order.symbol == "BTC/USDT"
        assert order.side == "BUY"
        assert order.order_type == "LIMIT"
        assert order.status in (OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED)

        # Verify order appears in open orders
        open_orders = await gateway.get_open_orders("BTC/USDT")
        order_ids = [o.order_id for o in open_orders]
        assert order.order_id in order_ids

        # Verify can query order status
        order_status = await gateway.get_order_status("BTC/USDT", order_id=order.order_id)
        assert order_status.order_id == order.order_id

    finally:
        # Cleanup: Cancel order if still open
        try:
            if order.status in (OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED):
                await gateway.cancel_order("BTC/USDT", order_id=order.order_id)
        except Exception:
            pass  # Order may already be filled/canceled


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_place_and_cancel_multiple_orders(gateway):
    """
    Test placing multiple LIMIT orders and canceling them.

    KPI 1.3: Order modification & cancellation
    """
    await ensure_one_way_mode(gateway)

    # Get symbol constraints and market price
    symbol_info = await gateway.get_symbol_info("BTC/USDT")
    ticker = await gateway.get_ticker_24hr("BTC/USDT")
    market_price = float(ticker.last_price)

    orders = []

    try:
        # Place 3 LIMIT orders at different price levels
        for i in range(3):
            order_price = round_to_precision(
                market_price * (0.95 - i * 0.01),  # 95%, 94%, 93% of market
                symbol_info.price_step
            )
            quantity = round_to_precision(0.002, symbol_info.quantity_step)

            order = await gateway.submit_order(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=quantity,
                price=order_price,
                time_in_force=TimeInForce.GTC
            )

            orders.append(order)
            assert order.status == OrderStatus.NEW
            await asyncio.sleep(0.2)  # Small delay between orders

        # Verify all orders are open
        open_orders = await gateway.get_open_orders("BTC/USDT")
        open_order_ids = {o.order_id for o in open_orders}

        for order in orders:
            assert order.order_id in open_order_ids

        # Cancel all orders
        for order in orders:
            result = await gateway.cancel_order("BTC/USDT", order_id=order.order_id)
            assert result is not None

        # Wait for cancellations to propagate
        await asyncio.sleep(1)

        # Verify orders are canceled
        open_orders = await gateway.get_open_orders("BTC/USDT")
        remaining_ids = {o.order_id for o in open_orders}

        for order in orders:
            assert order.order_id not in remaining_ids

    finally:
        # Cleanup: Ensure all orders are canceled
        for order in orders:
            try:
                await gateway.cancel_order("BTC/USDT", order_id=order.order_id)
            except Exception:
                pass  # Already canceled


# ============================================================================
# Error Handling Tests
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_invalid_symbol_error(gateway):
    """Test error handling for invalid symbol."""
    with pytest.raises(Exception):
        await gateway.get_symbol_info("INVALID/SYMBOL")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_order_validation_errors(gateway):
    """Test order validation errors."""
    # Missing price for LIMIT order
    with pytest.raises(InvalidOrderError):
        await gateway.submit_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.001
            # Missing required price parameter
        )


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_kpi_1_2_hedge_mode_market_orders(gateway):
    """
    KPI 1.2: Place 5 market orders (3 long, 2 short) in HEDGE mode.

    WARNING: This executes REAL market orders on Testnet with HEDGE position mode.
    """
    await ensure_hedge_mode(gateway)

    symbol_info = await gateway.get_symbol_info("BTC/USDT")
    min_qty = float(symbol_info.min_quantity)

    long_orders = []
    short_orders = []

    try:
        # Place 3 LONG market orders (positionSide=LONG)
        for _ in range(3):
            order = await submit_market_order_and_wait(
                gateway,
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                quantity=min_qty,
                position_side="LONG"
            )
            long_orders.append(order)
            assert order.status == OrderStatus.FILLED
            await asyncio.sleep(0.5)

        # Place 2 SHORT market orders (positionSide=SHORT)
        for _ in range(2):
            order = await submit_market_order_and_wait(
                gateway,
                symbol="BTC/USDT",
                side=OrderSide.SELL,
                quantity=min_qty,
                position_side="SHORT"
            )
            short_orders.append(order)
            assert order.status == OrderStatus.FILLED
            await asyncio.sleep(0.5)

        # Verify all filled
        assert len(long_orders) == 3
        assert len(short_orders) == 2
        assert all(o.status == OrderStatus.FILLED for o in long_orders + short_orders)

        # Close all LONG positions (SELL with positionSide=LONG)
        for _ in range(3):
            close_order = await submit_market_order_and_wait(
                gateway,
                symbol="BTC/USDT",
                side=OrderSide.SELL,
                quantity=min_qty,
                position_side="LONG"
            )
            assert close_order.status == OrderStatus.FILLED
            await asyncio.sleep(0.5)

        # Close all SHORT positions (BUY with positionSide=SHORT)
        for _ in range(2):
            close_order = await submit_market_order_and_wait(
                gateway,
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                quantity=min_qty,
                position_side="SHORT"
            )
            assert close_order.status == OrderStatus.FILLED
            await asyncio.sleep(0.5)

    except Exception as e:
        pytest.fail(f"KPI 1.2 HEDGE mode failed: {str(e)}")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_multiple_symbols_support(gateway):
    """Test that gateway works with multiple symbols."""
    symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]

    for symbol in symbols:
        # Get symbol info
        info = await gateway.get_symbol_info(symbol)
        assert info.symbol == symbol
        assert info.is_trading is True

        # Get ticker
        ticker = await gateway.get_ticker_24hr(symbol)
        assert ticker.symbol == symbol
        assert ticker.last_price > 0

        await asyncio.sleep(0.2)  # Rate limit delay


# ============================================================================
# KPI Validation Tests (Manual execution only)
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_kpi_1_2_place_five_market_orders(gateway):
    """
    KPI 1.2: Place 5 market orders (3 long, 2 short) in ONE_WAY mode.

    WARNING: This executes REAL market orders on Testnet.
    """
    await ensure_one_way_mode(gateway)

    symbol_info = await gateway.get_symbol_info("BTC/USDT")
    min_qty = float(symbol_info.min_quantity)

    orders = []

    try:
        # Place 3 LONG market orders
        for _ in range(3):
            order = await submit_market_order_and_wait(
                gateway,
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                quantity=min_qty
            )
            orders.append(order)
            assert order.status == OrderStatus.FILLED
            await asyncio.sleep(0.5)

        # Place 2 SHORT market orders
        for _ in range(2):
            order = await submit_market_order_and_wait(
                gateway,
                symbol="BTC/USDT",
                side=OrderSide.SELL,
                quantity=min_qty
            )
            orders.append(order)
            assert order.status == OrderStatus.FILLED
            await asyncio.sleep(0.5)

        # Verify all filled
        assert len(orders) == 5
        assert all(o.status == OrderStatus.FILLED for o in orders)

        # Close remaining position
        remaining = await submit_market_order_and_wait(
            gateway,
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            quantity=min_qty
        )
        assert remaining.status == OrderStatus.FILLED

    except Exception as e:
        pytest.fail(f"KPI 1.2 failed: {str(e)}")
