"""
Exchange gateway module for API integration.
"""

from .gateway import ExchangeGateway, OrderSide, OrderType, TimeInForce, PositionMode
from .exceptions import (
    ExchangeError,
    ExchangeAPIError,
    TransientError,
    PermanentError,
    WebSocketError,
    RateLimitError,
    InvalidOrderError,
    InsufficientBalanceError,
    ConnectionError,
    InvalidTransitionError
)
from .binance_gateway import BinanceGateway
from .models import (
    Order,
    OrderStatus,
    Balance,
    Position,
    PositionSide,
    SymbolInfo,
    Ticker,
    OrderBook,
    Candle,
    Trade,
    AccountBalance,
    AccountPosition,
    AccountUpdate
)
from .exchange_config import (
    ExchangeType,
    ExchangeConfig,
    get_exchange_config,
    normalize_symbol,
    denormalize_symbol
)
from .rate_limiter import RateLimiter, GlobalRateLimiter
from .websocket_manager import WebSocketManager
from .websocket_parser import WebSocketParser

__all__ = [
    # Gateway interfaces
    "ExchangeGateway",
    "BinanceGateway",
    "OrderSide",
    "OrderType",
    "TimeInForce",
    "PositionMode",

    # Exceptions
    "ExchangeError",
    "ExchangeAPIError",
    "TransientError",
    "PermanentError",
    "WebSocketError",
    "RateLimitError",
    "InvalidOrderError",
    "InsufficientBalanceError",
    "ConnectionError",
    "InvalidTransitionError",

    # Data models
    "Order",
    "OrderStatus",
    "Balance",
    "Position",
    "PositionSide",
    "SymbolInfo",
    "Ticker",
    "OrderBook",
    "Candle",
    "Trade",
    "AccountBalance",
    "AccountPosition",
    "AccountUpdate",

    # Exchange config
    "ExchangeType",
    "ExchangeConfig",
    "get_exchange_config",
    "normalize_symbol",
    "denormalize_symbol",

    # Rate limiting
    "RateLimiter",
    "GlobalRateLimiter",

    # WebSocket
    "WebSocketManager",
    "WebSocketParser"
]
