"""Academic item category domain exceptions."""


class CategoryNotFoundError(Exception):
    """Raised when a category does not exist."""


class CategoryTypeNotFoundError(Exception):
    """Raised when a category type does not exist."""


class InvalidCategoryError(Exception):
    """Raised when the referenced parent category does not exist."""
