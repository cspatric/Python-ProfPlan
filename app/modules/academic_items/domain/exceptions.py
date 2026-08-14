"""Academic item domain exceptions."""

from app.shared.exceptions.base import NotFoundError, UnprocessableError


class AcademicItemNotFoundError(NotFoundError):
    """Raised when an item does not exist or is not owned by the user."""

    detail = "Academic item not found"


class HandoutNotReadyError(UnprocessableError):
    """Raised when a handout is asked for before the AI wrote the material.

    A PDF of an empty activity would be a cover page and nothing else, which
    reads as a broken export rather than as "come back in a minute".
    """

    detail = "This activity has no material yet, so there is nothing to export"


class InvalidModuleError(UnprocessableError):
    """Raised when the referenced module does not belong to the user."""

    detail = "Module not found or not owned by the user"
