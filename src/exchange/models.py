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

    Minimal, essential fields for order tracking in high-liquidity markets.
    Same structure for REST API and WebSocket data.

    For MARKET orders:
        - price = None
        - average_fill_price = actual execution price

    For LIMIT orders:
        - price = limit price specified when placing order
        - average_fill_price = actual execution price (0 if not filled yet)

    See docs/DATA_MODELS.md for detailed usage examples.
    """
    # Identifiers
    order_id: str                    # Exchange order ID
    client_order_id: str             # Client-provided order ID

    # Order details
    symbol: str                      # Normalized symbol
    side: str                        # "BUY" or "SELL"
    order_type: str                  # "LIMIT" or "MARKET"
    status: str                      # "NEW", "FILLED", "CANCELED", "REJECTED"

    # Quantities and pricing
    quantity: Decimal                # Original quantity
    price: Optional[Decimal]         # Limit price (None for MARKET orders)
    average_fill_price: Decimal      # Average fill price (0 if not filled yet)

    # Financials
    commission: Decimal              # Trading fee paid
    commission_asset: str            # Fee currency

    def __post_init__(self):
        """Ensure Decimal types."""
        if not isinstance(self.quantity, Decimal):
            self.quantity = Decimal(str(self.quantity))
        if self.price is not None and not isinstance(self.price, Decimal):
            self.price = Decimal(str(self.price))
        if not isinstance(self.average_fill_price, Decimal):
            self.average_fill_price = Decimal(str(self.average_fill_price))
        if not isinstance(self.commission, Decimal):
            self.commission = Decimal(str(self.commission))

    @property
    def is_filled(self) -> bool:
        """Check if order is fully filled."""
        return self.status == "FILLED"

    @property
    def is_active(self) -> bool:
        """Check if order is active (can be filled)."""
        return self.status == "NEW"


@dataclass
class Ticker:
    """
    Normalized ticker data.

    Minimal, essential fields for order placement and monitoring.
    Same structure for REST API and WebSocket data.
    """
    symbol: str
    last_price: Decimal
    bid_price: Decimal
    ask_price: Decimal
    bid_qty: Decimal
    ask_qty: Decimal
    timestamp: datetime

    def __post_init__(self):
        """Ensure Decimal types."""
        for field_name in ['last_price', 'bid_price', 'ask_price', 'bid_qty', 'ask_qty']:
            value = getattr(self, field_name)
            if not isinstance(value, Decimal):
                setattr(self, field_name, Decimal(str(value)))


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
    """
    Normalized OHLCV candle data.

    Minimal, essential fields for trading decisions.
    Same structure for REST API and WebSocket data.
    """
    symbol: str
    interval: str                    # "1m", "5m", "1h", etc.
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal                  # Base asset volume

    def __post_init__(self):
        """Ensure Decimal types."""
        for field_name in ['open', 'high', 'low', 'close', 'volume']:
            value = getattr(self, field_name)
            if not isinstance(value, Decimal):
                setattr(self, field_name, Decimal(str(value)))


@dataclass
class Trade:
    """
    Trade data (individual trade execution).

    Used for real-time trade streams from WebSocket.
    """
    symbol: str
    price: Decimal
    quantity: Decimal
    time: datetime

    def __post_init__(self):
        """Ensure Decimal types."""
        if not isinstance(self.price, Decimal):
            self.price = Decimal(str(self.price))
        if not isinstance(self.quantity, Decimal):
            self.quantity = Decimal(str(self.quantity))


@dataclass
class AccountBalance:
    """
    Balance data from account update.

    Used in AccountUpdate from WebSocket user data stream.
    """
    asset: str
    wallet_balance: Decimal
    cross_wallet_balance: Decimal

    def __post_init__(self):
        """Ensure Decimal types."""
        if not isinstance(self.wallet_balance, Decimal):
            self.wallet_balance = Decimal(str(self.wallet_balance))
        if not isinstance(self.cross_wallet_balance, Decimal):
            self.cross_wallet_balance = Decimal(str(self.cross_wallet_balance))


@dataclass
class AccountPosition:
    """
    Position data from account update.

    Used in AccountUpdate from WebSocket user data stream.
    """
    symbol: str
    position_amount: Decimal
    entry_price: Decimal
    unrealized_pnl: Decimal
    position_side: str  # "BOTH", "LONG", or "SHORT"

    def __post_init__(self):
        """Ensure Decimal types."""
        if not isinstance(self.position_amount, Decimal):
            self.position_amount = Decimal(str(self.position_amount))
        if not isinstance(self.entry_price, Decimal):
            self.entry_price = Decimal(str(self.entry_price))
        if not isinstance(self.unrealized_pnl, Decimal):
            self.unrealized_pnl = Decimal(str(self.unrealized_pnl))


@dataclass
class AccountUpdate:
    """
    Complete account state update from WebSocket.

    Emitted when account state changes (order fills, funding fees, etc.).
    """
    event_time: datetime
    transaction_time: datetime
    balances: List[AccountBalance]
    positions: List[AccountPosition]
    reason: str  # Update reason (e.g., "ORDER", "FUNDING_FEE", "WITHDRAW")
