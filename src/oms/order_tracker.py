"""
Order Management System - Order Tracker.

Provides order reconciliation between local state and exchange state.
"""

from typing import Dict, Any
import structlog

from src.exchange.gateway import ExchangeGateway
from src.exchange.models import Order
from .order_manager import OrderManager

logger = structlog.get_logger(__name__)


class OrderTracker:
    """
    Order Tracker for reconciliation between local and exchange state.

    Responsibilities:
    - Sync local orders with exchange on startup
    - Detect and resolve order state discrepancies
    - Handle stray orders (exist on exchange but not locally)
    """

    def __init__(self, order_manager: OrderManager, gateway: ExchangeGateway):
        """
        Initialize Order Tracker.

        Args:
            order_manager: Order manager instance
            gateway: Exchange gateway instance
        """
        self.order_manager = order_manager
        self.gateway = gateway

        logger.info("OrderTracker initialized")

    async def reconcile_orders(self, symbol: str = None) -> Dict[str, Any]:
        """
        Reconcile local orders with exchange state.

        Fetches open orders from exchange and compares with local state.
        Resolves discrepancies by trusting exchange as source of truth.

        Args:
            symbol: Optional symbol to reconcile (None for all)

        Returns:
            Reconciliation report with statistics
        """
        logger.info("Starting order reconciliation", symbol=symbol)

        # Get open orders from exchange
        exchange_orders = await self.gateway.get_open_orders(symbol)
        exchange_order_ids = {o.order_id for o in exchange_orders}

        # Get local orders
        local_orders = self.order_manager.get_open_orders(symbol)
        local_order_ids = {o.order_id for o in local_orders}

        # Find discrepancies
        missing_locally = exchange_order_ids - local_order_ids  # On exchange but not local
        missing_on_exchange = local_order_ids - exchange_order_ids  # Local but not on exchange
        common_orders = exchange_order_ids & local_order_ids

        report = {
            "total_exchange_orders": len(exchange_orders),
            "total_local_orders": len(local_orders),
            "missing_locally": len(missing_locally),
            "missing_on_exchange": len(missing_on_exchange),
            "common_orders": len(common_orders),
            "updates_applied": 0
        }

        # Create lookup dict for efficient access
        exchange_orders_dict = {o.order_id: o for o in exchange_orders}

        # Add missing orders to local tracking
        for order_id in missing_locally:
            exchange_order = exchange_orders_dict[order_id]
            self.order_manager.add_order(exchange_order)
            logger.warning(
                "Added stray order from exchange",
                order_id=order_id,
                symbol=exchange_order.symbol,
                side=exchange_order.side
            )

        report["updates_applied"] += len(missing_locally)

        # Mark local orders as potentially canceled if not on exchange
        for order_id in missing_on_exchange:
            local_order = self.order_manager.get_order(order_id)
            if local_order:
                logger.warning(
                    "Local order not found on exchange, may be filled or canceled",
                    order_id=order_id,
                    symbol=local_order.symbol,
                    status=local_order.status
                )
                # Query specific order status from exchange
                try:
                    order_status = await self.gateway.get_order_status(
                        local_order.symbol,
                        order_id=order_id
                    )
                    self.order_manager.update_order(order_status)
                    report["updates_applied"] += 1
                except Exception as e:
                    logger.error(
                        "Failed to query order status",
                        order_id=order_id,
                        error=str(e)
                    )

        # Update common orders with latest state
        for order_id in common_orders:
            exchange_order = exchange_orders_dict[order_id]
            local_order = self.order_manager.get_order(order_id)

            # Compare and update if different
            if local_order and local_order.status != exchange_order.status:
                self.order_manager.update_order(exchange_order)
                report["updates_applied"] += 1
                logger.info(
                    "Updated order from exchange",
                    order_id=order_id,
                    old_status=local_order.status,
                    new_status=exchange_order.status
                )

        logger.info(
            "Order reconciliation complete",
            **report
        )

        return report

    async def sync_all_orders(self) -> Dict[str, Any]:
        """
        Perform full order synchronization across all symbols.

        Returns:
            Sync report with statistics
        """
        logger.info("Starting full order synchronization")

        # Get all open orders from exchange (all symbols)
        exchange_orders = await self.gateway.get_open_orders()

        # Clear local orders and reload from exchange
        # (Alternative: incremental sync like reconcile_orders)
        local_orders = self.order_manager.get_all_orders()

        report = {
            "total_exchange_orders": len(exchange_orders),
            "total_local_orders_before": len(local_orders),
            "orders_added": 0,
            "orders_updated": 0
        }

        # Process each exchange order
        for exchange_order in exchange_orders:
            local_order = self.order_manager.get_order(exchange_order.order_id)

            if local_order is None:
                # Add new order
                self.order_manager.add_order(exchange_order)
                report["orders_added"] += 1
            elif local_order.status != exchange_order.status:
                # Update existing order
                self.order_manager.update_order(exchange_order)
                report["orders_updated"] += 1

        report["total_local_orders_after"] = self.order_manager.order_count

        logger.info(
            "Full order synchronization complete",
            **report
        )

        return report

    async def cancel_stray_orders(self, symbol: str = None) -> int:
        """
        Cancel all orders on exchange that are not in local tracking.

        Use with caution! This will cancel orders created outside this bot.

        Args:
            symbol: Optional symbol filter

        Returns:
            Number of orders canceled
        """
        logger.warning(
            "Canceling stray orders on exchange",
            symbol=symbol
        )

        # Get orders from exchange
        exchange_orders = await self.gateway.get_open_orders(symbol)
        local_order_ids = {o.order_id for o in self.order_manager.get_open_orders(symbol)}

        canceled_count = 0
        for order in exchange_orders:
            if order.order_id not in local_order_ids:
                try:
                    await self.gateway.cancel_order(order.symbol, order_id=order.order_id)
                    canceled_count += 1
                    logger.info(
                        "Canceled stray order",
                        order_id=order.order_id,
                        symbol=order.symbol
                    )
                except Exception as e:
                    logger.error(
                        "Failed to cancel stray order",
                        order_id=order.order_id,
                        error=str(e)
                    )

        logger.info(
            "Stray order cancellation complete",
            canceled_count=canceled_count
        )

        return canceled_count
