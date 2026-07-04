"""Request/response schemas for subjects."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SubjectCreate(BaseModel):
    """Payload to create a subject."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    knowledge_area: str | None = Field(default=None, max_length=255)
    icon_id: UUID | None = None
    color_id: UUID | None = None


class SubjectUpdate(BaseModel):
    """Payload to update a subject (all fields optional)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    knowledge_area: str | None = Field(default=None, max_length=255)
    icon_id: UUID | None = None
    color_id: UUID | None = None


class SubjectResponse(BaseModel):
    """Public representation of a subject."""

    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    user_id: UUID
    name: str
    description: str | None
    knowledge_area: str | None
    icon_id: UUID | None
    color_id: UUID | None
    created_at: datetime
    updated_at: datetime
