"""
WebSocket data parser for converting raw Binance data to typed models.

This module handles parsing of raw WebSocket messages into normalized data models.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List
import logging

from .models import (
    Candle,
    Trade,
    Ticker,
    Order,
    AccountBalance,
    AccountPosition,
    AccountUpdate
)
from .exchange_config import normalize_symbol, ExchangeType

logger = logging.getLogger(__name__)


class WebSocketParser:
    """Parser for Binance WebSocket messages."""

    def __init__(self, exchange_type: ExchangeType):
        """
        Initialize parser.

        Args:
            exchange_type: Exchange type (SPOT or FUTURES)
        """
        self.exchange_type = exchange_type

    def parse_kline(self, data: Dict[str, Any]) -> Optional[Candle]:
        """
        Parse kline (candlestick) data.

        Only returns Candle if the candle is closed (x: true).
        For open candles, returns None.

        Args:
            data: Raw kline message from WebSocket

        Returns:
            Candle object if candle is closed, None otherwise
        """
        try:
            kline = data.get('k', {})

            # CRITICAL: Only emit closed candles
            if not kline.get('x', False):
                return None

            symbol = normalize_symbol(data['s'], self.exchange_type)

            return Candle(
                symbol=symbol,
                interval=kline['i'],
                open_time=datetime.fromtimestamp(kline['t'] / 1000),
                close_time=datetime.fromtimestamp(kline['T'] / 1000),
                open=Decimal(kline['o']),
                high=Decimal(kline['h']),
                low=Decimal(kline['l']),
                close=Decimal(kline['c']),
                volume=Decimal(kline['v'])
            )

        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Failed to parse kline data: {e}", exc_info=True)
            return None

    def parse_trade(self, data: Dict[str, Any]) -> Optional[Trade]:
        """
        Parse trade data.

        Args:
            data: Raw trade message from WebSocket

        Returns:
            Trade object or None if parsing fails
        """
        try:
            symbol = normalize_symbol(data['s'], self.exchange_type)

            return Trade(
                symbol=symbol,
                price=Decimal(data['p']),
                quantity=Decimal(data['q']),
                time=datetime.fromtimestamp(data['T'] / 1000)
            )

        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Failed to parse trade data: {e}", exc_info=True)
            return None

    def parse_book_ticker(self, data: Dict[str, Any]) -> Optional[Ticker]:
        """
        Parse book ticker data (best bid/ask).

        Args:
            data: Raw book ticker message from WebSocket

        Returns:
            Ticker object or None if parsing fails
        """
        try:
            symbol = normalize_symbol(data['s'], self.exchange_type)

            # For bookTicker, we don't have last_price directly
            # Use best bid as last_price (or could use midpoint)
            last_price = Decimal(data['b'])

            return Ticker(
                symbol=symbol,
                last_price=last_price,
                bid_price=Decimal(data['b']),
                ask_price=Decimal(data['a']),
                bid_qty=Decimal(data['B']),
                ask_qty=Decimal(data['A']),
                timestamp=datetime.utcnow()
            )

        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Failed to parse book ticker data: {e}", exc_info=True)
            return None

    def parse_order_update(self, data: Dict[str, Any]) -> Optional[Order]:
        """
        Parse order update from user data stream.

        Handles ORDER_TRADE_UPDATE event (Futures) and executionReport (Spot).

        Args:
            data: Raw order update message from WebSocket

        Returns:
            Order object or None if parsing fails
        """
        try:
            # Futures uses 'o' for order data, Spot uses direct fields
            order_data = data.get('o', data)

            symbol = normalize_symbol(order_data['s'], self.exchange_type)

            # Order type
            order_type = order_data['o']  # "LIMIT", "MARKET", etc.

            # Price: None for MARKET orders, limit price for LIMIT orders
            price = None
            if order_type == "LIMIT":
                price = Decimal(order_data['p']) if order_data['p'] != '0' else None

            # Average fill price
            avg_price = Decimal(order_data.get('ap', '0'))
            if avg_price == 0:
                avg_price = Decimal(order_data.get('L', '0'))  # Last filled price

            # Commission
            commission = Decimal(order_data.get('n', '0'))
            commission_asset = order_data.get('N', 'USDT')

            return Order(
                order_id=str(order_data['i']),
                client_order_id=order_data['c'],
                symbol=symbol,
                side=order_data['S'],
                order_type=order_type,
                status=order_data['X'],  # Order status
                quantity=Decimal(order_data['q']),
                price=price,
                average_fill_price=avg_price,
                commission=commission,
                commission_asset=commission_asset
            )

        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Failed to parse order update: {e}", exc_info=True)
            return None

    def parse_account_update(self, data: Dict[str, Any]) -> Optional[AccountUpdate]:
        """
        Parse account update from user data stream (Futures).

        Args:
            data: Raw account update message from WebSocket

        Returns:
            AccountUpdate object or None if parsing fails
        """
        try:
            update_data = data.get('a', {})

            # Parse balances
            balances = []
            for balance_data in update_data.get('B', []):
                balances.append(AccountBalance(
                    asset=balance_data['a'],
                    wallet_balance=Decimal(balance_data['wb']),
                    cross_wallet_balance=Decimal(balance_data['cw'])
                ))

            # Parse positions
            positions = []
            for position_data in update_data.get('P', []):
                positions.append(AccountPosition(
                    symbol=normalize_symbol(position_data['s'], self.exchange_type),
                    position_amount=Decimal(position_data['pa']),
                    entry_price=Decimal(position_data['ep']),
                    unrealized_pnl=Decimal(position_data['up']),
                    position_side=position_data['ps']
                ))

            return AccountUpdate(
                event_time=datetime.fromtimestamp(data['E'] / 1000),
                transaction_time=datetime.fromtimestamp(data['T'] / 1000),
                balances=balances,
                positions=positions,
                reason=update_data.get('m', 'UNKNOWN')
            )

        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Failed to parse account update: {e}", exc_info=True)
            return None

    def parse_user_data(self, data: Dict[str, Any]) -> Optional[Any]:
        """
        Parse user data stream message.

        Routes to appropriate parser based on event type.

        Args:
            data: Raw user data message from WebSocket

        Returns:
            Parsed model (Order or AccountUpdate) or None
        """
        event_type = data.get('e')

        if event_type == 'ORDER_TRADE_UPDATE':
            # Futures order update
            return self.parse_order_update(data)
        elif event_type == 'executionReport':
            # Spot order update
            return self.parse_order_update(data)
        elif event_type == 'ACCOUNT_UPDATE':
            # Futures account update
            return self.parse_account_update(data)
        elif event_type == 'outboundAccountPosition':
            # Spot account update (balance changes)
            # For now, return raw data (can be enhanced later)
            logger.debug(f"Spot account position update: {data}")
            return data
        else:
            logger.warning(f"Unknown user data event type: {event_type}")
            return None
