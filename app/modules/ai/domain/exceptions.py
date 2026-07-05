"""AI domain exceptions."""

from app.shared.exceptions.base import AppError


class ProviderUnavailableError(Exception):
    """Internal: a provider cannot serve the request (skip to the next)."""


class AllProvidersFailedError(AppError):
    """Raised when every provider in the fallback chain failed."""

    status_code = 503
    detail = "All AI providers are currently unavailable"

    def __init__(self, errors: dict[str, str] | None = None) -> None:
        self.errors = errors or {}
        super().__init__(self.detail)
