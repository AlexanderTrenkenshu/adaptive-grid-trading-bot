"""
WebSocket Manager for Binance Futures.

Handles real-time market data and user data streams with:
- Auto-reconnection with exponential backoff
- Multi-stream subscription management
- ListenKey keep-alive for user data
- Event-driven callback system
"""

import asyncio
import json
import time
from typing import Dict, Callable, Optional, List, Any
from datetime import datetime
import structlog

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from .exceptions import WebSocketError, ConnectionError as ExchangeConnectionError
from .exchange_config import ExchangeConfig, ExchangeType
from .websocket_parser import WebSocketParser


logger = structlog.get_logger(__name__)


class WebSocketManager:
    """
    Manages WebSocket connections for market data and user data streams.

    Features:
    - Multiple concurrent stream subscriptions
    - Auto-reconnection with exponential backoff
    - Ping/pong heartbeat monitoring
    - ListenKey management for user data
    """

    # Reconnection parameters
    INITIAL_RECONNECT_DELAY = 1  # seconds
    MAX_RECONNECT_DELAY = 120  # seconds
    RECONNECT_BACKOFF_FACTOR = 2

    # Heartbeat parameters
    PING_INTERVAL = 60  # seconds (Binance requires ping every 3 minutes)
    PONG_TIMEOUT = 10  # seconds

    # ListenKey parameters
    LISTEN_KEY_REFRESH_INTERVAL = 1800  # 30 minutes (Binance expires after 60 minutes)

    def __init__(
        self,
        config: ExchangeConfig,
        testnet: bool = False
    ):
        """
        Initialize WebSocket manager.

        Args:
            config: Exchange configuration
            testnet: Whether to use testnet endpoints
        """
        self.config = config
        self.testnet = testnet

        # WebSocket parser
        self._parser = WebSocketParser(config.exchange_type)

        # WebSocket connections
        self._market_ws: Optional[websockets.WebSocketClientProtocol] = None
        self._user_ws: Optional[websockets.WebSocketClientProtocol] = None

        # Connection state
        self._is_connected = False
        self._is_reconnecting = False
        self._reconnect_delay = self.INITIAL_RECONNECT_DELAY

        # Subscriptions
        self._market_subscriptions: Dict[str, Callable] = {}  # stream_name -> callback
        self._user_callback: Optional[Callable] = None
        self._listen_key: Optional[str] = None

        # Background tasks
        self._tasks: List[asyncio.Task] = []
        self._running = False

        # Statistics
        self._stats = {
            'messages_received': 0,
            'reconnections': 0,
            'last_message_time': None,
            'connected_at': None
        }

        logger.info(
            "WebSocket manager initialized",
            testnet=testnet,
            base_url=config.websocket_testnet_url if testnet else config.websocket_base_url
        )

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._is_connected

    @property
    def stats(self) -> Dict[str, Any]:
        """Get connection statistics."""
        return self._stats.copy()

    def _get_ws_url(self, streams: List[str] = None) -> str:
        """
        Get WebSocket URL for market data.

        Args:
            streams: List of stream names (e.g., ["btcusdt@kline_1m", "btcusdt@trade"])

        Returns:
            WebSocket URL
        """
        base_url = (
            self.config.websocket_testnet_url if self.testnet
            else self.config.websocket_base_url
        )

        if streams:
            # Combined streams format: wss://stream.binance.com/stream?streams=btcusdt@trade/ethusdt@trade
            stream_str = '/'.join(streams)
            return f"{base_url}/stream?streams={stream_str}"
        else:
            # Single stream format: wss://stream.binance.com/ws
            return f"{base_url}/ws"

    def _get_user_data_url(self, listen_key: str) -> str:
        """
        Get WebSocket URL for user data stream.

        Args:
            listen_key: Listen key from Binance API

        Returns:
            WebSocket URL
        """
        base_url = (
            self.config.websocket_testnet_url if self.testnet
            else self.config.websocket_base_url
        )
        return f"{base_url}/ws/{listen_key}"

    async def connect(self):
        """Connect to WebSocket and start background tasks."""
        if self._running:
            logger.warning("WebSocket manager already running")
            return

        self._running = True
        self._stats['connected_at'] = datetime.utcnow()

        # Start market data connection if we have subscriptions
        if self._market_subscriptions:
            self._tasks.append(asyncio.create_task(self._market_data_loop()))

        # Start user data connection if we have a listen key
        if self._listen_key and self._user_callback:
            self._tasks.append(asyncio.create_task(self._user_data_loop()))
            self._tasks.append(asyncio.create_task(self._keep_alive_listen_key()))

        logger.info("WebSocket manager started")

    async def disconnect(self):
        """Disconnect from WebSocket and stop background tasks."""
        self._running = False

        # Cancel all background tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks.clear()

        # Close WebSocket connections
        if self._market_ws:
            await self._market_ws.close()
            self._market_ws = None

        if self._user_ws:
            await self._user_ws.close()
            self._user_ws = None

        self._is_connected = False

        logger.info("WebSocket manager stopped")

    async def subscribe_kline(
        self,
        symbol: str,
        interval: str,
        callback: Callable[[Dict], None]
    ):
        """
        Subscribe to kline (candlestick) data.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            interval: Kline interval (e.g., "1m", "15m", "1h", "1d")
            callback: Function to call with kline data
        """
        stream_name = f"{symbol.lower()}@kline_{interval}"
        self._market_subscriptions[stream_name] = callback

        logger.info("Subscribed to kline stream", symbol=symbol, interval=interval)

        # Restart market data loop to update subscriptions
        if self._running:
            await self._restart_market_data_loop()

    async def subscribe_trade(
        self,
        symbol: str,
        callback: Callable[[Dict], None]
    ):
        """
        Subscribe to trade data.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            callback: Function to call with trade data
        """
        stream_name = f"{symbol.lower()}@trade"
        self._market_subscriptions[stream_name] = callback

        logger.info("Subscribed to trade stream", symbol=symbol)

        if self._running:
            await self._restart_market_data_loop()

    async def subscribe_book_ticker(
        self,
        symbol: str,
        callback: Callable[[Dict], None]
    ):
        """
        Subscribe to book ticker (best bid/ask).

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            callback: Function to call with book ticker data
        """
        stream_name = f"{symbol.lower()}@bookTicker"
        self._market_subscriptions[stream_name] = callback

        logger.info("Subscribed to book ticker stream", symbol=symbol)

        if self._running:
            await self._restart_market_data_loop()

    async def subscribe_user_data(
        self,
        listen_key: str,
        callback: Callable[[Dict], None]
    ):
        """
        Subscribe to user data stream (order updates, balance changes).

        Args:
            listen_key: Listen key from Binance API
            callback: Function to call with user data
        """
        self._listen_key = listen_key
        self._user_callback = callback

        logger.info("Subscribed to user data stream")

        # Start user data loop if manager is running
        if self._running:
            self._tasks.append(asyncio.create_task(self._user_data_loop()))
            self._tasks.append(asyncio.create_task(self._keep_alive_listen_key()))

    async def unsubscribe(self, stream_name: str):
        """
        Unsubscribe from a stream.

        Args:
            stream_name: Stream name (e.g., "btcusdt@kline_1m")
        """
        if stream_name in self._market_subscriptions:
            del self._market_subscriptions[stream_name]
            logger.info("Unsubscribed from stream", stream=stream_name)

            if self._running:
                await self._restart_market_data_loop()

    async def unsubscribe_all(self):
        """Unsubscribe from all streams."""
        self._market_subscriptions.clear()
        self._user_callback = None
        self._listen_key = None

        logger.info("Unsubscribed from all streams")

    async def _restart_market_data_loop(self):
        """Restart market data loop to update subscriptions."""
        # Find and cancel existing market data task
        for task in self._tasks:
            if task.get_name() == "market_data_loop":
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                self._tasks.remove(task)
                break

        # Close existing connection
        if self._market_ws:
            await self._market_ws.close()
            self._market_ws = None

        # Start new market data loop
        if self._market_subscriptions:
            task = asyncio.create_task(self._market_data_loop())
            task.set_name("market_data_loop")
            self._tasks.append(task)

    async def _market_data_loop(self):
        """Main loop for market data WebSocket connection."""
        while self._running:
            try:
                streams = list(self._market_subscriptions.keys())
                if not streams:
                    logger.debug("No market subscriptions, stopping market data loop")
                    break

                url = self._get_ws_url(streams)

                logger.info("Connecting to market data WebSocket", url=url, streams=len(streams))

                async with websockets.connect(url) as ws:
                    self._market_ws = ws
                    self._is_connected = True
                    self._reconnect_delay = self.INITIAL_RECONNECT_DELAY

                    logger.info("Connected to market data WebSocket")

                    # Start ping task
                    ping_task = asyncio.create_task(self._ping_loop(ws))

                    try:
                        async for message in ws:
                            await self._handle_market_message(message)
                    finally:
                        ping_task.cancel()
                        try:
                            await ping_task
                        except asyncio.CancelledError:
                            pass

            except (ConnectionClosed, WebSocketException, OSError) as e:
                self._is_connected = False
                self._stats['reconnections'] += 1

                logger.warning(
                    "Market data WebSocket disconnected",
                    error=str(e),
                    reconnect_delay=self._reconnect_delay
                )

                if self._running:
                    await asyncio.sleep(self._reconnect_delay)
                    self._reconnect_delay = min(
                        self._reconnect_delay * self.RECONNECT_BACKOFF_FACTOR,
                        self.MAX_RECONNECT_DELAY
                    )

            except Exception as e:
                logger.error("Unexpected error in market data loop", error=str(e), exc_info=True)
                await asyncio.sleep(self._reconnect_delay)

    async def _user_data_loop(self):
        """Main loop for user data WebSocket connection."""
        while self._running and self._listen_key:
            try:
                url = self._get_user_data_url(self._listen_key)

                logger.info("Connecting to user data WebSocket")

                async with websockets.connect(url) as ws:
                    self._user_ws = ws

                    logger.info("Connected to user data WebSocket")

                    # Start ping task
                    ping_task = asyncio.create_task(self._ping_loop(ws))

                    try:
                        async for message in ws:
                            await self._handle_user_message(message)
                    finally:
                        ping_task.cancel()
                        try:
                            await ping_task
                        except asyncio.CancelledError:
                            pass

            except (ConnectionClosed, WebSocketException, OSError) as e:
                logger.warning("User data WebSocket disconnected", error=str(e))

                if self._running:
                    await asyncio.sleep(self._reconnect_delay)

            except Exception as e:
                logger.error("Unexpected error in user data loop", error=str(e), exc_info=True)
                await asyncio.sleep(self._reconnect_delay)

    async def _ping_loop(self, ws: websockets.WebSocketClientProtocol):
        """Send periodic pings to keep connection alive."""
        try:
            while True:
                await asyncio.sleep(self.PING_INTERVAL)

                try:
                    pong_waiter = await ws.ping()
                    await asyncio.wait_for(pong_waiter, timeout=self.PONG_TIMEOUT)
                    logger.debug("Ping/pong successful")
                except asyncio.TimeoutError:
                    logger.warning("Pong timeout, closing connection")
                    await ws.close()
                    break

        except asyncio.CancelledError:
            pass

    async def _keep_alive_listen_key(self):
        """Refresh listen key periodically to keep user data stream alive."""
        # Note: This requires access to the REST API client
        # In practice, this should call gateway.refresh_listen_key()
        while self._running and self._listen_key:
            await asyncio.sleep(self.LISTEN_KEY_REFRESH_INTERVAL)

            logger.debug("Listen key keep-alive (refresh should be done via REST API)")

    async def _handle_market_message(self, message: str):
        """
        Handle incoming market data message.

        Parses raw WebSocket data into typed models and invokes callbacks.

        Args:
            message: JSON message from WebSocket
        """
        try:
            data = json.loads(message)

            self._stats['messages_received'] += 1
            self._stats['last_message_time'] = datetime.utcnow()

            # Combined streams format: {"stream": "btcusdt@kline_1m", "data": {...}}
            if 'stream' in data:
                stream_name = data['stream']
                stream_data = data['data']
            else:
                # Single stream format
                stream_name = data.get('e')  # event type
                stream_data = data

            # Find matching callback
            callback = self._market_subscriptions.get(stream_name)
            if callback:
                try:
                    # Parse data into typed model based on stream type
                    parsed_data = None

                    if '@kline_' in stream_name:
                        # Parse kline data (returns None if candle is not closed)
                        parsed_data = self._parser.parse_kline(stream_data)
                    elif '@trade' in stream_name:
                        # Parse trade data
                        parsed_data = self._parser.parse_trade(stream_data)
                    elif '@bookTicker' in stream_name:
                        # Parse book ticker data
                        parsed_data = self._parser.parse_book_ticker(stream_data)
                    else:
                        # Unknown stream type, pass raw data
                        logger.warning(f"Unknown stream type: {stream_name}")
                        parsed_data = stream_data

                    # Only invoke callback if we have parsed data
                    # (for klines, this filters out open candles)
                    if parsed_data is not None:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(parsed_data)
                        else:
                            callback(parsed_data)

                except Exception as e:
                    logger.error(
                        "Error in market data callback",
                        stream=stream_name,
                        error=str(e),
                        exc_info=True
                    )

        except json.JSONDecodeError as e:
            logger.error("Failed to decode market message", error=str(e))
        except Exception as e:
            logger.error("Error handling market message", error=str(e), exc_info=True)

    async def _handle_user_message(self, message: str):
        """
        Handle incoming user data message.

        Parses raw WebSocket data into typed models (Order or AccountUpdate) and invokes callbacks.

        Args:
            message: JSON message from WebSocket
        """
        try:
            data = json.loads(message)

            self._stats['messages_received'] += 1
            self._stats['last_message_time'] = datetime.utcnow()

            if self._user_callback:
                try:
                    # Parse user data into typed model
                    parsed_data = self._parser.parse_user_data(data)

                    # Only invoke callback if parsing succeeded
                    if parsed_data is not None:
                        if asyncio.iscoroutinefunction(self._user_callback):
                            await self._user_callback(parsed_data)
                        else:
                            self._user_callback(parsed_data)

                except Exception as e:
                    logger.error(
                        "Error in user data callback",
                        error=str(e),
                        exc_info=True
                    )

        except json.JSONDecodeError as e:
            logger.error("Failed to decode user message", error=str(e))
        except Exception as e:
            logger.error("Error handling user message", error=str(e), exc_info=True)