"""Base application exceptions mapped to HTTP responses.

Domain modules raise subclasses of these; the centralized exception handlers
(see app/api/exceptions.py) turn them into consistent JSON error responses, so
routers never map errors by hand.
"""

from fastapi import status


class AppError(Exception):
    """Base class for expected application errors."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    detail: str = "Internal server error"

    def __init__(self, detail: str | None = None) -> None:
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)


class NotFoundError(AppError):
    """The requested resource does not exist (or is not visible to the user)."""

    status_code = status.HTTP_404_NOT_FOUND
    detail = "Resource not found"


class UnprocessableError(AppError):
    """The request is well-formed but references invalid data."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    detail = "Unprocessable request"


class ConflictError(AppError):
    """The request conflicts with the current state."""

    status_code = status.HTTP_409_CONFLICT
    detail = "Conflict"


class UnauthorizedError(AppError):
    """Authentication is required or has failed."""

    status_code = status.HTTP_401_UNAUTHORIZED
    detail = "Not authenticated"


class RateLimitError(AppError):
    """Too many requests in the given window."""

    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    detail = "Too many requests"
