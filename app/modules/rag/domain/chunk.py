"""RAG domain value objects."""

from dataclasses import dataclass


@dataclass(slots=True)
class ChunkInput:
    """A chunk ready to be indexed for a document content."""

    chunk_index: int
    content: str
    token_count: int | None = None
    embedding: list[float] | None = None


@dataclass(slots=True)
class SearchResult:
    """A retrieved chunk with its cosine distance to the query (lower closer)."""

    chunk_id: str
    document_content_id: str
    content: str
    distance: float
