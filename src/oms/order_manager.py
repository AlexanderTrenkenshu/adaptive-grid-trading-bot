"""
Order Management System - Order Manager.

Provides order state machine, validation, and lifecycle management.
"""

from typing import Dict, Optional, Callable, List
import structlog

from src.exchange.models import Order, OrderStatus
from src.exchange.exceptions import InvalidTransitionError

logger = structlog.get_logger(__name__)


class OrderStateMachine:
    """
    Order state machine for managing order lifecycle transitions.

    Valid transitions:
    - PENDING_NEW → NEW (order accepted by exchange)
    - PENDING_NEW → REJECTED (order rejected by exchange)
    - NEW → PARTIALLY_FILLED (partial execution)
    - NEW → FILLED (full execution)
    - NEW → PENDING_CANCEL (cancellation requested)
    - PARTIALLY_FILLED → FILLED (remaining quantity filled)
    - PARTIALLY_FILLED → PENDING_CANCEL (cancellation requested)
    - PENDING_CANCEL → CANCELED (cancellation confirmed)
    - NEW → CANCELED (direct cancellation, rare)
    - NEW → EXPIRED (order expired)
    """

    # Define valid state transitions
    VALID_TRANSITIONS = {
        OrderStatus.PENDING_NEW: [
            OrderStatus.NEW,
            OrderStatus.REJECTED
        ],
        OrderStatus.NEW: [
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.PENDING_CANCEL,
            OrderStatus.CANCELED,  # Direct cancellation
            OrderStatus.EXPIRED
        ],
        OrderStatus.PARTIALLY_FILLED: [
            OrderStatus.FILLED,
            OrderStatus.PENDING_CANCEL,
            OrderStatus.CANCELED  # Direct cancellation
        ],
        OrderStatus.PENDING_CANCEL: [
            OrderStatus.CANCELED
        ],
        # Terminal states (no transitions out)
        OrderStatus.FILLED: [],
        OrderStatus.CANCELED: [],
        OrderStatus.REJECTED: [],
        OrderStatus.EXPIRED: []
    }

    @classmethod
    def can_transition(cls, from_status: OrderStatus, to_status: OrderStatus) -> bool:
        """
        Check if transition is valid.

        Args:
            from_status: Current order status
            to_status: Target order status

        Returns:
            True if transition is valid
        """
        return to_status in cls.VALID_TRANSITIONS.get(from_status, [])

    @classmethod
    def validate_transition(cls, from_status: OrderStatus, to_status: OrderStatus):
        """
        Validate state transition and raise exception if invalid.

        Args:
            from_status: Current order status
            to_status: Target order status

        Raises:
            InvalidTransitionError: If transition is not allowed
        """
        if not cls.can_transition(from_status, to_status):
            raise InvalidTransitionError(
                f"Invalid order state transition: {from_status.value} → {to_status.value}"
            )

    @classmethod
    def is_terminal_state(cls, status: OrderStatus) -> bool:
        """
        Check if status is a terminal state (no further transitions).

        Args:
            status: Order status to check

        Returns:
            True if terminal state
        """
        return status in [
            OrderStatus.FILLED,
            OrderStatus.CANCELED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED
        ]

    @classmethod
    def is_active_state(cls, status: OrderStatus) -> bool:
        """
        Check if order is in active state (can be filled or canceled).

        Args:
            status: Order status to check

        Returns:
            True if active
        """
        return status in [
            OrderStatus.NEW,
            OrderStatus.PARTIALLY_FILLED
        ]


