"""
Normalized data models for exchange-agnostic operations.

These models provide a standardized interface across different exchanges,
ensuring that the bot logic remains independent of exchange-specific formats.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from decimal import Decimal
from enum import Enum


class OrderStatus(Enum):
    """Normalized order status across exchanges."""
    PENDING_NEW = "PENDING_NEW"      # Order submitted, awaiting confirmation
    NEW = "NEW"                       # Order accepted by exchange
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    PENDING_CANCEL = "PENDING_CANCEL"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class PositionSide(Enum):
    """Position side for futures/margin trading."""
    LONG = "LONG"
    SHORT = "SHORT"
    BOTH = "BOTH"  # Hedge mode


@dataclass
class SymbolInfo:
    """
    Normalized symbol information across exchanges.

    Exchange-specific data is stored in `raw_data` field.
    """
    symbol: str                      # Normalized symbol (e.g., "BTC/USDT")
    base_asset: str                  # e.g., "BTC"
    quote_asset: str                 # e.g., "USDT"

    # Trading constraints
    min_quantity: Decimal
    max_quantity: Decimal
    quantity_step: Decimal           # Lot size step

    min_price: Decimal
    max_price: Decimal
    price_step: Decimal              # Tick size

    min_notional: Decimal            # Minimum order value

    # Market type
    is_spot: bool
    is_futures: bool
    is_margin: bool

    # Status
    is_trading: bool

    # Exchange-specific data
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Ensure Decimal types for precision."""
        if not isinstance(self.min_quantity, Decimal):
            self.min_quantity = Decimal(str(self.min_quantity))
        if not isinstance(self.max_quantity, Decimal):
            self.max_quantity = Decimal(str(self.max_quantity))
        if not isinstance(self.quantity_step, Decimal):
            self.quantity_step = Decimal(str(self.quantity_step))
        if not isinstance(self.min_price, Decimal):
            self.min_price = Decimal(str(self.min_price))
        if not isinstance(self.max_price, Decimal):
            self.max_price = Decimal(str(self.max_price))
        if not isinstance(self.price_step, Decimal):
            self.price_step = Decimal(str(self.price_step))
        if not isinstance(self.min_notional, Decimal):
            self.min_notional = Decimal(str(self.min_notional))


@dataclass
class Balance:
    """Normalized account balance."""
    asset: str
    free: Decimal                    # Available balance
    locked: Decimal                  # Locked in orders
    total: Decimal                   # Total balance

    def __post_init__(self):
        if not isinstance(self.free, Decimal):
            self.free = Decimal(str(self.free))
        if not isinstance(self.locked, Decimal):
            self.locked = Decimal(str(self.locked))
        if not isinstance(self.total, Decimal):
            self.total = Decimal(str(self.total))


@dataclass
class Position:
    """Normalized futures position."""
    symbol: str
    side: PositionSide
    quantity: Decimal                # Position size (abs value)
    entry_price: Decimal             # Average entry price
    mark_price: Decimal              # Current mark price
    unrealized_pnl: Decimal
    leverage: int

    # Optional fields
    liquidation_price: Optional[Decimal] = None
    margin: Optional[Decimal] = None

    # Exchange-specific data
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.quantity, Decimal):
            self.quantity = Decimal(str(self.quantity))
        if not isinstance(self.entry_price, Decimal):
            self.entry_price = Decimal(str(self.entry_price))
        if not isinstance(self.mark_price, Decimal):
            self.mark_price = Decimal(str(self.mark_price))
        if not isinstance(self.unrealized_pnl, Decimal):
            self.unrealized_pnl = Decimal(str(self.unrealized_pnl))
        if self.liquidation_price and not isinstance(self.liquidation_price, Decimal):
            self.liquidation_price = Decimal(str(self.liquidation_price))
        if self.margin and not isinstance(self.margin, Decimal):
            self.margin = Decimal(str(self.margin))


