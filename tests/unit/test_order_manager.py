"""
Unit tests for Order Manager.
"""

import pytest
from decimal import Decimal
from datetime import datetime

from src.oms.order_manager import OrderManager, OrderStateMachine
from src.exchange.models import Order, OrderStatus
from src.exchange.exceptions import InvalidTransitionError


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def order_manager():
    """Create Order Manager instance."""
    return OrderManager()


@pytest.fixture
def sample_order():
    """Create sample order."""
    return Order(
        order_id="12345",
        client_order_id="client_123",
        symbol="BTC/USDT",
        side="BUY",
        order_type="LIMIT",
        status=OrderStatus.NEW.value,
        quantity=Decimal("0.001"),
        price=Decimal("50000.0"),
        average_fill_price=Decimal("0"),
        commission=Decimal("0"),
        commission_asset="USDT"
    )


# ============================================================================
# OrderStateMachine Tests
# ============================================================================

@pytest.mark.unit
def test_valid_transitions():
    """Test valid state transitions."""
    # PENDING_NEW → NEW
    assert OrderStateMachine.can_transition(OrderStatus.PENDING_NEW, OrderStatus.NEW)

    # PENDING_NEW → REJECTED
    assert OrderStateMachine.can_transition(OrderStatus.PENDING_NEW, OrderStatus.REJECTED)

    # NEW → PARTIALLY_FILLED
    assert OrderStateMachine.can_transition(OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED)

    # NEW → FILLED
    assert OrderStateMachine.can_transition(OrderStatus.NEW, OrderStatus.FILLED)

    # NEW → PENDING_CANCEL
    assert OrderStateMachine.can_transition(OrderStatus.NEW, OrderStatus.PENDING_CANCEL)

    # PARTIALLY_FILLED → FILLED
    assert OrderStateMachine.can_transition(OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED)

    # PENDING_CANCEL → CANCELED
    assert OrderStateMachine.can_transition(OrderStatus.PENDING_CANCEL, OrderStatus.CANCELED)


@pytest.mark.unit
def test_invalid_transitions():
    """Test invalid state transitions."""
    # Cannot go from FILLED to any state
    assert not OrderStateMachine.can_transition(OrderStatus.FILLED, OrderStatus.NEW)
    assert not OrderStateMachine.can_transition(OrderStatus.FILLED, OrderStatus.CANCELED)

    # Cannot go from CANCELED to any state
    assert not OrderStateMachine.can_transition(OrderStatus.CANCELED, OrderStatus.NEW)
    assert not OrderStateMachine.can_transition(OrderStatus.CANCELED, OrderStatus.FILLED)

    # Cannot go from REJECTED to any state
    assert not OrderStateMachine.can_transition(OrderStatus.REJECTED, OrderStatus.NEW)

    # Cannot go backwards
    assert not OrderStateMachine.can_transition(OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED)
    assert not OrderStateMachine.can_transition(OrderStatus.PARTIALLY_FILLED, OrderStatus.NEW)


@pytest.mark.unit
def test_validate_transition_success():
    """Test successful transition validation."""
    # Should not raise exception
    OrderStateMachine.validate_transition(OrderStatus.NEW, OrderStatus.FILLED)
    OrderStateMachine.validate_transition(OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED)


@pytest.mark.unit
def test_validate_transition_failure():
    """Test failed transition validation."""
    with pytest.raises(InvalidTransitionError):
        OrderStateMachine.validate_transition(OrderStatus.FILLED, OrderStatus.NEW)

    with pytest.raises(InvalidTransitionError):
        OrderStateMachine.validate_transition(OrderStatus.CANCELED, OrderStatus.FILLED)


@pytest.mark.unit
def test_terminal_states():
    """Test terminal state detection."""
    assert OrderStateMachine.is_terminal_state(OrderStatus.FILLED)
    assert OrderStateMachine.is_terminal_state(OrderStatus.CANCELED)
    assert OrderStateMachine.is_terminal_state(OrderStatus.REJECTED)
    assert OrderStateMachine.is_terminal_state(OrderStatus.EXPIRED)

    assert not OrderStateMachine.is_terminal_state(OrderStatus.NEW)
    assert not OrderStateMachine.is_terminal_state(OrderStatus.PARTIALLY_FILLED)


@pytest.mark.unit
def test_active_states():
    """Test active state detection."""
    assert OrderStateMachine.is_active_state(OrderStatus.NEW)
    assert OrderStateMachine.is_active_state(OrderStatus.PARTIALLY_FILLED)

    assert not OrderStateMachine.is_active_state(OrderStatus.FILLED)
    assert not OrderStateMachine.is_active_state(OrderStatus.CANCELED)


