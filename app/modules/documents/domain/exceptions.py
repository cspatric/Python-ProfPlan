"""Document domain exceptions."""

from app.shared.exceptions.base import NotFoundError, UnprocessableError


class DocumentNotFoundError(NotFoundError):
    """Raised when a document does not exist or is not owned by the user."""

    detail = "Document not found"


class DocumentContentNotFoundError(NotFoundError):
    """Raised when a document content does not exist."""

    detail = "Document content not found"


class InvalidSubjectError(UnprocessableError):
    """Raised when the referenced subject does not belong to the user."""

    detail = "Subject not found or not owned by the user"
