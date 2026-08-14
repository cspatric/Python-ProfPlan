"""RAG domain exceptions."""

from app.shared.exceptions.base import UnprocessableError


class InvalidContentError(UnprocessableError):
    """Raised when indexing references a document content that does not exist."""

    detail = "Document content not found"


class EmptyDocumentError(UnprocessableError):
    """Raised when a parsed document yields no text to index.

    Not a technical failure: the pipeline ran and the file simply had nothing
    in it to search. It is reported as one anyway, because the alternative is a
    document that says "Indexed" and feeds the AI nothing.
    """

    detail = (
        "No readable text could be extracted from this file. A scanned PDF has "
        "no text layer, so it has to be run through OCR before it can be used."
    )
