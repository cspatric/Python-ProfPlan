"""Authentication domain exceptions."""

from app.shared.exceptions.base import (
    ConflictError,
    ForbiddenError,
    RateLimitError,
    UnauthorizedError,
)


class InvalidCredentialsError(UnauthorizedError):
    """Raised when the email/password pair is invalid."""

    detail = "Invalid email or password"


class EmailAlreadyRegisteredError(ConflictError):
    """Raised when registering with an email that already exists."""

    detail = "Email already registered"


class RateLimitedError(RateLimitError):
    """Raised when too many login attempts were made."""

    detail = "Too many login attempts. Try again later."


class InvalidTokenError(UnauthorizedError):
    """Raised when a refresh token is missing, invalid or expired."""

    detail = "Invalid or expired refresh token"


class TokenReuseError(UnauthorizedError):
    """Raised when a revoked refresh token is presented again."""

    detail = "Refresh token reuse detected. All sessions revoked."


class InvalidVerificationTokenError(UnauthorizedError):
    """Raised for a reset or verification token that is unknown, spent or expired.

    One error for all three cases on purpose: telling the difference would
    confirm that a token existed, which is information an attacker holding a
    guess does not get to have.
    """

    detail = "Invalid or expired token"


class EmailNotVerifiedError(ForbiddenError):
    """Raised on login when the account has not confirmed its address."""

    detail = "Confirm your email address before signing in"
