"""Request/response schemas for teaching plans."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PlanCreate(BaseModel):
    """Payload to create a plan."""

    subject_id: UUID
    starts_at: date
    ends_at: date
    class_duration: int = Field(gt=0, description="Class length in minutes")
    class_per_week: int = Field(gt=0)
    total_weight: float | None = Field(default=None, ge=0)
    academic_items_id: UUID | None = None

    @model_validator(mode="after")
    def _check_dates(self) -> "PlanCreate":
        if self.ends_at < self.starts_at:
            raise ValueError("ends_at must not be before starts_at")
        return self


class PlanUpdate(BaseModel):
    """Payload to update a plan (all fields optional)."""

    subject_id: UUID | None = None
    starts_at: date | None = None
    ends_at: date | None = None
    class_duration: int | None = Field(default=None, gt=0)
    class_per_week: int | None = Field(default=None, gt=0)
    total_weight: float | None = Field(default=None, ge=0)
    academic_items_id: UUID | None = None


class PlanResponse(BaseModel):
    """Public representation of a plan."""

    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    user_id: UUID
    subject_id: UUID
    starts_at: date
    ends_at: date
    class_duration: int
    class_per_week: int
    total_weight: float | None
    academic_items_id: UUID | None
    created_at: datetime
    updated_at: datetime
