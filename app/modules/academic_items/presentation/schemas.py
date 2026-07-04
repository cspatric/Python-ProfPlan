"""Request/response schemas for academic items."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AcademicItemMetadata(BaseModel):
    """Structure of the academic item `metadata` JSON field."""

    uuid: UUID | None = None
    academic_item_id: UUID | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    is_graded: bool = False
    weight: float | None = Field(default=None, ge=0)
    is_individual: bool = False
    estimated_duration: int | None = Field(
        default=None, ge=0, description="Estimated duration in minutes"
    )


class AcademicItemCreate(BaseModel):
    """Payload to create an academic item."""

    module_id: UUID
    item_category_id: UUID | None = None
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    content: dict[str, Any] | None = None
    metadata: AcademicItemMetadata | None = None


class AcademicItemUpdate(BaseModel):
    """Payload to update an academic item (all fields optional)."""

    module_id: UUID | None = None
    item_category_id: UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    content: dict[str, Any] | None = None
    metadata: AcademicItemMetadata | None = None


class AcademicItemResponse(BaseModel):
    """Public representation of an academic item."""

    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    user_id: UUID
    module_id: UUID
    item_category_id: UUID | None
    title: str
    description: str | None
    content: dict[str, Any] | None
    metadata: AcademicItemMetadata | None
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime
