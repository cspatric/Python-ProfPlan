"""Document domain types."""

from enum import Enum


class IngestionStatus(str, Enum):
    """Lifecycle of a document's RAG ingestion.

    PENDING    -> uploaded, queued for processing
    PROCESSING -> the worker is parsing/embedding it
    INDEXED    -> chunks (with embeddings) are persisted in pgvector
    FAILED     -> ingestion errored after exhausting retries (see ingestion_error)
    """

    PENDING = "pending"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"
