"""Academic item domain exceptions."""


class AcademicItemNotFoundError(Exception):
    """Raised when an item does not exist or is not owned by the user."""


class InvalidModuleError(Exception):
    """Raised when the referenced module does not belong to the user."""
