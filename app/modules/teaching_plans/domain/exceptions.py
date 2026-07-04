"""Teaching plan domain exceptions."""

from app.shared.exceptions.base import NotFoundError, UnprocessableError


class PlanNotFoundError(NotFoundError):
    """Raised when a plan does not exist or is not owned by the user."""

    detail = "Plan not found"


class InvalidSubjectError(UnprocessableError):
    """Raised when the referenced subject does not belong to the user."""

    detail = "Subject not found or not owned by the user"
