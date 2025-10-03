"""
Structured logging utilities using structlog.

Provides JSON-formatted logging for production and
human-readable logging for development.
"""

import sys
import structlog
from pathlib import Path
from datetime import datetime
from typing import Optional


def setup_logger(
    log_level: str = "INFO",
    log_dir: str = "logs",
    log_format: str = "json",
    service_name: str = "adaptive-grid-bot"
) -> structlog.BoundLogger:
    """
    Configure and return a structured logger.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Directory for log files
        log_format: "json" for production, "console" for development
        service_name: Name of the service for log context

    Returns:
        Configured structlog logger instance
    """
    # Create log directory if it doesn't exist
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Generate log filename with current date
    log_filename = f"bot_{datetime.utcnow().strftime('%Y-%m-%d')}.log"
    log_file = log_path / log_filename

    # Configure processors based on format
    if log_format == "json":
        processors = [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
        ]
    else:  # console format for development
        processors = [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=True)
        ]

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(structlog.stdlib, log_level.upper(), structlog.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=open(log_file, "a")),
        cache_logger_on_first_use=True,
    )

    # Also configure console output
    console_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=True),
        structlog.dev.ConsoleRenderer(colors=True)
    ]

    console_logger = structlog.PrintLoggerFactory(file=sys.stdout)

    # Get logger with service context
    logger = structlog.get_logger(service=service_name)

    return logger


def get_logger(name: Optional[str] = None) -> structlog.BoundLogger:
    """
    Get a logger instance with optional name context.

    Args:
        name: Optional logger name (typically __name__)

    Returns:
        Logger instance
    """
    if name:
        return structlog.get_logger(logger_name=name)
    return structlog.get_logger()


# Event type constants for structured logging
class EventType:
    """Standard event types for bot logging."""

    # Trading events
    ORDER_PLACED = "ORDER_PLACED"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_CANCELED = "ORDER_CANCELED"
    ORDER_MODIFIED = "ORDER_MODIFIED"
    ORDER_REJECTED = "ORDER_REJECTED"
    TRADE_CLOSED = "TRADE_CLOSED"

    # System events
    STATUS = "STATUS"
    STARTUP = "STARTUP"
    SHUTDOWN = "SHUTDOWN"
    ERROR = "ERROR"
    WARNING = "WARNING"

    # Strategy events
    SIGNAL_GENERATED = "SIGNAL_GENERATED"
    CONVICTION_UPDATE = "CONVICTION_UPDATE"
    WEIGHT_UPDATE = "WEIGHT_UPDATE"

    # Risk events
    DRAWDOWN_BRAKE = "DRAWDOWN_BRAKE"
    RISK_LIMIT_REACHED = "RISK_LIMIT_REACHED"
    LEVERAGE_ADJUSTED = "LEVERAGE_ADJUSTED"

    # Connection events
    WEBSOCKET_CONNECTED = "WEBSOCKET_CONNECTED"
    WEBSOCKET_DISCONNECTED = "WEBSOCKET_DISCONNECTED"
    WEBSOCKET_RECONNECTING = "WEBSOCKET_RECONNECTING"
    API_ERROR = "API_ERROR"
    RATE_LIMIT_WARNING = "RATE_LIMIT_WARNING"


def log_trade_event(
    logger: structlog.BoundLogger,
    event_type: str,
    symbol: str,
    **kwargs
) -> None:
    """
    Log a trade-related event with standard fields.

    Args:
        logger: Logger instance
        event_type: Event type from EventType class
        symbol: Trading symbol
        **kwargs: Additional event-specific fields
    """
    logger.info(
        event_type,
        event_type=event_type,
        symbol=symbol,
        timestamp=datetime.utcnow().isoformat(),
        **kwargs
    )


def log_order_event(
    logger: structlog.BoundLogger,
    event_type: str,
    order_id: str,
    symbol: str,
    side: str,
    order_type: str,
    quantity: float,
    price: Optional[float] = None,
    **kwargs
) -> None:
    """
    Log an order-related event with standard fields.

    Args:
        logger: Logger instance
        event_type: Event type from EventType class
        order_id: Order ID
        symbol: Trading symbol
        side: BUY or SELL
        order_type: LIMIT, MARKET, etc.
        quantity: Order quantity
        price: Order price (optional for market orders)
        **kwargs: Additional fields
    """
    logger.info(
        event_type,
        event_type=event_type,
        order_id=order_id,
        symbol=symbol,
        side=side,
        type=order_type,
        quantity=quantity,
        price=price,
        timestamp=datetime.utcnow().isoformat(),
        **kwargs
    )


def log_system_event(
    logger: structlog.BoundLogger,
    event_type: str,
    message: str,
    **kwargs
) -> None:
    """
    Log a system event.

    Args:
        logger: Logger instance
        event_type: Event type from EventType class
        message: Event message
        **kwargs: Additional context
    """
    logger.info(
        message,
        event_type=event_type,
        timestamp=datetime.utcnow().isoformat(),
        **kwargs
    )