# ============================================================================
# OrderManager Tests
# ============================================================================

@pytest.mark.unit
def test_order_manager_initialization(order_manager):
    """Test Order Manager initialization."""
    assert order_manager.order_count == 0
    assert order_manager.active_order_count == 0


@pytest.mark.unit
def test_add_order(order_manager, sample_order):
    """Test adding order to tracker."""
    order_manager.add_order(sample_order)

    assert order_manager.order_count == 1
    assert order_manager.active_order_count == 1

    retrieved_order = order_manager.get_order(sample_order.order_id)
    assert retrieved_order is not None
    assert retrieved_order.order_id == sample_order.order_id
    assert retrieved_order.symbol == "BTC/USDT"


@pytest.mark.unit
def test_add_duplicate_order(order_manager, sample_order):
    """Test adding duplicate order raises error."""
    order_manager.add_order(sample_order)

    with pytest.raises(ValueError, match="already exists"):
        order_manager.add_order(sample_order)


@pytest.mark.unit
def test_get_order_by_client_id(order_manager, sample_order):
    """Test retrieving order by client ID."""
    order_manager.add_order(sample_order)

    retrieved_order = order_manager.get_order_by_client_id(sample_order.client_order_id)
    assert retrieved_order is not None
    assert retrieved_order.order_id == sample_order.order_id


@pytest.mark.unit
def test_update_order(order_manager, sample_order):
    """Test updating order state."""
    order_manager.add_order(sample_order)

    # Create updated order
    updated_order = Order(
        order_id=sample_order.order_id,
        client_order_id=sample_order.client_order_id,
        symbol=sample_order.symbol,
        side=sample_order.side,
        order_type=sample_order.order_type,
        status=OrderStatus.FILLED.value,
        quantity=sample_order.quantity,
        price=sample_order.price,
        average_fill_price=Decimal("50000.0"),
        commission=Decimal("0.05"),
        commission_asset="USDT"
    )

    order_manager.update_order(updated_order)

    retrieved_order = order_manager.get_order(sample_order.order_id)
    assert retrieved_order.status == OrderStatus.FILLED.value
    assert retrieved_order.average_fill_price == Decimal("50000.0")


@pytest.mark.unit
def test_update_order_invalid_transition(order_manager, sample_order):
    """Test updating order with invalid transition raises error."""
    # Set order to FILLED
    filled_order = Order(
        order_id=sample_order.order_id,
        client_order_id=sample_order.client_order_id,
        symbol=sample_order.symbol,
        side=sample_order.side,
        order_type=sample_order.order_type,
        status=OrderStatus.FILLED.value,
        quantity=sample_order.quantity,
        price=sample_order.price,
        average_fill_price=Decimal("50000.0"),
        commission=Decimal("0.05"),
        commission_asset="USDT"
    )
    order_manager.add_order(filled_order)

    # Try to transition back to NEW
    invalid_update = Order(
        order_id=sample_order.order_id,
        client_order_id=sample_order.client_order_id,
        symbol=sample_order.symbol,
        side=sample_order.side,
        order_type=sample_order.order_type,
        status=OrderStatus.NEW.value,
        quantity=sample_order.quantity,
        price=sample_order.price,
        average_fill_price=Decimal("0"),
        commission=Decimal("0"),
        commission_asset="USDT"
    )

    with pytest.raises(InvalidTransitionError):
        order_manager.update_order(invalid_update)


@pytest.mark.unit
def test_update_untracked_order(order_manager):
    """Test updating untracked order adds it."""
    new_order = Order(
        order_id="99999",
        client_order_id="client_999",
        symbol="ETH/USDT",
        side="SELL",
        order_type="MARKET",
        status=OrderStatus.FILLED.value,
        quantity=Decimal("1.0"),
        price=None,
        average_fill_price=Decimal("3000.0"),
        commission=Decimal("3.0"),
        commission_asset="USDT"
    )

    order_manager.update_order(new_order)

    assert order_manager.order_count == 1
    retrieved_order = order_manager.get_order("99999")
    assert retrieved_order is not None


