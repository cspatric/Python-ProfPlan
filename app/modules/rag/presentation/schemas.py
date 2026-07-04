"""Request/response schemas for RAG retrieval."""

from uuid import UUID

from pydantic import BaseModel, Field


class RagQueryRequest(BaseModel):
    """A retrieval query over the user's indexed documents."""

    query: str = Field(min_length=1)
    subject_id: UUID | None = None
    limit: int = Field(default=5, ge=1, le=20)


class RagChunkResult(BaseModel):
    """A retrieved chunk with its similarity to the query."""

    chunk_id: UUID
    document_content_id: UUID
    content: str
    distance: float
    score: float


class RagQueryResponse(BaseModel):
    """The result set of a RAG query."""

    query: str
    results: list[RagChunkResult]
