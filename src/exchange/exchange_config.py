"""
Exchange-specific configurations for multi-exchange support.

This module contains exchange-specific settings such as:
- API endpoints
- Rate limits
- Error code mappings
- Symbol format converters
"""

from dataclasses import dataclass
from typing import Dict, Callable
from enum import Enum


class ExchangeType(Enum):
    """Supported exchanges."""
    BINANCE = "binance"
    BYBIT = "bybit"
    OKX = "okx"
    KRAKEN = "kraken"
    # Add more exchanges as needed


@dataclass
class RateLimitConfig:
    """Rate limit configuration for an exchange."""
    requests_per_minute: int
    weight_per_minute: int
    order_rate_per_second: int
    websocket_connections_per_ip: int


@dataclass
class ExchangeConfig:
    """
    Configuration for a specific exchange.

    This encapsulates all exchange-specific settings, making it easy
    to add new exchanges without modifying core bot logic.
    """
    exchange_type: ExchangeType
    name: str

    # Endpoints
    rest_base_url: str
    rest_testnet_url: str
    websocket_base_url: str
    websocket_testnet_url: str

    # Rate limits
    rate_limits: RateLimitConfig

    # Symbol format conversion
    symbol_separator: str            # "/" for "BTC/USDT", "" for "BTCUSDT"

    # Order types supported
    supports_stop_orders: bool
    supports_post_only: bool
    supports_reduce_only: bool

    # Futures-specific
    supports_hedge_mode: bool
    supports_one_way_mode: bool


# ============================================================================
# BINANCE CONFIGURATION
# ============================================================================

BINANCE_CONFIG = ExchangeConfig(
    exchange_type=ExchangeType.BINANCE,
    name="Binance",

    # REST Endpoints
    rest_base_url="https://fapi.binance.com",
    rest_testnet_url="https://testnet.binancefuture.com",

    # WebSocket Endpoints
    websocket_base_url="wss://fstream.binance.com",
    websocket_testnet_url="wss://stream.binancefuture.com",

    # Rate Limits (Binance Futures)
    rate_limits=RateLimitConfig(
        requests_per_minute=2400,    # REST API
        weight_per_minute=2400,      # Weight-based limit
        order_rate_per_second=300,   # Order placement limit
        websocket_connections_per_ip=300
    ),

    # Symbol format
    symbol_separator="",             # BTCUSDT (no separator)

    # Features
    supports_stop_orders=True,
    supports_post_only=True,
    supports_reduce_only=True,
    supports_hedge_mode=True,
    supports_one_way_mode=True
)


# ============================================================================
# BYBIT CONFIGURATION (Future expansion)
# ============================================================================

BYBIT_CONFIG = ExchangeConfig(
    exchange_type=ExchangeType.BYBIT,
    name="Bybit",

    # REST Endpoints
    rest_base_url="https://api.bybit.com",
    rest_testnet_url="https://api-testnet.bybit.com",

    # WebSocket Endpoints
    websocket_base_url="wss://stream.bybit.com",
    websocket_testnet_url="wss://stream-testnet.bybit.com",

    # Rate Limits (Bybit)
    rate_limits=RateLimitConfig(
        requests_per_minute=600,
        weight_per_minute=600,
        order_rate_per_second=10,
        websocket_connections_per_ip=500
    ),

    # Symbol format
    symbol_separator="",             # BTCUSDT

    # Features
    supports_stop_orders=True,
    supports_post_only=True,
    supports_reduce_only=True,
    supports_hedge_mode=True,
    supports_one_way_mode=True
)


# ============================================================================
# OKX CONFIGURATION (Future expansion)
# ============================================================================

OKX_CONFIG = ExchangeConfig(
    exchange_type=ExchangeType.OKX,
    name="OKX",

    # REST Endpoints
    rest_base_url="https://www.okx.com",
    rest_testnet_url="https://www.okx.com",  # OKX uses same URL with demo flag

    # WebSocket Endpoints
    websocket_base_url="wss://ws.okx.com:8443/ws/v5/public",
    websocket_testnet_url="wss://wspap.okx.com:8443/ws/v5/public",

    # Rate Limits (OKX)
    rate_limits=RateLimitConfig(
        requests_per_minute=1200,
        weight_per_minute=1200,
        order_rate_per_second=60,
        websocket_connections_per_ip=100
    ),

    # Symbol format
    symbol_separator="-",            # BTC-USDT

    # Features
    supports_stop_orders=True,
    supports_post_only=True,
    supports_reduce_only=True,
    supports_hedge_mode=True,
    supports_one_way_mode=True
)


# ============================================================================
# EXCHANGE REGISTRY
# ============================================================================

EXCHANGE_CONFIGS: Dict[ExchangeType, ExchangeConfig] = {
    ExchangeType.BINANCE: BINANCE_CONFIG,
    ExchangeType.BYBIT: BYBIT_CONFIG,
    ExchangeType.OKX: OKX_CONFIG,
}


def get_exchange_config(exchange_type: ExchangeType) -> ExchangeConfig:
    """
    Get configuration for a specific exchange.

    Args:
        exchange_type: Type of exchange

    Returns:
        ExchangeConfig instance

    Raises:
        ValueError: If exchange is not supported
    """
    if exchange_type not in EXCHANGE_CONFIGS:
        raise ValueError(f"Unsupported exchange: {exchange_type}")

    return EXCHANGE_CONFIGS[exchange_type]


# ============================================================================
# SYMBOL NORMALIZATION
# ============================================================================

def normalize_symbol(symbol: str, exchange_type: ExchangeType) -> str:
    """
    Convert exchange-specific symbol format to normalized format.

    Normalized format: "BASE/QUOTE" (e.g., "BTC/USDT")

    Args:
        symbol: Exchange-specific symbol
        exchange_type: Exchange type

    Returns:
        Normalized symbol string

    Examples:
        >>> normalize_symbol("BTCUSDT", ExchangeType.BINANCE)
        "BTC/USDT"
        >>> normalize_symbol("BTC-USDT", ExchangeType.OKX)
        "BTC/USDT"
    """
    config = get_exchange_config(exchange_type)

    if config.symbol_separator:
        # Symbol has separator (e.g., "BTC-USDT")
        return symbol.replace(config.symbol_separator, "/")
    else:
        # Symbol has no separator (e.g., "BTCUSDT")
        # Need exchange-specific logic to split base/quote
        if exchange_type == ExchangeType.BINANCE:
            return _normalize_binance_symbol(symbol)
        else:
            raise NotImplementedError(f"Symbol normalization for {exchange_type} not implemented")


def denormalize_symbol(symbol: str, exchange_type: ExchangeType) -> str:
    """
    Convert normalized symbol format to exchange-specific format.

    Args:
        symbol: Normalized symbol ("BTC/USDT")
        exchange_type: Exchange type

    Returns:
        Exchange-specific symbol string

    Examples:
        >>> denormalize_symbol("BTC/USDT", ExchangeType.BINANCE)
        "BTCUSDT"
        >>> denormalize_symbol("BTC/USDT", ExchangeType.OKX)
        "BTC-USDT"
    """
    config = get_exchange_config(exchange_type)

    if "/" in symbol:
        base, quote = symbol.split("/")
        return f"{base}{config.symbol_separator}{quote}"
    else:
        # Already in exchange format
        return symbol


def _normalize_binance_symbol(symbol: str) -> str:
    """
    Normalize Binance symbol format.

    Binance uses no separator, so we need to detect common quote currencies.

    Args:
        symbol: Binance symbol (e.g., "BTCUSDT")

    Returns:
        Normalized symbol ("BTC/USDT")
    """
    # Common quote currencies (ordered by length for proper matching)
    quote_currencies = ["USDT", "BUSD", "USDC", "BTC", "ETH", "BNB", "DAI"]

    for quote in quote_currencies:
        if symbol.endswith(quote):
            base = symbol[:-len(quote)]
            return f"{base}/{quote}"

    # Fallback: assume last 3-4 chars are quote currency
    if len(symbol) > 6:
        return f"{symbol[:-4]}/{symbol[-4:]}"
    else:
        return f"{symbol[:-3]}/{symbol[-3:]}"


# ============================================================================
# ERROR CODE MAPPINGS
# ============================================================================

# Binance error codes that should trigger retry (transient)
BINANCE_TRANSIENT_ERRORS = {
    -1001,  # Internal error
    -1003,  # Too many requests
    -1021,  # Timestamp out of recv window
    -1022,  # Invalid signature (can be transient)
}

# Binance error codes that are permanent (no retry)
BINANCE_PERMANENT_ERRORS = {
    -1100,  # Invalid parameter
    -1102,  # Mandatory parameter missing
    -2010,  # NEW_ORDER_REJECTED
    -2011,  # CANCEL_REJECTED
    -4001,  # Invalid leverage
    -4003,  # Quantity less than min
    -4004,  # Quantity greater than max
    -4131,  # Price less than min
    -4132,  # Price greater than max
}


def is_transient_error(error_code: int, exchange_type: ExchangeType) -> bool:
    """
    Check if error code represents a transient (retryable) error.

    Args:
        error_code: Exchange error code
        exchange_type: Exchange type

    Returns:
        True if error is transient and should be retried
    """
    if exchange_type == ExchangeType.BINANCE:
        return error_code in BINANCE_TRANSIENT_ERRORS

    # Add logic for other exchanges
    return False


def is_permanent_error(error_code: int, exchange_type: ExchangeType) -> bool:
    """
    Check if error code represents a permanent (non-retryable) error.

    Args:
        error_code: Exchange error code
        exchange_type: Exchange type

    Returns:
        True if error is permanent and should not be retried
    """
    if exchange_type == ExchangeType.BINANCE:
        return error_code in BINANCE_PERMANENT_ERRORS

    # Add logic for other exchanges
    return False
