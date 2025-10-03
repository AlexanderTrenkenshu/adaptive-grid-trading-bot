"""
Retry decorators and utilities for handling transient errors.
"""

import asyncio
import functools
from typing import Callable, Type, Tuple
from ..exchange.exceptions import TransientError
from .logger import get_logger

logger = get_logger(__name__)


def retry_on_transient_error(
    max_attempts: int = 3,
    backoff_base: int = 2,
    exceptions: Tuple[Type[Exception], ...] = (TransientError,)
):
    """
    Decorator to retry async functions on transient errors.

    Uses exponential backoff: delay = backoff_base ** attempt_number

    Args:
        max_attempts: Maximum number of retry attempts (default: 3)
        backoff_base: Base for exponential backoff calculation (default: 2)
        exceptions: Tuple of exception types to retry on

    Example:
        @retry_on_transient_error(max_attempts=3)
        async def api_call():
            # Your API call here
            pass
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_attempts - 1:
                        # Last attempt failed, raise the exception
                        logger.error(
                            "max_retries_exceeded",
                            function=func.__name__,
                            attempts=max_attempts,
                            error=str(e)
                        )
                        raise

                    # Calculate delay and retry
                    delay = backoff_base ** attempt
                    logger.warning(
                        "retrying_after_error",
                        function=func.__name__,
                        attempt=attempt + 1,
                        max_attempts=max_attempts,
                        delay_seconds=delay,
                        error=str(e)
                    )
                    await asyncio.sleep(delay)

            # Should never reach here, but just in case
            if last_exception:
                raise last_exception

        return wrapper
    return decorator


def retry_with_timeout(
    max_attempts: int = 3,
    timeout_seconds: float = 30.0,
    backoff_base: int = 2
):
    """
    Decorator to retry async functions with a timeout.

    Combines retry logic with timeout enforcement.

    Args:
        max_attempts: Maximum retry attempts
        timeout_seconds: Timeout for each attempt in seconds
        backoff_base: Base for exponential backoff

    Example:
        @retry_with_timeout(max_attempts=3, timeout_seconds=30)
        async def slow_operation():
            # Your operation here
            pass
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    # Apply timeout to the function call
                    return await asyncio.wait_for(
                        func(*args, **kwargs),
                        timeout=timeout_seconds
                    )
                except asyncio.TimeoutError as e:
                    if attempt == max_attempts - 1:
                        logger.error(
                            "timeout_max_retries_exceeded",
                            function=func.__name__,
                            attempts=max_attempts,
                            timeout_seconds=timeout_seconds
                        )
                        raise

                    delay = backoff_base ** attempt
                    logger.warning(
                        "retrying_after_timeout",
                        function=func.__name__,
                        attempt=attempt + 1,
                        max_attempts=max_attempts,
                        delay_seconds=delay,
                        timeout_seconds=timeout_seconds
                    )
                    await asyncio.sleep(delay)
                except Exception as e:
                    # Re-raise non-timeout exceptions immediately
                    logger.error(
                        "unexpected_error_in_retry",
                        function=func.__name__,
                        error=str(e),
                        error_type=type(e).__name__
                    )
                    raise

        return wrapper
    return decorator
