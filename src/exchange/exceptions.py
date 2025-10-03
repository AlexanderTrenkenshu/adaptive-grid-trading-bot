"""
Exchange-related exception classes.
"""


class ExchangeError(Exception):
    """Base exception for all exchange-related errors."""
    pass


class ExchangeAPIError(ExchangeError):
    """Exception raised when API call fails."""

    def __init__(self, message: str, status_code: int = None, error_code: str = None):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(self.message)


class TransientError(ExchangeAPIError):
    """Exception for temporary errors that can be retried (5xx, timeouts)."""
    pass


class PermanentError(ExchangeAPIError):
    """Exception for permanent errors that should not be retried (4xx)."""
    pass


class WebSocketError(ExchangeError):
    """Exception raised for WebSocket-related errors."""
    pass


class RateLimitError(ExchangeAPIError):
    """Exception raised when API rate limit is exceeded."""
    pass


class InvalidOrderError(PermanentError):
    """Exception raised for invalid order parameters."""
    pass


class InsufficientBalanceError(PermanentError):
    """Exception raised when account has insufficient balance."""
    pass


class ConnectionError(ExchangeError):
    """Exception raised when connection to exchange fails."""
    pass


class InvalidTransitionError(ExchangeError):
    """Exception raised for invalid state machine transitions."""
    pass
