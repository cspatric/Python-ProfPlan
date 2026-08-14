"""Request/response schemas for subjects."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.shared.validation import OptionalText, RequiredText


class SubjectCreate(BaseModel):
    """Payload to create a subject."""

    name: RequiredText = Field(min_length=1, max_length=255)
    description: OptionalText = Field(default=None, max_length=2000)
    knowledge_area: OptionalText = Field(default=None, max_length=255)
    icon_id: UUID | None = None
    color_id: UUID | None = None


class SubjectUpdate(BaseModel):
    """Payload to update a subject (all fields optional)."""

    name: OptionalText = Field(default=None, min_length=1, max_length=255)
    description: OptionalText = Field(default=None, max_length=2000)
    knowledge_area: OptionalText = Field(default=None, max_length=255)
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
