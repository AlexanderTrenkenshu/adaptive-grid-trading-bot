"""
Rate limiter for exchange API requests.

This module implements exchange-agnostic rate limiting using token bucket algorithm
and configurable limits per exchange type.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, Optional
from datetime import datetime, timedelta

from .exchange_config import ExchangeConfig, ExchangeType, get_exchange_config
from ..utils.logger import get_logger


logger = get_logger(__name__)


@dataclass
class RequestBucket:
    """Token bucket for rate limiting."""
    capacity: int                    # Maximum tokens
    refill_rate: float               # Tokens per second
    tokens: float = field(init=False)  # Current tokens
    last_refill: float = field(init=False)  # Last refill timestamp

    def __post_init__(self):
        self.tokens = float(self.capacity)
        self.last_refill = time.time()

    def refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill

        # Add tokens based on refill rate
        self.tokens = min(
            self.capacity,
            self.tokens + (elapsed * self.refill_rate)
        )

        self.last_refill = now

    def consume(self, tokens: int = 1) -> bool:
        """
        Attempt to consume tokens.

        Args:
            tokens: Number of tokens to consume

        Returns:
            True if tokens were consumed, False if insufficient tokens
        """
        self.refill()

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        else:
            return False

    def wait_time(self, tokens: int = 1) -> float:
        """
        Calculate wait time until tokens available.

        Args:
            tokens: Number of tokens needed

        Returns:
            Wait time in seconds
        """
        self.refill()

        if self.tokens >= tokens:
            return 0.0

        tokens_needed = tokens - self.tokens
        return tokens_needed / self.refill_rate


class RateLimiter:
    """
    Exchange-agnostic rate limiter.

    Uses token bucket algorithm to enforce:
    - Request rate limits (requests per minute)
    - Weight-based limits (API weight per minute)
    - Order rate limits (orders per second)
    """

    def __init__(self, exchange_type: ExchangeType):
        """
        Initialize rate limiter for specific exchange.

        Args:
            exchange_type: Type of exchange
        """
        self.exchange_type = exchange_type
        self.config = get_exchange_config(exchange_type)

        # Create token buckets for each limit type
        self._request_bucket = RequestBucket(
            capacity=self.config.rate_limits.requests_per_minute,
            refill_rate=self.config.rate_limits.requests_per_minute / 60.0
        )

        self._weight_bucket = RequestBucket(
            capacity=self.config.rate_limits.weight_per_minute,
            refill_rate=self.config.rate_limits.weight_per_minute / 60.0
        )

        self._order_bucket = RequestBucket(
            capacity=self.config.rate_limits.order_rate_per_second * 10,  # 10-second window
            refill_rate=self.config.rate_limits.order_rate_per_second
        )

        # Statistics
        self._request_count = 0
        self._weight_used = 0
        self._order_count = 0
        self._rate_limit_hits = 0
        self._start_time = time.time()

        logger.info(
            "Rate limiter initialized",
            exchange=self.exchange_type.value,
            requests_per_min=self.config.rate_limits.requests_per_minute,
            weight_per_min=self.config.rate_limits.weight_per_minute,
            orders_per_sec=self.config.rate_limits.order_rate_per_second
        )

    async def acquire(self, weight: int = 1, is_order: bool = False) -> None:
        """
        Acquire permission to make an API request.

        This will block until rate limits allow the request.

        Args:
            weight: API weight of the request (default 1)
            is_order: Whether this is an order placement request
        """
        max_wait = 30.0  # Maximum wait time in seconds

        while True:
            # Check all applicable rate limits
            wait_times = []

            # 1. Request count limit
            if not self._request_bucket.consume(1):
                wait_times.append(self._request_bucket.wait_time(1))

            # 2. Weight limit
            if not self._weight_bucket.consume(weight):
                wait_times.append(self._weight_bucket.wait_time(weight))

            # 3. Order rate limit (if applicable)
            if is_order and not self._order_bucket.consume(1):
                wait_times.append(self._order_bucket.wait_time(1))

            # If all limits passed, allow request
            if not wait_times:
                self._request_count += 1
                self._weight_used += weight
                if is_order:
                    self._order_count += 1

                logger.debug(
                    "Rate limit passed",
                    weight=weight,
                    is_order=is_order,
                    request_tokens=self._request_bucket.tokens,
                    weight_tokens=self._weight_bucket.tokens
                )

                return

            # Calculate wait time
            wait_time = min(max(wait_times), max_wait)

            self._rate_limit_hits += 1

            logger.warning(
                "Rate limit hit, waiting",
                wait_time=wait_time,
                weight=weight,
                is_order=is_order,
                request_tokens=self._request_bucket.tokens,
                weight_tokens=self._weight_bucket.tokens
            )

            await asyncio.sleep(wait_time)

    def reset(self) -> None:
        """Reset all rate limit buckets and statistics."""
        self._request_bucket.tokens = float(self._request_bucket.capacity)
        self._weight_bucket.tokens = float(self._weight_bucket.capacity)
        self._order_bucket.tokens = float(self._order_bucket.capacity)

        self._request_count = 0
        self._weight_used = 0
        self._order_count = 0
        self._rate_limit_hits = 0
        self._start_time = time.time()

        logger.info("Rate limiter reset")

    def get_stats(self) -> Dict:
        """
        Get rate limiter statistics.

        Returns:
            Dict with statistics
        """
        elapsed = time.time() - self._start_time

        return {
            'exchange': self.exchange_type.value,
            'elapsed_seconds': elapsed,
            'total_requests': self._request_count,
            'total_weight': self._weight_used,
            'total_orders': self._order_count,
            'rate_limit_hits': self._rate_limit_hits,
            'requests_per_minute': (self._request_count / elapsed * 60) if elapsed > 0 else 0,
            'weight_per_minute': (self._weight_used / elapsed * 60) if elapsed > 0 else 0,
            'current_request_tokens': self._request_bucket.tokens,
            'current_weight_tokens': self._weight_bucket.tokens,
            'current_order_tokens': self._order_bucket.tokens
        }

    @property
    def request_utilization(self) -> float:
        """Get current request bucket utilization (0.0-1.0)."""
        return 1.0 - (self._request_bucket.tokens / self._request_bucket.capacity)

    @property
    def weight_utilization(self) -> float:
        """Get current weight bucket utilization (0.0-1.0)."""
        return 1.0 - (self._weight_bucket.tokens / self._weight_bucket.capacity)

    @property
    def order_utilization(self) -> float:
        """Get current order bucket utilization (0.0-1.0)."""
        return 1.0 - (self._order_bucket.tokens / self._order_bucket.capacity)


class GlobalRateLimiter:
    """
    Global rate limiter manager for multiple exchanges.

    This singleton manages separate rate limiters for each exchange type.
    """

    _instance: Optional['GlobalRateLimiter'] = None
    _limiters: Dict[ExchangeType, RateLimiter] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_limiter(cls, exchange_type: ExchangeType) -> RateLimiter:
        """
        Get rate limiter for specific exchange.

        Args:
            exchange_type: Exchange type

        Returns:
            RateLimiter instance
        """
        if exchange_type not in cls._limiters:
            cls._limiters[exchange_type] = RateLimiter(exchange_type)

        return cls._limiters[exchange_type]

    @classmethod
    def reset_all(cls) -> None:
        """Reset all rate limiters."""
        for limiter in cls._limiters.values():
            limiter.reset()

        logger.info("All rate limiters reset")

    @classmethod
    def get_all_stats(cls) -> Dict[str, Dict]:
        """
        Get statistics from all rate limiters.

        Returns:
            Dict mapping exchange type to stats
        """
        return {
            exchange_type.value: limiter.get_stats()
            for exchange_type, limiter in cls._limiters.items()
        }
