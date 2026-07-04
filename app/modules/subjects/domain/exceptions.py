"""Subject domain exceptions."""

from app.shared.exceptions.base import NotFoundError


class SubjectNotFoundError(NotFoundError):
    """Raised when a subject does not exist or is not owned by the user."""

    detail = "Subject not found"