@pytest.mark.unit
def test_get_open_orders(order_manager):
    """Test retrieving open orders."""
    # Add active orders
    order1 = Order(
        order_id="1",
        client_order_id="c1",
        symbol="BTC/USDT",
        side="BUY",
        order_type="LIMIT",
        status=OrderStatus.NEW.value,
        quantity=Decimal("0.001"),
        price=Decimal("50000.0"),
        average_fill_price=Decimal("0"),
        commission=Decimal("0"),
        commission_asset="USDT"
    )
    order_manager.add_order(order1)

    order2 = Order(
        order_id="2",
        client_order_id="c2",
        symbol="ETH/USDT",
        side="SELL",
        order_type="LIMIT",
        status=OrderStatus.PARTIALLY_FILLED.value,
        quantity=Decimal("1.0"),
        price=Decimal("3000.0"),
        average_fill_price=Decimal("3000.0"),
        commission=Decimal("1.5"),
        commission_asset="USDT"
    )
    order_manager.add_order(order2)

    # Add terminal order
    order3 = Order(
        order_id="3",
        client_order_id="c3",
        symbol="BTC/USDT",
        side="BUY",
        order_type="MARKET",
        status=OrderStatus.FILLED.value,
        quantity=Decimal("0.001"),
        price=None,
        average_fill_price=Decimal("50100.0"),
        commission=Decimal("0.05"),
        commission_asset="USDT"
    )
    order_manager.add_order(order3)

    # Get all open orders
    open_orders = order_manager.get_open_orders()
    assert len(open_orders) == 2
    assert order1 in open_orders
    assert order2 in open_orders
    assert order3 not in open_orders

    # Get open orders by symbol
    btc_orders = order_manager.get_open_orders(symbol="BTC/USDT")
    assert len(btc_orders) == 1
    assert btc_orders[0].order_id == "1"


@pytest.mark.unit
def test_remove_order(order_manager, sample_order):
    """Test removing order from tracker."""
    order_manager.add_order(sample_order)
    assert order_manager.order_count == 1

    removed_order = order_manager.remove_order(sample_order.order_id)
    assert removed_order is not None
    assert removed_order.order_id == sample_order.order_id
    assert order_manager.order_count == 0

    # Verify order is gone
    assert order_manager.get_order(sample_order.order_id) is None
    assert order_manager.get_order_by_client_id(sample_order.client_order_id) is None


@pytest.mark.unit
def test_order_callback(order_manager, sample_order):
    """Test order callback invocation."""
    callback_invocations = []

    def callback(order: Order):
        callback_invocations.append(order)

    order_manager.register_callback(callback)
    order_manager.add_order(sample_order)

    assert len(callback_invocations) == 1
    assert callback_invocations[0].order_id == sample_order.order_id


@pytest.mark.unit
def test_callback_error_handling(order_manager, sample_order):
    """Test that callback errors don't crash OrderManager."""
    def failing_callback(order: Order):
        raise ValueError("Test error")

    order_manager.register_callback(failing_callback)

    # Should not raise exception
    order_manager.add_order(sample_order)

    assert order_manager.order_count == 1


@pytest.mark.unit
def test_clear_terminal_orders(order_manager):
    """Test clearing terminal orders."""
    # Add mix of active and terminal orders
    active_order = Order(
        order_id="1",
        client_order_id="c1",
        symbol="BTC/USDT",
        side="BUY",
        order_type="LIMIT",
        status=OrderStatus.NEW.value,
        quantity=Decimal("0.001"),
        price=Decimal("50000.0"),
        average_fill_price=Decimal("0"),
        commission=Decimal("0"),
        commission_asset="USDT"
    )
    order_manager.add_order(active_order)

    filled_order = Order(
        order_id="2",
        client_order_id="c2",
        symbol="BTC/USDT",
        side="BUY",
        order_type="MARKET",
        status=OrderStatus.FILLED.value,
        quantity=Decimal("0.001"),
        price=None,
        average_fill_price=Decimal("50000.0"),
        commission=Decimal("0.05"),
        commission_asset="USDT"
    )
    order_manager.add_order(filled_order)

    canceled_order = Order(
        order_id="3",
        client_order_id="c3",
        symbol="ETH/USDT",
        side="SELL",
        order_type="LIMIT",
        status=OrderStatus.CANCELED.value,
        quantity=Decimal("1.0"),
        price=Decimal("3000.0"),
        average_fill_price=Decimal("0"),
        commission=Decimal("0"),
        commission_asset="USDT"
    )
    order_manager.add_order(canceled_order)

    assert order_manager.order_count == 3

    # Clear terminal orders
    order_manager.clear_terminal_orders()

    assert order_manager.order_count == 1
    assert order_manager.get_order("1") is not None  # Active order remains
    assert order_manager.get_order("2") is None  # Filled order removed
    assert order_manager.get_order("3") is None  # Canceled order removed
