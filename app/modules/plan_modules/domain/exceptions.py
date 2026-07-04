"""Plan-module domain exceptions."""

from app.shared.exceptions.base import NotFoundError, UnprocessableError


class ModuleNotFoundError(NotFoundError):
    """Raised when a module does not exist or is not owned by the user."""

    detail = "Module not found"


class InvalidPlanError(UnprocessableError):
    """Raised when the referenced plan does not belong to the user."""

    detail = "Plan not found or not owned by the user"
