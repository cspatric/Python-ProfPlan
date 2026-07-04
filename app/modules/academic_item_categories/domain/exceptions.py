"""Academic item category domain exceptions."""

from app.shared.exceptions.base import NotFoundError, UnprocessableError


class CategoryNotFoundError(NotFoundError):
    """Raised when a category does not exist."""

    detail = "Category not found"


class CategoryTypeNotFoundError(NotFoundError):
    """Raised when a category type does not exist."""

    detail = "Category type not found"


class InvalidCategoryError(UnprocessableError):
    """Raised when the referenced parent category does not exist."""

    detail = "Parent category not found"
