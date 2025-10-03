"""
Unit tests for ExchangeGateway abstract base class.
"""

import pytest
from src.exchange.gateway import ExchangeGateway, OrderSide, OrderType, TimeInForce, PositionMode


class MockExchangeGateway(ExchangeGateway):
    """Mock implementation for testing."""

    async def get_exchange_info(self, symbol=None):
        return {"symbol": symbol or "BTCUSDT", "filters": []}

    async def get_ohlc_data(self, symbol, interval, start_time=None, end_time=None, limit=500):
        return []

    async def get_ticker_24hr(self, symbol):
        return {"symbol": symbol, "lastPrice": "50000.0"}

    async def get_order_book(self, symbol, limit=100):
        return {"bids": [], "asks": []}

    async def get_account_balance(self):
        return {"balances": []}

    async def get_positions(self):
        return []

    async def set_leverage(self, symbol, leverage):
        return {"symbol": symbol, "leverage": leverage}

    async def get_position_mode(self):
        return PositionMode.ONE_WAY

    async def set_position_mode(self, mode):
        return {"dualSidePosition": mode == PositionMode.HEDGE}

    async def submit_order(self, symbol, side, order_type, quantity, price=None,
                          time_in_force=TimeInForce.GTC, stop_price=None,
                          client_order_id=None, **kwargs):
        return {"orderId": 12345, "symbol": symbol, "status": "NEW"}

    async def modify_order(self, symbol, order_id, quantity=None, price=None, **kwargs):
        return {"orderId": order_id, "symbol": symbol}

    async def cancel_order(self, symbol, order_id=None, client_order_id=None):
        return {"orderId": order_id or 12345, "status": "CANCELED"}

    async def get_open_orders(self, symbol=None):
        return []

    async def get_order_status(self, symbol, order_id=None, client_order_id=None):
        return {"orderId": order_id, "status": "FILLED"}

    async def subscribe_kline(self, symbol, interval, callback):
        pass

    async def subscribe_trade(self, symbol, callback):
        pass

    async def subscribe_book_ticker(self, symbol, callback):
        pass

    async def subscribe_user_data(self, callback):
        pass

    async def unsubscribe_all(self):
        pass

    async def connect(self):
        self._is_connected = True

    async def disconnect(self):
        self._is_connected = False


@pytest.mark.asyncio
async def test_gateway_initialization():
    """Test gateway initialization."""
    gateway = MockExchangeGateway(
        api_key="test_key",
        api_secret="test_secret",
        testnet=True
    )

    assert gateway.api_key == "test_key"
    assert gateway.api_secret == "test_secret"
    assert gateway.testnet is True
    assert gateway.is_connected is False


@pytest.mark.asyncio
async def test_gateway_connection():
    """Test connection management."""
    gateway = MockExchangeGateway("key", "secret", testnet=True)

    assert not gateway.is_connected

    await gateway.connect()
    assert gateway.is_connected

    await gateway.disconnect()
    assert not gateway.is_connected


@pytest.mark.asyncio
async def test_get_exchange_info():
    """Test getting exchange information."""
    gateway = MockExchangeGateway("key", "secret", testnet=True)

    info = await gateway.get_exchange_info("BTCUSDT")
    assert info["symbol"] == "BTCUSDT"
    assert "filters" in info


@pytest.mark.asyncio
async def test_submit_order():
    """Test order submission."""
    gateway = MockExchangeGateway("key", "secret", testnet=True)

    order = await gateway.submit_order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=0.1,
        price=50000.0
    )

    assert "orderId" in order
    assert order["symbol"] == "BTCUSDT"
    assert order["status"] == "NEW"


@pytest.mark.asyncio
async def test_cancel_order():
    """Test order cancellation."""
    gateway = MockExchangeGateway("key", "secret", testnet=True)

    result = await gateway.cancel_order("BTCUSDT", order_id=12345)
    assert result["status"] == "CANCELED"


@pytest.mark.asyncio
async def test_order_enums():
    """Test order-related enumerations."""
    assert OrderSide.BUY.value == "BUY"
    assert OrderSide.SELL.value == "SELL"

    assert OrderType.LIMIT.value == "LIMIT"
    assert OrderType.MARKET.value == "MARKET"

    assert TimeInForce.GTC.value == "GTC"
    assert TimeInForce.IOC.value == "IOC"
    assert TimeInForce.FOK.value == "FOK"
