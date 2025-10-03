"""
Exchange gateway module for API integration.
"""

from .gateway import ExchangeGateway, OrderSide, OrderType, TimeInForce
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

__all__ = [
    "ExchangeGateway",
    "OrderSide",
    "OrderType",
    "TimeInForce",
    "ExchangeError",
    "ExchangeAPIError",
    "TransientError",
    "PermanentError",
    "WebSocketError",
    "RateLimitError",
    "InvalidOrderError",
    "InsufficientBalanceError",
    "ConnectionError",
    "InvalidTransitionError"
]
