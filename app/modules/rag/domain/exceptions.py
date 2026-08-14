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


class EmbeddingDimensionMismatchError(UnprocessableError):
    """Raised when the model's vectors do not fit the column they go into.

    The vector size is fixed by a migration (``chunks.embedding``), so
    switching EMBEDDING_MODEL to a model of a different size is a schema
    change, not a setting change. Checked on the first batch: without it the
    run pays for every chunk and then fails on the insert with a SQL error
    naming neither the model nor the setting that caused it.
    """

    def __init__(self, *, expected: int, got: int, model: str) -> None:
        self.detail = (
            f"The embedding model '{model}' returns {got}-dimension vectors, but "
            f"the chunks column stores {expected}. Switching models needs a "
            f"migration that resizes the column and a re-index of every "
            f"document; the vectors already stored cannot be compared with new "
            f"ones."
        )
        super().__init__(self.detail)