@dataclass
class Order:
    """
    Normalized order representation.

    This model is exchange-agnostic and used throughout the bot.
    """
    # Identifiers
    order_id: str                    # Exchange order ID
    client_order_id: Optional[str]   # Client-provided ID

    # Order details
    symbol: str                      # Normalized symbol
    side: str                        # "BUY" or "SELL"
    order_type: str                  # "LIMIT", "MARKET", etc.
    status: OrderStatus

    # Quantities
    quantity: Decimal                # Original quantity
    executed_qty: Decimal            # Filled quantity
    remaining_qty: Decimal           # Unfilled quantity

    # Pricing
    price: Optional[Decimal]         # Order price (None for MARKET)
    avg_price: Optional[Decimal]     # Average fill price
    stop_price: Optional[Decimal]    # Stop/trigger price

    # Financials
    cumulative_quote_qty: Decimal    # Total quote asset traded
    commission: Decimal              # Trading fee paid
    commission_asset: str            # Fee currency

    # Metadata
    time_in_force: str               # "GTC", "IOC", "FOK"
    created_at: datetime
    updated_at: datetime

    # Exchange-specific data
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Ensure Decimal types and calculated fields."""
        if not isinstance(self.quantity, Decimal):
            self.quantity = Decimal(str(self.quantity))
        if not isinstance(self.executed_qty, Decimal):
            self.executed_qty = Decimal(str(self.executed_qty))

        # Calculate remaining qty
        self.remaining_qty = self.quantity - self.executed_qty

        if self.price and not isinstance(self.price, Decimal):
            self.price = Decimal(str(self.price))
        if self.avg_price and not isinstance(self.avg_price, Decimal):
            self.avg_price = Decimal(str(self.avg_price))
        if self.stop_price and not isinstance(self.stop_price, Decimal):
            self.stop_price = Decimal(str(self.stop_price))
        if not isinstance(self.cumulative_quote_qty, Decimal):
            self.cumulative_quote_qty = Decimal(str(self.cumulative_quote_qty))
        if not isinstance(self.commission, Decimal):
            self.commission = Decimal(str(self.commission))

    @property
    def is_filled(self) -> bool:
        """Check if order is fully filled."""
        return self.status == OrderStatus.FILLED

    @property
    def is_active(self) -> bool:
        """Check if order is active (can be filled)."""
        return self.status in (OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED)

    @property
    def fill_percentage(self) -> float:
        """Calculate fill percentage."""
        if self.quantity == 0:
            return 0.0
        return float((self.executed_qty / self.quantity) * 100)


@dataclass
class Ticker:
    """Normalized 24hr ticker data."""
    symbol: str
    last_price: Decimal
    bid_price: Decimal
    ask_price: Decimal
    volume_24h: Decimal              # Base asset volume
    quote_volume_24h: Decimal        # Quote asset volume
    price_change_24h: Decimal
    price_change_pct_24h: Decimal
    high_24h: Decimal
    low_24h: Decimal
    timestamp: datetime


@dataclass
class OrderBook:
    """Normalized order book snapshot."""
    symbol: str
    bids: List[tuple[Decimal, Decimal]]  # [(price, quantity), ...]
    asks: List[tuple[Decimal, Decimal]]
    timestamp: datetime

    @property
    def best_bid(self) -> Optional[Decimal]:
        """Get best bid price."""
        return self.bids[0][0] if self.bids else None

    @property
    def best_ask(self) -> Optional[Decimal]:
        """Get best ask price."""
        return self.asks[0][0] if self.asks else None

    @property
    def spread(self) -> Optional[Decimal]:
        """Calculate bid-ask spread."""
        if self.best_bid and self.best_ask:
            return self.best_ask - self.best_bid
        return None


@dataclass
class Candle:
    """Normalized OHLCV candle data."""
    symbol: str
    interval: str                    # "1m", "5m", "1h", etc.
    open_time: datetime
    close_time: datetime

    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal                  # Base asset volume

    quote_volume: Decimal            # Quote asset volume
    trades: int                      # Number of trades

    def __post_init__(self):
        """Ensure Decimal types."""
        for field_name in ['open', 'high', 'low', 'close', 'volume', 'quote_volume']:
            value = getattr(self, field_name)
            if not isinstance(value, Decimal):
                setattr(self, field_name, Decimal(str(value)))
