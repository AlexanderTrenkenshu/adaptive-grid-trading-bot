"""
Binance exchange gateway implementation.

This module implements the ExchangeGateway interface specifically for Binance,
while maintaining exchange-agnostic data models for use by the rest of the bot.
"""

import hashlib
import hmac
import time
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timedelta
from decimal import Decimal

from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException

from .gateway import ExchangeGateway, OrderSide, OrderType, TimeInForce, PositionMode
from .exceptions import (
    ExchangeAPIError,
    TransientError,
    PermanentError,
    RateLimitError,
    InvalidOrderError,
    InsufficientBalanceError,
    ConnectionError as ExchangeConnectionError
)
from .models import (
    Order,
    OrderStatus,
    Balance,
    Position,
    PositionSide,
    SymbolInfo,
    Ticker,
    OrderBook,
    Candle
)
from .exchange_config import (
    BINANCE_CONFIG,
    ExchangeType,
    normalize_symbol,
    denormalize_symbol,
    is_transient_error,
    is_permanent_error
)
from .websocket_manager import WebSocketManager
from ..utils.logger import get_logger
from ..utils.retry import retry_on_transient_error


logger = get_logger(__name__)


class BinanceGateway(ExchangeGateway):
    """
    Binance-specific implementation of ExchangeGateway.

    This class handles all Binance API interactions and converts
    Binance-specific responses to normalized data models.
    """

    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        """
        Initialize Binance gateway.

        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            testnet: Use testnet if True
        """
        super().__init__(api_key, api_secret, testnet)

        self.exchange_type = ExchangeType.BINANCE
        self.config = BINANCE_CONFIG

        # Select appropriate base URL
        if testnet:
            self.base_url = self.config.rest_testnet_url
            self.ws_url = self.config.websocket_testnet_url
        else:
            self.base_url = self.config.rest_base_url
            self.ws_url = self.config.websocket_base_url

        # Initialize python-binance client
        self.client: Optional[Client] = None

        # Initialize WebSocket manager
        self.ws_manager = WebSocketManager(self.config, testnet=testnet)
        self._listen_key: Optional[str] = None

        logger.info(
            "Binance gateway initialized",
            testnet=testnet,
            base_url=self.base_url
        )

    async def connect(self) -> None:
        """
        Establish connection to Binance API.

        This initializes the Binance client and verifies connectivity.
        """
        try:
            self.client = Client(
                api_key=self.api_key,
                api_secret=self.api_secret,
                testnet=self.testnet
            )

            # Override base URL for testnet
            if self.testnet:
                self.client.API_URL = self.base_url

            # Test connectivity
            server_time = self.client.get_server_time()
            logger.info(
                "Connected to Binance",
                server_time=server_time,
                testnet=self.testnet
            )

            self._is_connected = True

            # Start WebSocket manager
            await self.ws_manager.connect()

        except BinanceAPIException as e:
            logger.error("Binance API error during connection", error=str(e), code=e.code)
            raise self._map_exception(e)
        except Exception as e:
            logger.error("Failed to connect to Binance", error=str(e))
            raise ExchangeConnectionError(f"Connection failed: {str(e)}")

    async def disconnect(self) -> None:
        """Disconnect from Binance API."""
        # Stop WebSocket manager
        await self.ws_manager.disconnect()

        if self.client:
            # python-binance doesn't have explicit disconnect
            self.client = None
            self._is_connected = False
            logger.info("Disconnected from Binance")

    # ========================================================================
    # REST API Methods - Market Data
    # ========================================================================

    @retry_on_transient_error(max_attempts=3, backoff_base=2)
    async def get_exchange_info(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Get exchange trading rules and symbol information.

        Args:
            symbol: Specific symbol to query (optional)

        Returns:
            Exchange info dict with symbol filters and trading rules
        """
        try:
            if not self.client:
                raise ExchangeConnectionError("Not connected to exchange")

            info = self.client.futures_exchange_info()

            if symbol:
                # Denormalize symbol for Binance
                binance_symbol = denormalize_symbol(symbol, self.exchange_type)

                # Find specific symbol
                for sym_info in info['symbols']:
                    if sym_info['symbol'] == binance_symbol:
                        return sym_info

                raise InvalidOrderError(f"Symbol {symbol} not found")

            return info

        except BinanceAPIException as e:
            logger.error("Binance API error in get_exchange_info", error=str(e), code=e.code)
            raise self._map_exception(e)

    async def get_symbol_info(self, symbol: str) -> SymbolInfo:
        """
        Get normalized symbol information.

        This is a convenience method that returns SymbolInfo model.

        Args:
            symbol: Normalized symbol ("BTC/USDT")

        Returns:
            SymbolInfo instance
        """
        exchange_info = await self.get_exchange_info(symbol)

        # Parse Binance filters
        filters = {f['filterType']: f for f in exchange_info['filters']}

        # Extract lot size (quantity) constraints
        lot_size = filters.get('LOT_SIZE', {})
        min_qty = Decimal(lot_size.get('minQty', '0'))
        max_qty = Decimal(lot_size.get('maxQty', '0'))
        step_size = Decimal(lot_size.get('stepSize', '0'))

        # Extract price constraints
        price_filter = filters.get('PRICE_FILTER', {})
        min_price = Decimal(price_filter.get('minPrice', '0'))
        max_price = Decimal(price_filter.get('maxPrice', '0'))
        tick_size = Decimal(price_filter.get('tickSize', '0'))

        # Extract minimum notional
        min_notional = Decimal(filters.get('MIN_NOTIONAL', {}).get('notional', '0'))

        return SymbolInfo(
            symbol=symbol,
            base_asset=exchange_info['baseAsset'],
            quote_asset=exchange_info['quoteAsset'],
            min_quantity=min_qty,
            max_quantity=max_qty,
            quantity_step=step_size,
            min_price=min_price,
            max_price=max_price,
            price_step=tick_size,
            min_notional=min_notional,
            is_spot=False,
            is_futures=True,
            is_margin=False,
            is_trading=exchange_info['status'] == 'TRADING',
            raw_data=exchange_info
        )

    @retry_on_transient_error(max_attempts=3, backoff_base=2)
    async def get_ohlc_data(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 500
    ) -> List[Candle]:
        """
        Get historical OHLC (candlestick) data.

        Args:
            symbol: Normalized symbol
            interval: Candle interval ("1m", "5m", "1h", "1d", etc.)
            start_time: Start timestamp (optional)
            end_time: End timestamp (optional)
            limit: Number of candles to fetch (max 1500)

        Returns:
            List of Candle objects
        """
        try:
            if not self.client:
                raise ExchangeConnectionError("Not connected to exchange")

            binance_symbol = denormalize_symbol(symbol, self.exchange_type)

            kwargs = {'limit': limit}
            if start_time:
                kwargs['startTime'] = int(start_time.timestamp() * 1000)
            if end_time:
                kwargs['endTime'] = int(end_time.timestamp() * 1000)

            klines = self.client.futures_klines(
                symbol=binance_symbol,
                interval=interval,
                **kwargs
            )

            candles = []
            for k in klines:
                candles.append(Candle(
                    symbol=symbol,
                    interval=interval,
                    open_time=datetime.fromtimestamp(k[0] / 1000),
                    close_time=datetime.fromtimestamp(k[6] / 1000),
                    open=Decimal(k[1]),
                    high=Decimal(k[2]),
                    low=Decimal(k[3]),
                    close=Decimal(k[4]),
                    volume=Decimal(k[5]),
                    quote_volume=Decimal(k[7]),
                    trades=int(k[8])
                ))

            logger.debug(
                "Fetched OHLC data",
                symbol=symbol,
                interval=interval,
                count=len(candles)
            )

            return candles

        except BinanceAPIException as e:
            logger.error("Binance API error in get_ohlc_data", error=str(e), code=e.code)
            raise self._map_exception(e)

    @retry_on_transient_error(max_attempts=3, backoff_base=2)
    async def get_ticker_24hr(self, symbol: str) -> Ticker:
        """
        Get 24-hour ticker data.

        Args:
            symbol: Normalized symbol

        Returns:
            Ticker object
        """
        try:
            if not self.client:
                raise ExchangeConnectionError("Not connected to exchange")

            binance_symbol = denormalize_symbol(symbol, self.exchange_type)

            # Get 24hr ticker data
            ticker = self.client.futures_ticker(symbol=binance_symbol)

            # Get bid/ask prices from orderbook ticker
            book_ticker = self.client.futures_orderbook_ticker(symbol=binance_symbol)

            return Ticker(
                symbol=symbol,
                last_price=Decimal(ticker['lastPrice']),
                bid_price=Decimal(book_ticker['bidPrice']),
                ask_price=Decimal(book_ticker['askPrice']),
                bid_qty=Decimal(book_ticker['bidQty']),
                ask_qty=Decimal(book_ticker['askQty']),
                timestamp=datetime.fromtimestamp(int(ticker['closeTime']) / 1000)
            )

        except BinanceAPIException as e:
            logger.error("Binance API error in get_ticker_24hr", error=str(e), code=e.code)
            raise self._map_exception(e)

    @retry_on_transient_error(max_attempts=3, backoff_base=2)
    async def get_order_book(self, symbol: str, limit: int = 100) -> OrderBook:
        """
        Get current order book.

        Args:
            symbol: Normalized symbol
            limit: Depth limit (5, 10, 20, 50, 100, 500, 1000)

        Returns:
            OrderBook object
        """
        try:
            if not self.client:
                raise ExchangeConnectionError("Not connected to exchange")

            binance_symbol = denormalize_symbol(symbol, self.exchange_type)
            depth = self.client.futures_order_book(symbol=binance_symbol, limit=limit)

            bids = [(Decimal(price), Decimal(qty)) for price, qty in depth['bids']]
            asks = [(Decimal(price), Decimal(qty)) for price, qty in depth['asks']]

            return OrderBook(
                symbol=symbol,
                bids=bids,
                asks=asks,
                timestamp=datetime.now()
            )

        except BinanceAPIException as e:
            logger.error("Binance API error in get_order_book", error=str(e), code=e.code)
            raise self._map_exception(e)

    # ========================================================================
    # REST API Methods - Account
    # ========================================================================

    @retry_on_transient_error(max_attempts=3, backoff_base=2)
    async def get_account_balance(self) -> List[Balance]:
        """
        Get account balance for all assets.

        Returns:
            List of Balance objects
        """
        try:
            if not self.client:
                raise ExchangeConnectionError("Not connected to exchange")

            account_info = self.client.futures_account()

            balances = []
            for asset_info in account_info['assets']:
                free = Decimal(asset_info['availableBalance'])
                locked = Decimal(asset_info['initialMargin'])
                total = free + locked

                # Only include non-zero balances
                if total > 0:
                    balances.append(Balance(
                        asset=asset_info['asset'],
                        free=free,
                        locked=locked,
                        total=total
                    ))

            logger.debug("Fetched account balance", count=len(balances))
            return balances

        except BinanceAPIException as e:
            logger.error("Binance API error in get_account_balance", error=str(e), code=e.code)
            raise self._map_exception(e)

    @retry_on_transient_error(max_attempts=3, backoff_base=2)
    async def get_positions(self) -> List[Position]:
        """
        Get all open futures positions.

        Returns:
            List of Position objects
        """
        try:
            if not self.client:
                raise ExchangeConnectionError("Not connected to exchange")

            positions_data = self.client.futures_position_information()

            positions = []
            for pos in positions_data:
                quantity = abs(Decimal(pos['positionAmt']))

                # Only include non-zero positions
                if quantity == 0:
                    continue

                # Determine position side
                if Decimal(pos['positionAmt']) > 0:
                    side = PositionSide.LONG
                elif Decimal(pos['positionAmt']) < 0:
                    side = PositionSide.SHORT
                else:
                    continue

                positions.append(Position(
                    symbol=normalize_symbol(pos['symbol'], self.exchange_type),
                    side=side,
                    quantity=quantity,
                    entry_price=Decimal(pos['entryPrice']),
                    mark_price=Decimal(pos['markPrice']),
                    unrealized_pnl=Decimal(pos['unRealizedProfit']),
                    leverage=int(pos['leverage']),
                    liquidation_price=Decimal(pos['liquidationPrice']) if pos.get('liquidationPrice') else None,
                    raw_data=pos
                ))

            logger.debug("Fetched positions", count=len(positions))
            return positions

        except BinanceAPIException as e:
            logger.error("Binance API error in get_positions", error=str(e), code=e.code)
            raise self._map_exception(e)

    @retry_on_transient_error(max_attempts=3, backoff_base=2)
    async def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """
        Set leverage for a symbol.

        Args:
            symbol: Normalized symbol
            leverage: Leverage value (1-125 for Binance Futures)

        Returns:
            Response dict
        """
        try:
            if not self.client:
                raise ExchangeConnectionError("Not connected to exchange")

            binance_symbol = denormalize_symbol(symbol, self.exchange_type)

            result = self.client.futures_change_leverage(
                symbol=binance_symbol,
                leverage=leverage
            )

            logger.info("Leverage set", symbol=symbol, leverage=leverage)
            return result

        except BinanceAPIException as e:
            logger.error("Binance API error in set_leverage", error=str(e), code=e.code)
            raise self._map_exception(e)

    @retry_on_transient_error(max_attempts=3, backoff_base=2)
    async def get_position_mode(self) -> PositionMode:
        """
        Get current position mode.

        Returns:
            PositionMode enum (ONE_WAY or HEDGE)
        """
        try:
            if not self.client:
                raise ExchangeConnectionError("Not connected to exchange")

            result = self.client.futures_get_position_mode()

            # Binance returns {'dualSidePosition': bool}
            # True = Hedge mode, False = One-way mode
            is_hedge = result.get('dualSidePosition', False)

            mode = PositionMode.HEDGE if is_hedge else PositionMode.ONE_WAY

            logger.debug("Position mode retrieved", mode=mode.value)
            return mode

        except BinanceAPIException as e:
            logger.error("Binance API error in get_position_mode", error=str(e), code=e.code)
            raise self._map_exception(e)

    @retry_on_transient_error(max_attempts=3, backoff_base=2)
    async def set_position_mode(self, mode: PositionMode) -> Dict[str, Any]:
        """
        Set position mode.

        Args:
            mode: Position mode to set (ONE_WAY or HEDGE)

        Returns:
            Response dict

        Raises:
            ExchangeAPIError: If positions are open or other error occurs
        """
        try:
            if not self.client:
                raise ExchangeConnectionError("Not connected to exchange")

            # Convert PositionMode to Binance format
            dual_side_position = (mode == PositionMode.HEDGE)

            result = self.client.futures_change_position_mode(
                dualSidePosition=dual_side_position
            )

            logger.info("Position mode set", mode=mode.value, dual_side=dual_side_position)
            return result

        except BinanceAPIException as e:
            logger.error("Binance API error in set_position_mode", error=str(e), code=e.code)
            raise self._map_exception(e)

    # ========================================================================
    # REST API Methods - Orders
    # ========================================================================

    @retry_on_transient_error(max_attempts=3, backoff_base=2)
    async def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: Optional[float] = None,
        time_in_force: TimeInForce = TimeInForce.GTC,
        stop_price: Optional[float] = None,
        client_order_id: Optional[str] = None,
        **kwargs
    ) -> Order:
        """
        Submit a new order.

        Args:
            symbol: Normalized symbol
            side: Order side (BUY/SELL)
            order_type: Order type (LIMIT/MARKET/etc.)
            quantity: Order quantity
            price: Limit price (required for LIMIT orders)
            time_in_force: Time in force (GTC/IOC/FOK)
            stop_price: Stop/trigger price (for stop orders)
            client_order_id: Client-provided order ID
            **kwargs: Additional exchange-specific parameters

        Returns:
            Order object
        """
        try:
            if not self.client:
                raise ExchangeConnectionError("Not connected to exchange")

            binance_symbol = denormalize_symbol(symbol, self.exchange_type)

            # Prepare order parameters
            params = {
                'symbol': binance_symbol,
                'side': side.value,
                'type': order_type.value,
                'quantity': quantity,
            }

            # Add price for limit orders
            if order_type in (OrderType.LIMIT, OrderType.STOP_LOSS_LIMIT, OrderType.TAKE_PROFIT_LIMIT):
                if price is None:
                    raise InvalidOrderError("Price required for LIMIT orders")
                params['price'] = price
                params['timeInForce'] = time_in_force.value

            # Add stop price for stop orders
            if order_type in (OrderType.STOP_LOSS, OrderType.STOP_LOSS_LIMIT, OrderType.TAKE_PROFIT, OrderType.TAKE_PROFIT_LIMIT):
                if stop_price is None:
                    raise InvalidOrderError("Stop price required for stop orders")
                params['stopPrice'] = stop_price

            # Add client order ID if provided
            if client_order_id:
                params['newClientOrderId'] = client_order_id

            # Merge additional parameters
            params.update(kwargs)

            # Submit order
            response = self.client.futures_create_order(**params)

            order = self._parse_order_response(response, symbol)

            logger.info(
                "Order submitted",
                symbol=symbol,
                side=side.value,
                order_type=order_type.value,
                quantity=quantity,
                price=price,
                order_id=order.order_id
            )

            return order

        except BinanceAPIException as e:
            logger.error("Binance API error in submit_order", error=str(e), code=e.code)
            raise self._map_exception(e)

    @retry_on_transient_error(max_attempts=3, backoff_base=2)
    async def modify_order(
        self,
        symbol: str,
        order_id: str,
        quantity: Optional[float] = None,
        price: Optional[float] = None,
        **kwargs
    ) -> Order:
        """
        Modify an existing order.

        Binance Futures supports order modification via cancelReplace API.

        Args:
            symbol: Normalized symbol
            order_id: Exchange order ID
            quantity: New quantity (optional)
            price: New price (optional)
            **kwargs: Additional parameters

        Returns:
            Modified Order object
        """
        try:
            if not self.client:
                raise ExchangeConnectionError("Not connected to exchange")

            binance_symbol = denormalize_symbol(symbol, self.exchange_type)

            params = {
                'symbol': binance_symbol,
                'orderId': order_id,
            }

            if quantity is not None:
                params['quantity'] = quantity

            if price is not None:
                params['price'] = price

            params.update(kwargs)

            # Use cancelReplace API
            response = self.client.futures_cancel_replace(**params)

            order = self._parse_order_response(response['newOrderResponse'], symbol)

            logger.info("Order modified", symbol=symbol, order_id=order_id)
            return order

        except BinanceAPIException as e:
            # If modify not supported, will need to cancel + replace manually
            logger.error("Binance API error in modify_order", error=str(e), code=e.code)
            raise self._map_exception(e)

    @retry_on_transient_error(max_attempts=3, backoff_base=2)
    async def cancel_order(
        self,
        symbol: str,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cancel an existing order.

        Args:
            symbol: Normalized symbol
            order_id: Exchange order ID (optional)
            client_order_id: Client order ID (optional)

        Returns:
            Response dict

        Raises:
            InvalidOrderError: If neither order_id nor client_order_id provided
        """
        try:
            if not self.client:
                raise ExchangeConnectionError("Not connected to exchange")

            if not order_id and not client_order_id:
                raise InvalidOrderError("Either order_id or client_order_id required")

            binance_symbol = denormalize_symbol(symbol, self.exchange_type)

            params = {'symbol': binance_symbol}

            if order_id:
                params['orderId'] = order_id
            else:
                params['origClientOrderId'] = client_order_id

            response = self.client.futures_cancel_order(**params)

            logger.info(
                "Order canceled",
                symbol=symbol,
                order_id=order_id,
                client_order_id=client_order_id
            )

            return response

        except BinanceAPIException as e:
            logger.error("Binance API error in cancel_order", error=str(e), code=e.code)
            raise self._map_exception(e)

    @retry_on_transient_error(max_attempts=3, backoff_base=2)
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """
        Get all open orders.

        Args:
            symbol: Filter by symbol (optional)

        Returns:
            List of Order objects
        """
        try:
            if not self.client:
                raise ExchangeConnectionError("Not connected to exchange")

            params = {}
            if symbol:
                params['symbol'] = denormalize_symbol(symbol, self.exchange_type)

            orders_data = self.client.futures_get_open_orders(**params)

            orders = [
                self._parse_order_response(order, normalize_symbol(order['symbol'], self.exchange_type))
                for order in orders_data
            ]

            logger.debug("Fetched open orders", count=len(orders))
            return orders

        except BinanceAPIException as e:
            logger.error("Binance API error in get_open_orders", error=str(e), code=e.code)
            raise self._map_exception(e)

    @retry_on_transient_error(max_attempts=3, backoff_base=2)
    async def get_order_status(
        self,
        symbol: str,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None
    ) -> Order:
        """
        Get status of a specific order.

        Args:
            symbol: Normalized symbol
            order_id: Exchange order ID (optional)
            client_order_id: Client order ID (optional)

        Returns:
            Order object

        Raises:
            InvalidOrderError: If neither order_id nor client_order_id provided
        """
        try:
            if not self.client:
                raise ExchangeConnectionError("Not connected to exchange")

            if not order_id and not client_order_id:
                raise InvalidOrderError("Either order_id or client_order_id required")

            binance_symbol = denormalize_symbol(symbol, self.exchange_type)

            params = {'symbol': binance_symbol}

            if order_id:
                params['orderId'] = order_id
            else:
                params['origClientOrderId'] = client_order_id

            order_data = self.client.futures_get_order(**params)

            return self._parse_order_response(order_data, symbol)

        except BinanceAPIException as e:
            logger.error("Binance API error in get_order_status", error=str(e), code=e.code)
            raise self._map_exception(e)

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _parse_order_response(self, response: Dict[str, Any], symbol: str) -> Order:
        """
        Parse Binance order response into normalized Order object.

        Args:
            response: Binance API response
            symbol: Normalized symbol

        Returns:
            Order object
        """
        # Parse order type and price
        order_type = response['type']

        # For MARKET orders, price is None
        # For LIMIT orders, price is the limit price
        if order_type == "MARKET":
            price = None
        else:
            price = Decimal(response['price']) if response.get('price') and response['price'] != '0' else None

        # Average fill price (0 if not filled yet)
        avg_fill_price = Decimal(response.get('avgPrice', '0'))
        if avg_fill_price == 0 and response.get('executedQty', '0') != '0':
            # Try to calculate from cumulative quote qty / executed qty
            executed_qty = Decimal(response.get('executedQty', '0'))
            cum_quote = Decimal(response.get('cumQuote', '0'))
            if executed_qty > 0 and cum_quote > 0:
                avg_fill_price = cum_quote / executed_qty

        return Order(
            order_id=str(response['orderId']),
            client_order_id=response.get('clientOrderId', ''),
            symbol=symbol,
            side=response['side'],
            order_type=order_type,
            status=response['status'],
            quantity=Decimal(response['origQty']),
            price=price,
            average_fill_price=avg_fill_price,
            commission=Decimal('0'),  # Commission not in order response, comes from fills
            commission_asset='USDT'  # Default, actual value comes from fills
        )

    # ========================================================================
    # WebSocket Methods
    # ========================================================================

    async def subscribe_kline(
        self,
        symbol: str,
        interval: str,
        callback: Callable
    ):
        """
        Subscribe to kline (candlestick) data stream.

        Callback receives Candle objects for CLOSED candles only.
        For 1m interval, callback is invoked once per minute when candle closes.

        Args:
            symbol: Normalized symbol (e.g., "BTC/USDT")
            interval: Kline interval (e.g., "1m", "15m", "1h", "1d")
            callback: Function to call with Candle objects
        """
        binance_symbol = denormalize_symbol(symbol, self.exchange_type)
        await self.ws_manager.subscribe_kline(binance_symbol, interval, callback)

    async def subscribe_trade(
        self,
        symbol: str,
        callback: Callable
    ):
        """
        Subscribe to trade data stream.

        Callback receives Trade objects for each trade execution.

        Args:
            symbol: Normalized symbol (e.g., "BTC/USDT")
            callback: Function to call with Trade objects
        """
        binance_symbol = denormalize_symbol(symbol, self.exchange_type)
        await self.ws_manager.subscribe_trade(binance_symbol, callback)

    async def subscribe_book_ticker(
        self,
        symbol: str,
        callback: Callable
    ):
        """
        Subscribe to book ticker (best bid/ask) stream.

        Callback receives Ticker objects with best bid/ask prices.

        Args:
            symbol: Normalized symbol (e.g., "BTC/USDT")
            callback: Function to call with Ticker objects
        """
        binance_symbol = denormalize_symbol(symbol, self.exchange_type)
        await self.ws_manager.subscribe_book_ticker(binance_symbol, callback)

    async def subscribe_user_data(
        self,
        callback: Callable
    ):
        """
        Subscribe to user data stream (order updates, balance changes).

        Callback receives Order or AccountUpdate objects depending on event type.

        Args:
            callback: Function to call with Order or AccountUpdate objects
        """
        # Generate listen key if not already done
        if not self._listen_key:
            self._listen_key = await self._get_listen_key()

        await self.ws_manager.subscribe_user_data(self._listen_key, callback)

    async def unsubscribe_all(self):
        """Unsubscribe from all WebSocket streams."""
        await self.ws_manager.unsubscribe_all()

    async def _get_listen_key(self) -> str:
        """
        Get listen key for user data stream.

        Returns:
            Listen key string
        """
        try:
            if not self.client:
                raise ExchangeConnectionError("Not connected to exchange")

            # Get listen key for Futures (synchronous call)
            result = self.client.futures_stream_get_listen_key()

            # Handle both dict response and direct string response
            if isinstance(result, dict):
                listen_key = result['listenKey']
            elif isinstance(result, str):
                listen_key = result
            else:
                raise ExchangeAPIError(f"Unexpected listen key response type: {type(result)}")

            logger.info("Listen key obtained for user data stream", listen_key=listen_key[:8] + "...")

            return listen_key

        except BinanceAPIException as e:
            logger.error("Failed to get listen key", error=str(e), code=e.code)
            raise self._map_exception(e)
        except Exception as e:
            logger.error("Unexpected error getting listen key", error=str(e))
            raise ExchangeAPIError(f"Failed to get listen key: {e}")

    async def _refresh_listen_key(self):
        """Refresh listen key to keep user data stream alive."""
        try:
            if not self.client or not self._listen_key:
                return

            # Refresh listen key for Futures
            self.client.futures_stream_keepalive(listenKey=self._listen_key)

            logger.debug("Listen key refreshed")

        except BinanceAPIException as e:
            logger.error("Failed to refresh listen key", error=str(e), code=e.code)
            raise self._map_exception(e)

    # ========================================================================
    # Error Handling
    # ========================================================================

    def _map_exception(self, e: BinanceAPIException) -> Exception:
        """
        Map Binance API exception to internal exception type.

        Args:
            e: Binance API exception

        Returns:
            Mapped exception
        """
        error_code = e.code

        # Check specific error types FIRST (before general transient/permanent)
        # Rate limit error
        if error_code == -1003:
            return RateLimitError(f"Rate limit exceeded: {e.message}")

        # Invalid order errors
        if error_code in (-2010, -4001, -4003, -4004, -4131, -4132):
            return InvalidOrderError(f"Invalid order: {e.message} (code: {error_code})")

        # Insufficient balance
        if 'insufficient balance' in e.message.lower():
            return InsufficientBalanceError(f"Insufficient balance: {e.message}")

        # Check if transient (retryable)
        if is_transient_error(error_code, self.exchange_type):
            return TransientError(f"Binance transient error: {e.message} (code: {error_code})")

        # Check if permanent (non-retryable)
        if is_permanent_error(error_code, self.exchange_type):
            return PermanentError(f"Binance permanent error: {e.message} (code: {error_code})")

        # Default to generic API error
        return ExchangeAPIError(f"Binance API error: {e.message} (code: {error_code})")
