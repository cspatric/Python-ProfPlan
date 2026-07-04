"""Academic item domain exceptions."""

from app.shared.exceptions.base import NotFoundError, UnprocessableError


class AcademicItemNotFoundError(NotFoundError):
    """Raised when an item does not exist or is not owned by the user."""

    detail = "Academic item not found"


class InvalidModuleError(UnprocessableError):
    """Raised when the referenced module does not belong to the user."""

    detail = "Module not found or not owned by the user"
