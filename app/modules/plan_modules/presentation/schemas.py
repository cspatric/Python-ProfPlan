"""Request/response schemas for plan modules."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ModuleCreate(BaseModel):
    """Payload to create a module."""

    plan_id: UUID
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    start_at: date
    ends_at: date

    @model_validator(mode="after")
    def _check_dates(self) -> "ModuleCreate":
        if self.ends_at < self.start_at:
            raise ValueError("ends_at must not be before start_at")
        return self


class ModuleUpdate(BaseModel):
    """Payload to update a module (all fields optional)."""

    plan_id: UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    start_at: date | None = None
    ends_at: date | None = None


class ModuleResponse(BaseModel):
    """Public representation of a module."""

    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    plan_id: UUID
    user_id: UUID
    title: str
    description: str | None
    start_at: date
    ends_at: date
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime
