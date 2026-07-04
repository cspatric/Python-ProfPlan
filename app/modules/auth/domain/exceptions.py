"""Authentication domain exceptions."""

from app.shared.exceptions.base import RateLimitError, UnauthorizedError


class InvalidCredentialsError(UnauthorizedError):
    """Raised when the email/password pair is invalid."""

    detail = "Invalid email or password"


class RateLimitedError(RateLimitError):
    """Raised when too many login attempts were made."""

    detail = "Too many login attempts. Try again later."


class InvalidTokenError(UnauthorizedError):
    """Raised when a refresh token is missing, invalid or expired."""

    detail = "Invalid or expired refresh token"


class TokenReuseError(UnauthorizedError):
    """Raised when a revoked refresh token is presented again."""

    detail = "Refresh token reuse detected. All sessions revoked."
