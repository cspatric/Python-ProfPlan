"""Authentication domain exceptions."""


class AuthError(Exception):
    """Base class for authentication errors."""


class InvalidCredentialsError(AuthError):
    """Raised when the email/password pair is invalid."""


class RateLimitedError(AuthError):
    """Raised when too many login attempts were made."""


class InvalidTokenError(AuthError):
    """Raised when a refresh token is missing, invalid or expired."""


class TokenReuseError(AuthError):
    """Raised when a revoked refresh token is presented again."""
