"""Request/response schemas for the AI module."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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


class ProviderStatusResponse(BaseModel):
    """Runtime status of a single LLM provider."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    order: int
    configured: bool
    enabled: bool
    active: bool
    circuit_open: bool


class AiHealthResponse(BaseModel):
    """The fallback chain and each provider's status."""

    providers: list[ProviderStatusResponse]


class ProviderToggleRequest(BaseModel):
    """Turn a provider on or off."""

    enabled: bool
