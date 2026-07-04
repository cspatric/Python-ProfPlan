"""RAG domain exceptions."""

from app.shared.exceptions.base import UnprocessableError


class InvalidContentError(UnprocessableError):
    """Raised when indexing references a document content that does not exist."""

    detail = "Document content not found"
