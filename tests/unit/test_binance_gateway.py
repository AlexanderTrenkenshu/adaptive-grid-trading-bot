"""
Unit tests for BinanceGateway implementation.

These tests use mocked Binance API responses to test the gateway logic
without making actual API calls.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
from decimal import Decimal

from src.exchange.binance_gateway import BinanceGateway
from src.exchange.gateway import OrderSide, OrderType, TimeInForce, PositionMode
from src.exchange.models import OrderStatus, PositionSide
from src.exchange.exceptions import (
    TransientError,
    PermanentError,
    InvalidOrderError,
    RateLimitError
)
from binance.exceptions import BinanceAPIException


@pytest.fixture
def mock_binance_client():
    """Create mock Binance client."""
    with patch('src.exchange.binance_gateway.Client') as mock_client_class:
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        yield mock_client


@pytest.fixture
async def gateway(mock_binance_client):
    """Create BinanceGateway instance with mocked client."""
    gateway = BinanceGateway(
        api_key="test_key",
        api_secret="test_secret",
        testnet=True
    )

    # Mock connect to initialize client
    mock_binance_client.get_server_time.return_value = {'serverTime': 1234567890}
    await gateway.connect()

    return gateway


# ============================================================================
# Connection Tests
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.unit
async def test_gateway_initialization():
    """Test gateway initialization."""
    gateway = BinanceGateway("key", "secret", testnet=True)

    assert gateway.api_key == "key"
    assert gateway.api_secret == "secret"
    assert gateway.testnet is True
    assert gateway.is_connected is False


@pytest.mark.asyncio
@pytest.mark.unit
async def test_gateway_connection(mock_binance_client):
    """Test connection to Binance."""
    gateway = BinanceGateway("key", "secret", testnet=True)

    mock_binance_client.get_server_time.return_value = {'serverTime': 1234567890}

    await gateway.connect()

    assert gateway.is_connected is True
    mock_binance_client.get_server_time.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_gateway_disconnection(gateway):
    """Test disconnection from Binance."""
    assert gateway.is_connected is True

    await gateway.disconnect()

    assert gateway.is_connected is False


# ============================================================================
# Market Data Tests
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_exchange_info(gateway, mock_binance_client):
    """Test getting exchange information."""
    mock_binance_client.futures_exchange_info.return_value = {
        'symbols': [
            {
                'symbol': 'BTCUSDT',
                'baseAsset': 'BTC',
                'quoteAsset': 'USDT',
                'status': 'TRADING',
                'filters': []
            }
        ]
    }

    info = await gateway.get_exchange_info("BTC/USDT")

    assert info['symbol'] == 'BTCUSDT'
    assert info['baseAsset'] == 'BTC'
    assert info['quoteAsset'] == 'USDT'


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_symbol_info(gateway, mock_binance_client):
    """Test getting normalized symbol information."""
    mock_binance_client.futures_exchange_info.return_value = {
        'symbols': [
            {
                'symbol': 'BTCUSDT',
                'baseAsset': 'BTC',
                'quoteAsset': 'USDT',
                'status': 'TRADING',
                'filters': [
                    {
                        'filterType': 'LOT_SIZE',
                        'minQty': '0.001',
                        'maxQty': '1000',
                        'stepSize': '0.001'
                    },
                    {
                        'filterType': 'PRICE_FILTER',
                        'minPrice': '0.01',
                        'maxPrice': '1000000',
                        'tickSize': '0.01'
                    },
                    {
                        'filterType': 'MIN_NOTIONAL',
                        'notional': '10'
                    }
                ]
            }
        ]
    }

    symbol_info = await gateway.get_symbol_info("BTC/USDT")

    assert symbol_info.symbol == "BTC/USDT"
    assert symbol_info.base_asset == "BTC"
    assert symbol_info.quote_asset == "USDT"
    assert symbol_info.min_quantity == Decimal('0.001')
    assert symbol_info.min_price == Decimal('0.01')
    assert symbol_info.min_notional == Decimal('10')
    assert symbol_info.is_futures is True
    assert symbol_info.is_trading is True


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_ohlc_data(gateway, mock_binance_client):
    """Test getting OHLC candlestick data."""
    mock_binance_client.futures_klines.return_value = [
        [
            1640000000000,  # Open time
            '50000.00',     # Open
            '51000.00',     # High
            '49000.00',     # Low
            '50500.00',     # Close
            '100.5',        # Volume
            1640003599999,  # Close time
            '5050000.00',   # Quote volume
            1000,           # Number of trades
            '60.0',         # Taker buy base
            '3030000.00',   # Taker buy quote
            '0'             # Ignore
        ]
    ]

    candles = await gateway.get_ohlc_data("BTC/USDT", "1h", limit=1)

    assert len(candles) == 1
    assert candles[0].symbol == "BTC/USDT"
    assert candles[0].interval == "1h"
    assert candles[0].open == Decimal('50000.00')
    assert candles[0].high == Decimal('51000.00')
    assert candles[0].low == Decimal('49000.00')
    assert candles[0].close == Decimal('50500.00')
    assert candles[0].volume == Decimal('100.5')
    assert candles[0].trades == 1000


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_ticker_24hr(gateway, mock_binance_client):
    """Test getting 24hr ticker data."""
    mock_binance_client.futures_ticker.return_value = {
        'symbol': 'BTCUSDT',
        'lastPrice': '50000.00',
        'volume': '1000.5',
        'quoteVolume': '50000000.00',
        'priceChange': '500.00',
        'priceChangePercent': '1.01',
        'highPrice': '51000.00',
        'lowPrice': '49000.00',
        'closeTime': 1640000000000
    }

    mock_binance_client.futures_orderbook_ticker.return_value = {
        'symbol': 'BTCUSDT',
        'bidPrice': '49995.00',
        'askPrice': '50005.00'
    }

    ticker = await gateway.get_ticker_24hr("BTC/USDT")

    assert ticker.symbol == "BTC/USDT"
    assert ticker.last_price == Decimal('50000.00')
    assert ticker.bid_price == Decimal('49995.00')
    assert ticker.ask_price == Decimal('50005.00')
    assert ticker.volume_24h == Decimal('1000.5')
    assert ticker.price_change_pct_24h == Decimal('1.01')


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_order_book(gateway, mock_binance_client):
    """Test getting order book."""
    mock_binance_client.futures_order_book.return_value = {
        'bids': [
            ['49995.00', '1.5'],
            ['49990.00', '2.0']
        ],
        'asks': [
            ['50005.00', '1.2'],
            ['50010.00', '1.8']
        ]
    }

    order_book = await gateway.get_order_book("BTC/USDT", limit=10)

    assert order_book.symbol == "BTC/USDT"
    assert len(order_book.bids) == 2
    assert len(order_book.asks) == 2
    assert order_book.best_bid == Decimal('49995.00')
    assert order_book.best_ask == Decimal('50005.00')
    assert order_book.spread == Decimal('10.00')


# ============================================================================
# Account Tests
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_account_balance(gateway, mock_binance_client):
    """Test getting account balance."""
    mock_binance_client.futures_account.return_value = {
        'assets': [
            {
                'asset': 'USDT',
                'availableBalance': '10000.50',
                'initialMargin': '500.00'
            },
            {
                'asset': 'BTC',
                'availableBalance': '0.5',
                'initialMargin': '0.1'
            }
        ]
    }

    balances = await gateway.get_account_balance()

    assert len(balances) == 2
    assert balances[0].asset == 'USDT'
    assert balances[0].free == Decimal('10000.50')
    assert balances[0].locked == Decimal('500.00')
    assert balances[0].total == Decimal('10500.50')


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_positions(gateway, mock_binance_client):
    """Test getting futures positions."""
    mock_binance_client.futures_position_information.return_value = [
        {
            'symbol': 'BTCUSDT',
            'positionAmt': '0.5',
            'entryPrice': '50000.00',
            'markPrice': '51000.00',
            'unRealizedProfit': '500.00',
            'leverage': '5',
            'liquidationPrice': '45000.00'
        },
        {
            'symbol': 'ETHUSDT',
            'positionAmt': '-2.0',
            'entryPrice': '3000.00',
            'markPrice': '2950.00',
            'unRealizedProfit': '100.00',
            'leverage': '3',
            'liquidationPrice': '3200.00'
        },
        {
            'symbol': 'SOLUSDT',
            'positionAmt': '0',
            'entryPrice': '0',
            'markPrice': '100.00',
            'unRealizedProfit': '0',
            'leverage': '1',
            'liquidationPrice': '0'
        }
    ]

    positions = await gateway.get_positions()

    # Should only return non-zero positions
    assert len(positions) == 2

    # Long position
    assert positions[0].symbol == "BTC/USDT"
    assert positions[0].side == PositionSide.LONG
    assert positions[0].quantity == Decimal('0.5')
    assert positions[0].entry_price == Decimal('50000.00')
    assert positions[0].leverage == 5

    # Short position
    assert positions[1].symbol == "ETH/USDT"
    assert positions[1].side == PositionSide.SHORT
    assert positions[1].quantity == Decimal('2.0')


@pytest.mark.asyncio
@pytest.mark.unit
async def test_set_leverage(gateway, mock_binance_client):
    """Test setting leverage."""
    mock_binance_client.futures_change_leverage.return_value = {
        'symbol': 'BTCUSDT',
        'leverage': 5
    }

    result = await gateway.set_leverage("BTC/USDT", 5)

    assert result['leverage'] == 5
    mock_binance_client.futures_change_leverage.assert_called_once_with(
        symbol='BTCUSDT',
        leverage=5
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_position_mode(gateway, mock_binance_client):
    """Test getting position mode."""
    mock_binance_client.futures_get_position_mode.return_value = {
        'dualSidePosition': False
    }

    mode = await gateway.get_position_mode()

    assert mode == PositionMode.ONE_WAY
    mock_binance_client.futures_get_position_mode.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_position_mode_hedge(gateway, mock_binance_client):
    """Test getting position mode (hedge mode)."""
    mock_binance_client.futures_get_position_mode.return_value = {
        'dualSidePosition': True
    }

    mode = await gateway.get_position_mode()

    assert mode == PositionMode.HEDGE
    mock_binance_client.futures_get_position_mode.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_set_position_mode(gateway, mock_binance_client):
    """Test setting position mode to ONE_WAY."""
    mock_binance_client.futures_change_position_mode.return_value = {
        'code': 200,
        'msg': 'success'
    }

    result = await gateway.set_position_mode(PositionMode.ONE_WAY)

    assert result is not None
    mock_binance_client.futures_change_position_mode.assert_called_once_with(
        dualSidePosition=False
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_set_position_mode_hedge(gateway, mock_binance_client):
    """Test setting position mode to HEDGE."""
    mock_binance_client.futures_change_position_mode.return_value = {
        'code': 200,
        'msg': 'success'
    }

    result = await gateway.set_position_mode(PositionMode.HEDGE)

    assert result is not None
    mock_binance_client.futures_change_position_mode.assert_called_once_with(
        dualSidePosition=True
    )


# ============================================================================
# Order Tests
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.unit
async def test_submit_limit_order(gateway, mock_binance_client):
    """Test submitting a LIMIT order."""
    mock_binance_client.futures_create_order.return_value = {
        'orderId': 123456,
        'symbol': 'BTCUSDT',
        'status': 'NEW',
        'side': 'BUY',
        'type': 'LIMIT',
        'origQty': '0.1',
        'executedQty': '0',
        'price': '50000.00',
        'timeInForce': 'GTC',
        'time': 1640000000000,
        'updateTime': 1640000000000,
        'cumQuote': '0'
    }

    order = await gateway.submit_order(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=0.1,
        price=50000.00,
        time_in_force=TimeInForce.GTC
    )

    assert order.order_id == '123456'
    assert order.symbol == "BTC/USDT"
    assert order.side == 'BUY'
    assert order.order_type == 'LIMIT'
    assert order.status == OrderStatus.NEW
    assert order.quantity == Decimal('0.1')
    assert order.executed_qty == Decimal('0')
    assert order.price == Decimal('50000.00')


@pytest.mark.asyncio
@pytest.mark.unit
async def test_submit_market_order(gateway, mock_binance_client):
    """Test submitting a MARKET order."""
    mock_binance_client.futures_create_order.return_value = {
        'orderId': 123457,
        'symbol': 'BTCUSDT',
        'status': 'FILLED',
        'side': 'SELL',
        'type': 'MARKET',
        'origQty': '0.1',
        'executedQty': '0.1',
        'avgPrice': '50100.00',
        'time': 1640000000000,
        'updateTime': 1640000000000,
        'cumQuote': '5010.00'
    }

    order = await gateway.submit_order(
        symbol="BTC/USDT",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=0.1
    )

    assert order.order_id == '123457'
    assert order.status == OrderStatus.FILLED
    assert order.executed_qty == Decimal('0.1')
    assert order.avg_price == Decimal('50100.00')


@pytest.mark.asyncio
@pytest.mark.unit
async def test_cancel_order(gateway, mock_binance_client):
    """Test canceling an order."""
    mock_binance_client.futures_cancel_order.return_value = {
        'orderId': 123456,
        'status': 'CANCELED'
    }

    result = await gateway.cancel_order("BTC/USDT", order_id="123456")

    assert result['status'] == 'CANCELED'
    mock_binance_client.futures_cancel_order.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_open_orders(gateway, mock_binance_client):
    """Test getting open orders."""
    mock_binance_client.futures_get_open_orders.return_value = [
        {
            'orderId': 123456,
            'symbol': 'BTCUSDT',
            'status': 'NEW',
            'side': 'BUY',
            'type': 'LIMIT',
            'origQty': '0.1',
            'executedQty': '0',
            'price': '50000.00',
            'time': 1640000000000,
            'updateTime': 1640000000000,
            'cumQuote': '0'
        }
    ]

    orders = await gateway.get_open_orders("BTC/USDT")

    assert len(orders) == 1
    assert orders[0].order_id == '123456'
    assert orders[0].status == OrderStatus.NEW


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_order_status(gateway, mock_binance_client):
    """Test getting order status."""
    mock_binance_client.futures_get_order.return_value = {
        'orderId': 123456,
        'symbol': 'BTCUSDT',
        'status': 'PARTIALLY_FILLED',
        'side': 'BUY',
        'type': 'LIMIT',
        'origQty': '0.1',
        'executedQty': '0.05',
        'price': '50000.00',
        'avgPrice': '50000.00',
        'time': 1640000000000,
        'updateTime': 1640000000000,
        'cumQuote': '2500.00'
    }

    order = await gateway.get_order_status("BTC/USDT", order_id="123456")

    assert order.status == OrderStatus.PARTIALLY_FILLED
    assert order.executed_qty == Decimal('0.05')
    assert order.remaining_qty == Decimal('0.05')
    assert order.fill_percentage == 50.0


# ============================================================================
# Error Handling Tests
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.unit
async def test_transient_error_mapping(gateway, mock_binance_client):
    """Test mapping of transient errors."""
    # Create proper mock response for BinanceAPIException
    mock_response = Mock()
    mock_response.text = '{"code": -1001, "msg": "Internal error"}'
    mock_response.status_code = 500

    error = BinanceAPIException(mock_response, -1001, "Internal error")
    # Manually set code attribute to ensure correct value
    error.code = -1001

    mock_binance_client.futures_exchange_info.side_effect = error

    with pytest.raises(TransientError) as exc_info:
        await gateway.get_exchange_info()

    assert "transient" in str(exc_info.value).lower()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_permanent_error_mapping(gateway, mock_binance_client):
    """Test mapping of permanent errors."""
    # Create proper mock response for BinanceAPIException
    mock_response = Mock()
    mock_response.text = '{"code": -1100, "msg": "Invalid parameter"}'
    mock_response.status_code = 400

    error = BinanceAPIException(mock_response, -1100, "Invalid parameter")
    # Manually set code attribute to ensure correct value
    error.code = -1100

    mock_binance_client.futures_create_order.side_effect = error

    with pytest.raises(PermanentError) as exc_info:
        await gateway.submit_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.1,
            price=50000.00
        )

    assert "permanent" in str(exc_info.value).lower()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_rate_limit_error_mapping(gateway, mock_binance_client):
    """Test mapping of rate limit errors."""
    # Create proper mock response for BinanceAPIException
    mock_response = Mock()
    mock_response.text = '{"code": -1003, "msg": "Too many requests"}'
    mock_response.status_code = 429

    error = BinanceAPIException(mock_response, -1003, "Too many requests")
    # Manually set code attribute to ensure correct value
    error.code = -1003

    mock_binance_client.futures_exchange_info.side_effect = error

    with pytest.raises(RateLimitError) as exc_info:
        await gateway.get_exchange_info()

    assert "rate limit" in str(exc_info.value).lower()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_invalid_order_error(gateway, mock_binance_client):
    """Test invalid order error (missing price for LIMIT)."""
    with pytest.raises(InvalidOrderError) as exc_info:
        await gateway.submit_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.1
            # Missing price!
        )

    assert "price required" in str(exc_info.value).lower()
