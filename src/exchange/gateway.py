"""
Abstract base class for exchange gateway operations.

This module defines the interface for all exchange-related operations,
including REST API calls and WebSocket stream management.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
from enum import Enum


class OrderSide(Enum):
    """Order side enumeration."""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    """Order type enumeration."""
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_LIMIT = "STOP_LOSS_LIMIT"
    TAKE_PROFIT = "TAKE_PROFIT"
    TAKE_PROFIT_LIMIT = "TAKE_PROFIT_LIMIT"


class TimeInForce(Enum):
    """Time in force enumeration."""
    GTC = "GTC"  # Good Till Cancel
    IOC = "IOC"  # Immediate or Cancel
    FOK = "FOK"  # Fill or Kill


class PositionMode(Enum):
    """Position mode for futures trading."""
    ONE_WAY = "ONE_WAY"      # Single position per symbol (default)
    HEDGE = "HEDGE"          # Separate LONG and SHORT positions


class ExchangeGateway(ABC):
    """
    Abstract base class for exchange gateway operations.

    All exchange implementations must inherit from this class and
    implement all abstract methods for REST and WebSocket operations.
    """

    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        """
        Initialize the exchange gateway.

        Args:
            api_key: Exchange API key
            api_secret: Exchange API secret
            testnet: Use testnet environment (default: True for safety)
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self._is_connected = False

    # =========================================================================
    # REST API - Market Data Methods
    # =========================================================================

    @abstractmethod
    async def get_exchange_info(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Get exchange trading rules and symbol information.

        Args:
            symbol: Specific symbol to query (optional, returns all if None)

        Returns:
            Dictionary containing exchange information including:
            - symbols: List of trading pairs
            - filters: Price/quantity filters (MIN_NOTIONAL, LOT_SIZE, etc.)
            - rateLimits: API rate limit information

        Raises:
            ExchangeAPIError: If API call fails
        """
        pass

    @abstractmethod
    async def get_ohlc_data(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 500
    ) -> List[Dict[str, Any]]:
        """
        Get historical OHLC (candlestick) data.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            interval: Timeframe (e.g., "1m", "15m", "1h", "1d")
            start_time: Start time for historical data
            end_time: End time for historical data
            limit: Maximum number of candles to return (default: 500)

        Returns:
            List of candle dictionaries containing:
            - open_time, open, high, low, close, volume
            - close_time, quote_asset_volume, number_of_trades

        Raises:
            ExchangeAPIError: If API call fails
        """
        pass

    @abstractmethod
    async def get_ticker_24hr(self, symbol: str) -> Dict[str, Any]:
        """
        Get 24-hour price change statistics.

        Args:
            symbol: Trading pair symbol

        Returns:
            Dictionary containing 24hr statistics:
            - priceChange, priceChangePercent
            - weightedAvgPrice, lastPrice
            - volume, quoteVolume

        Raises:
            ExchangeAPIError: If API call fails
        """
        pass

    @abstractmethod
    async def get_order_book(self, symbol: str, limit: int = 100) -> Dict[str, Any]:
        """
        Get current order book (bids and asks).

        Args:
            symbol: Trading pair symbol
            limit: Depth of order book (default: 100)

        Returns:
            Dictionary containing:
            - bids: List of [price, quantity]
            - asks: List of [price, quantity]
            - lastUpdateId: Order book update ID

        Raises:
            ExchangeAPIError: If API call fails
        """
        pass

    # =========================================================================
    # REST API - Account Methods
    # =========================================================================

    @abstractmethod
    async def get_account_balance(self) -> Dict[str, Any]:
        """
        Get account balance information.

        Returns:
            Dictionary containing:
            - balances: List of asset balances
            - totalWalletBalance: Total account balance (Futures)
            - availableBalance: Available balance for trading

        Raises:
            ExchangeAPIError: If API call fails
        """
        pass

    @abstractmethod
    async def get_positions(self) -> List[Dict[str, Any]]:
        """
        Get current open positions (Futures only).

        Returns:
            List of position dictionaries containing:
            - symbol, positionSide, positionAmt
            - entryPrice, unrealizedProfit
            - leverage, marginType

        Raises:
            ExchangeAPIError: If API call fails
            NotImplementedError: If called on Spot market
        """
        pass

    @abstractmethod
    async def get_position_mode(self) -> PositionMode:
        """
        Get current position mode (Futures only).

        Returns:
            PositionMode enum (ONE_WAY or HEDGE)

        Raises:
            ExchangeAPIError: If API call fails
            NotImplementedError: If called on Spot market
        """
        pass

    @abstractmethod
    async def set_position_mode(self, mode: PositionMode) -> Dict[str, Any]:
        """
        Set position mode (Futures only).

        Args:
            mode: Position mode to set (ONE_WAY or HEDGE)

        Returns:
            Response dictionary from exchange

        Raises:
            ExchangeAPIError: If API call fails
            NotImplementedError: If called on Spot market

        Note:
            - Cannot change position mode if open positions exist
            - Some exchanges require account-level setting
        """
        pass

    @abstractmethod
    async def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """
        Set leverage for a symbol (Futures only).

        Args:
            symbol: Trading pair symbol
            leverage: Leverage multiplier (1-125 depending on symbol)

        Returns:
            Dictionary confirming leverage setting

        Raises:
            ExchangeAPIError: If API call fails
            NotImplementedError: If called on Spot market
        """
        pass

    # =========================================================================
    # REST API - Order Management Methods
    # =========================================================================

    @abstractmethod
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
    ) -> Dict[str, Any]:
        """
        Submit a new order to the exchange.

        Args:
            symbol: Trading pair symbol
            side: BUY or SELL
            order_type: LIMIT, MARKET, STOP_LOSS, etc.
            quantity: Order quantity
            price: Order price (required for LIMIT orders)
            time_in_force: GTC, IOC, or FOK
            stop_price: Stop price for stop orders
            client_order_id: Custom order ID for tracking
            **kwargs: Additional exchange-specific parameters

        Returns:
            Dictionary containing:
            - orderId, clientOrderId
            - symbol, side, type, status
            - price, origQty, executedQty
            - transactTime

        Raises:
            ExchangeAPIError: If order submission fails
        """
        pass

    @abstractmethod
    async def modify_order(
        self,
        symbol: str,
        order_id: int,
        quantity: Optional[float] = None,
        price: Optional[float] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Modify an existing order (cancel and replace).

        Args:
            symbol: Trading pair symbol
            order_id: Exchange order ID to modify
            quantity: New quantity (optional)
            price: New price (optional)
            **kwargs: Additional parameters

        Returns:
            Dictionary with new order information

        Raises:
            ExchangeAPIError: If modification fails
        """
        pass

    @abstractmethod
    async def cancel_order(
        self,
        symbol: str,
        order_id: Optional[int] = None,
        client_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cancel an existing order.

        Args:
            symbol: Trading pair symbol
            order_id: Exchange order ID (one of order_id or client_order_id required)
            client_order_id: Client order ID

        Returns:
            Dictionary confirming cancellation

        Raises:
            ExchangeAPIError: If cancellation fails
        """
        pass

    @abstractmethod
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all open orders for account.

        Args:
            symbol: Filter by specific symbol (optional)

        Returns:
            List of open order dictionaries

        Raises:
            ExchangeAPIError: If API call fails
        """
        pass

    @abstractmethod
    async def get_order_status(
        self,
        symbol: str,
        order_id: Optional[int] = None,
        client_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Query order status.

        Args:
            symbol: Trading pair symbol
            order_id: Exchange order ID (one required)
            client_order_id: Client order ID (one required)

        Returns:
            Dictionary with order status and details

        Raises:
            ExchangeAPIError: If API call fails
        """
        pass

    # =========================================================================
    # WebSocket Methods
    # =========================================================================

    @abstractmethod
    async def subscribe_kline(
        self,
        symbol: str,
        interval: str,
        callback: Callable[[Dict[str, Any]], None]
    ) -> None:
        """
        Subscribe to kline/candlestick stream.

        Args:
            symbol: Trading pair symbol
            interval: Timeframe (e.g., "1m", "15m", "1h", "1d")
            callback: Function to call with kline data

        Raises:
            WebSocketError: If subscription fails
        """
        pass

    @abstractmethod
    async def subscribe_trade(
        self,
        symbol: str,
        callback: Callable[[Dict[str, Any]], None]
    ) -> None:
        """
        Subscribe to individual trade stream.

        Args:
            symbol: Trading pair symbol
            callback: Function to call with trade data

        Raises:
            WebSocketError: If subscription fails
        """
        pass

    @abstractmethod
    async def subscribe_book_ticker(
        self,
        symbol: str,
        callback: Callable[[Dict[str, Any]], None]
    ) -> None:
        """
        Subscribe to best bid/ask price stream.

        Args:
            symbol: Trading pair symbol
            callback: Function to call with ticker data

        Raises:
            WebSocketError: If subscription fails
        """
        pass

    @abstractmethod
    async def subscribe_user_data(
        self,
        callback: Callable[[Dict[str, Any]], None]
    ) -> None:
        """
        Subscribe to user data stream (order updates, balance changes).

        Args:
            callback: Function to call with user data events

        Raises:
            WebSocketError: If subscription fails
        """
        pass

    @abstractmethod
    async def unsubscribe_all(self) -> None:
        """
        Unsubscribe from all WebSocket streams.

        Raises:
            WebSocketError: If unsubscription fails
        """
        pass

    # =========================================================================
    # Connection Management
    # =========================================================================

    @abstractmethod
    async def connect(self) -> None:
        """
        Establish connection to exchange.

        Raises:
            ConnectionError: If connection fails
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """
        Close connection to exchange.
        """
        pass

    @property
    def is_connected(self) -> bool:
        """Check if gateway is connected."""
        return self._is_connected
