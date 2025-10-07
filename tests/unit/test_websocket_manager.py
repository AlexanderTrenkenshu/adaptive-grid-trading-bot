"""
Unit tests for WebSocket Manager.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
from decimal import Decimal

from src.exchange.websocket_manager import WebSocketManager
from src.exchange.exchange_config import BINANCE_CONFIG
from src.exchange.models import Candle, Trade, Ticker, Order


@pytest.fixture
def ws_manager():
    """Create WebSocket manager instance."""
    return WebSocketManager(BINANCE_CONFIG, testnet=True)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_websocket_manager_initialization(ws_manager):
    """Test WebSocket manager initialization."""
    assert ws_manager.config == BINANCE_CONFIG
    assert ws_manager.testnet is True
    assert ws_manager.is_connected is False
    assert len(ws_manager._market_subscriptions) == 0


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_ws_url_single_stream(ws_manager):
    """Test WebSocket URL generation for single stream."""
    url = ws_manager._get_ws_url()
    assert "wss://" in url or "ws://" in url
    assert "/ws" in url


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_ws_url_combined_streams(ws_manager):
    """Test WebSocket URL generation for combined streams."""
    streams = ["btcusdt@kline_1m", "ethusdt@trade"]
    url = ws_manager._get_ws_url(streams)

    assert "wss://" in url or "ws://" in url
    assert "streams=" in url
    assert "btcusdt@kline_1m" in url
    assert "ethusdt@trade" in url


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_user_data_url(ws_manager):
    """Test user data WebSocket URL generation."""
    listen_key = "test_listen_key_12345"
    url = ws_manager._get_user_data_url(listen_key)

    assert "wss://" in url or "ws://" in url
    assert listen_key in url


@pytest.mark.asyncio
@pytest.mark.unit
async def test_subscribe_kline(ws_manager):
    """Test subscribing to kline stream."""
    callback = Mock()

    await ws_manager.subscribe_kline("BTCUSDT", "1m", callback)

    assert "btcusdt@kline_1m" in ws_manager._market_subscriptions
    assert ws_manager._market_subscriptions["btcusdt@kline_1m"] == callback


@pytest.mark.asyncio
@pytest.mark.unit
async def test_subscribe_trade(ws_manager):
    """Test subscribing to trade stream."""
    callback = Mock()

    await ws_manager.subscribe_trade("BTCUSDT", callback)

    assert "btcusdt@trade" in ws_manager._market_subscriptions
    assert ws_manager._market_subscriptions["btcusdt@trade"] == callback


@pytest.mark.asyncio
@pytest.mark.unit
async def test_subscribe_book_ticker(ws_manager):
    """Test subscribing to book ticker stream."""
    callback = Mock()

    await ws_manager.subscribe_book_ticker("BTCUSDT", callback)

    assert "btcusdt@bookTicker" in ws_manager._market_subscriptions
    assert ws_manager._market_subscriptions["btcusdt@bookTicker"] == callback


@pytest.mark.asyncio
@pytest.mark.unit
async def test_subscribe_user_data(ws_manager):
    """Test subscribing to user data stream."""
    callback = Mock()
    listen_key = "test_listen_key"

    await ws_manager.subscribe_user_data(listen_key, callback)

    assert ws_manager._listen_key == listen_key
    assert ws_manager._user_callback == callback


@pytest.mark.asyncio
@pytest.mark.unit
async def test_unsubscribe(ws_manager):
    """Test unsubscribing from a stream."""
    callback = Mock()

    await ws_manager.subscribe_kline("BTCUSDT", "1m", callback)
    assert "btcusdt@kline_1m" in ws_manager._market_subscriptions

    await ws_manager.unsubscribe("btcusdt@kline_1m")
    assert "btcusdt@kline_1m" not in ws_manager._market_subscriptions


@pytest.mark.asyncio
@pytest.mark.unit
async def test_unsubscribe_all(ws_manager):
    """Test unsubscribing from all streams."""
    callback = Mock()

    await ws_manager.subscribe_kline("BTCUSDT", "1m", callback)
    await ws_manager.subscribe_trade("ETHUSDT", callback)
    await ws_manager.subscribe_user_data("test_key", callback)

    assert len(ws_manager._market_subscriptions) == 2
    assert ws_manager._listen_key is not None

    await ws_manager.unsubscribe_all()

    assert len(ws_manager._market_subscriptions) == 0
    assert ws_manager._listen_key is None
    assert ws_manager._user_callback is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_handle_market_message_combined_streams(ws_manager):
    """Test handling market message from combined streams."""
    callback = Mock()
    await ws_manager.subscribe_kline("BTCUSDT", "1m", callback)

    # Simulate combined streams format with CLOSED candle (x: true)
    message = json.dumps({
        "stream": "btcusdt@kline_1m",
        "data": {
            "e": "kline",
            "s": "BTCUSDT",
            "k": {
                "t": 1234567890000,
                "T": 1234567949999,
                "i": "1m",
                "o": "50000.0",
                "h": "50100.0",
                "l": "49900.0",
                "c": "50050.0",
                "v": "100.5",
                "x": True  # CLOSED candle
            }
        }
    })

    await ws_manager._handle_market_message(message)

    # Verify callback was called with Candle object
    callback.assert_called_once()
    call_args = callback.call_args[0][0]

    # Verify it's a Candle object
    assert isinstance(call_args, Candle)
    assert call_args.symbol == "BTC/USDT"  # Normalized
    assert call_args.interval == "1m"
    assert call_args.open == Decimal("50000.0")
    assert call_args.high == Decimal("50100.0")
    assert call_args.low == Decimal("49900.0")
    assert call_args.close == Decimal("50050.0")
    assert call_args.volume == Decimal("100.5")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_handle_market_message_open_candle_filtered(ws_manager):
    """Test that open candles (x: false) are filtered out."""
    callback = Mock()
    await ws_manager.subscribe_kline("BTCUSDT", "1m", callback)

    # Simulate OPEN candle (x: false)
    message = json.dumps({
        "stream": "btcusdt@kline_1m",
        "data": {
            "e": "kline",
            "s": "BTCUSDT",
            "k": {
                "t": 1234567890000,
                "T": 1234567949999,
                "i": "1m",
                "o": "50000.0",
                "h": "50100.0",
                "l": "49900.0",
                "c": "50050.0",
                "v": "100.5",
                "x": False  # OPEN candle - should be filtered out
            }
        }
    })

    await ws_manager._handle_market_message(message)

    # Verify callback was NOT called (open candles are filtered)
    callback.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_handle_market_message_async_callback(ws_manager):
    """Test handling market message with async callback."""
    callback = AsyncMock()
    await ws_manager.subscribe_trade("BTCUSDT", callback)

    message = json.dumps({
        "stream": "btcusdt@trade",
        "data": {
            "e": "trade",
            "s": "BTCUSDT",
            "p": "50000.0",
            "q": "1.5",
            "T": 1234567890000
        }
    })

    await ws_manager._handle_market_message(message)

    # Verify async callback was awaited with Trade object
    callback.assert_awaited_once()
    call_args = callback.call_args[0][0]
    assert isinstance(call_args, Trade)
    assert call_args.symbol == "BTC/USDT"
    assert call_args.price == Decimal("50000.0")
    assert call_args.quantity == Decimal("1.5")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_handle_user_message(ws_manager):
    """Test handling user data message."""
    callback = Mock()
    await ws_manager.subscribe_user_data("test_key", callback)

    message = json.dumps({
        "e": "ORDER_TRADE_UPDATE",
        "E": 1234567890000,
        "T": 1234567890000,
        "o": {
            "s": "BTCUSDT",
            "c": "client_order_123",
            "S": "BUY",
            "o": "LIMIT",
            "q": "0.001",
            "p": "50000.0",
            "X": "NEW",
            "i": 12345,
            "ap": "0",
            "n": "0",
            "N": "USDT"
        }
    })

    await ws_manager._handle_user_message(message)

    # Verify callback was called with Order object
    callback.assert_called_once()
    call_args = callback.call_args[0][0]
    assert isinstance(call_args, Order)
    assert call_args.symbol == "BTC/USDT"
    assert call_args.side == "BUY"
    assert call_args.order_type == "LIMIT"
    assert call_args.status == "NEW"
    assert call_args.quantity == Decimal("0.001")
    assert call_args.price == Decimal("50000.0")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_stats(ws_manager):
    """Test WebSocket statistics."""
    stats = ws_manager.stats

    assert 'messages_received' in stats
    assert 'reconnections' in stats
    assert 'last_message_time' in stats
    assert 'connected_at' in stats

    assert stats['messages_received'] == 0
    assert stats['reconnections'] == 0


@pytest.mark.asyncio
@pytest.mark.unit
async def test_connect_disconnect(ws_manager):
    """Test WebSocket connect and disconnect."""
    # Add a subscription to trigger connection
    callback = Mock()
    await ws_manager.subscribe_kline("BTCUSDT", "1m", callback)

    # Note: We can't fully test connection without a real WebSocket server
    # Just verify the manager state changes
    assert ws_manager._running is False

    await ws_manager.connect()
    assert ws_manager._running is True

    await ws_manager.disconnect()
    assert ws_manager._running is False
    assert ws_manager.is_connected is False


@pytest.mark.asyncio
@pytest.mark.unit
async def test_callback_error_handling(ws_manager):
    """Test that callback errors don't crash the WebSocket."""
    # Create a callback that raises an exception
    def failing_callback(data):
        raise ValueError("Test error")

    await ws_manager.subscribe_kline("BTCUSDT", "1m", failing_callback)

    message = json.dumps({
        "stream": "btcusdt@kline_1m",
        "data": {"e": "kline", "s": "BTCUSDT"}
    })

    # Should not raise exception
    await ws_manager._handle_market_message(message)

    # Stats should still be updated
    assert ws_manager.stats['messages_received'] == 1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_invalid_json_handling(ws_manager):
    """Test handling of invalid JSON messages."""
    callback = Mock()
    await ws_manager.subscribe_kline("BTCUSDT", "1m", callback)

    # Invalid JSON
    invalid_message = "{ invalid json"

    # Should not raise exception
    await ws_manager._handle_market_message(invalid_message)

    # Callback should not be called
    callback.assert_not_called()
