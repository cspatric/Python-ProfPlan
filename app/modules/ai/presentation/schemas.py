"""Request/response schemas for the AI module."""

from uuid import UUID

from pydantic import BaseModel, Field


class AiAskRequest(BaseModel):
    """A question to answer using the user's documents as context."""

    query: str = Field(min_length=1)
    subject_id: UUID | None = None
    limit: int = Field(default=5, ge=1, le=20)


class AiAnswerResponse(BaseModel):
    """The generated answer, the provider used and the source chunk ids."""

    answer: str
    provider: str
    sources: list[UUID]