class OrderManager:
    """
    Order Manager for tracking and managing order lifecycle.

    Responsibilities:
    - Maintain in-memory order book
    - Validate state transitions
    - Process order updates from WebSocket
    - Provide order query interface
    - Emit events for order state changes

    Note: This implementation is designed for single-threaded async use.
    For multi-threaded scenarios, add appropriate locking mechanisms.
    """

    def __init__(self):
        """Initialize Order Manager."""
        self._orders: Dict[str, Order] = {}  # order_id -> Order
        self._orders_by_client_id: Dict[str, str] = {}  # client_order_id -> order_id
        self._order_callbacks: List[Callable[[Order], None]] = []

        logger.info("OrderManager initialized")

    @staticmethod
    def _parse_status(status: str | OrderStatus) -> OrderStatus:
        """
        Parse status to OrderStatus enum.

        Args:
            status: Status as string or OrderStatus enum

        Returns:
            OrderStatus enum
        """
        return OrderStatus(status) if isinstance(status, str) else status

    def register_callback(self, callback: Callable[[Order], None]):
        """
        Register callback for order state changes.

        Args:
            callback: Function to call when order state changes
        """
        self._order_callbacks.append(callback)
        logger.debug("Order callback registered", callback=callback.__name__)

    def add_order(self, order: Order):
        """
        Add new order to tracking system.

        Args:
            order: Order object to track

        Raises:
            ValueError: If order already exists
        """
        if order.order_id in self._orders:
            raise ValueError(f"Order {order.order_id} already exists")

        self._orders[order.order_id] = order
        self._orders_by_client_id[order.client_order_id] = order.order_id

        logger.info(
            "Order added to tracker",
            order_id=order.order_id,
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            side=order.side,
            status=order.status
        )

        self._emit_callback(order)

    def update_order(self, order_update: Order):
        """
        Update existing order with new state.

        Validates state transition before applying update.

        Args:
            order_update: Updated order object

        Raises:
            ValueError: If order not found
            InvalidTransitionError: If state transition is invalid
        """
        order_id = order_update.order_id
        if order_id not in self._orders:
            # Order not tracked yet, add it
            logger.warning(
                "Received update for untracked order, adding",
                order_id=order_id
            )
            self.add_order(order_update)
            return

        existing_order = self._orders[order_id]

        # Parse status strings to OrderStatus enum
        old_status = self._parse_status(existing_order.status)
        new_status = self._parse_status(order_update.status)

        # Validate state transition
        if old_status != new_status:
            OrderStateMachine.validate_transition(old_status, new_status)

            logger.info(
                "Order status transition",
                order_id=order_id,
                old_status=old_status.value,
                new_status=new_status.value,
                symbol=order_update.symbol
            )

        # Update order
        self._orders[order_id] = order_update

        self._emit_callback(order_update)

    def get_order(self, order_id: str) -> Optional[Order]:
        """
        Get order by exchange order ID.

        Args:
            order_id: Exchange order ID

        Returns:
            Order object or None if not found
        """
        return self._orders.get(order_id)

    def get_order_by_client_id(self, client_order_id: str) -> Optional[Order]:
        """
        Get order by client order ID.

        Args:
            client_order_id: Client-provided order ID

        Returns:
            Order object or None if not found
        """
        order_id = self._orders_by_client_id.get(client_order_id)
        if order_id:
            return self._orders.get(order_id)
        return None

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """
        Get all open (active) orders.

        Args:
            symbol: Optional symbol filter

        Returns:
            List of active orders
        """
        orders = []
        for order in self._orders.values():
            status = self._parse_status(order.status)
            if OrderStateMachine.is_active_state(status):
                if symbol is None or order.symbol == symbol:
                    orders.append(order)
        return orders

    def get_all_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """
        Get all tracked orders.

        Args:
            symbol: Optional symbol filter

        Returns:
            List of all orders
        """
        if symbol is None:
            return list(self._orders.values())
        return [o for o in self._orders.values() if o.symbol == symbol]

    def remove_order(self, order_id: str) -> Optional[Order]:
        """
        Remove order from tracking (e.g., after terminal state).

        Args:
            order_id: Order ID to remove

        Returns:
            Removed order or None if not found
        """
        order = self._orders.pop(order_id, None)
        if order:
            self._orders_by_client_id.pop(order.client_order_id, None)
            logger.debug("Order removed from tracker", order_id=order_id)
        return order

    def clear_terminal_orders(self, max_age_seconds: int = 3600) -> int:
        """
        Clear terminal orders older than specified age.

        Note: Currently clears ALL terminal orders regardless of age,
        since Order model doesn't track timestamps yet. The max_age_seconds
        parameter is reserved for future implementation.

        Args:
            max_age_seconds: Maximum age for terminal orders (default 1 hour)
                           Currently not implemented - all terminal orders are cleared.

        Returns:
            Number of orders cleared
        """
        terminal_orders = []
        for order_id, order in self._orders.items():
            status = self._parse_status(order.status)
            if OrderStateMachine.is_terminal_state(status):
                terminal_orders.append(order_id)

        for order_id in terminal_orders:
            self.remove_order(order_id)

        if terminal_orders:
            logger.info(
                "Cleared terminal orders",
                count=len(terminal_orders)
            )

        return len(terminal_orders)

    def _emit_callback(self, order: Order):
        """
        Emit callbacks for order state change.

        Args:
            order: Updated order
        """
        for callback in self._order_callbacks:
            try:
                callback(order)
            except Exception as e:
                logger.error(
                    "Error in order callback",
                    callback=callback.__name__,
                    error=str(e),
                    exc_info=True
                )

    @property
    def order_count(self) -> int:
        """Get total number of tracked orders."""
        return len(self._orders)

    @property
    def active_order_count(self) -> int:
        """Get number of active orders."""
        return len(self.get_open_orders())
