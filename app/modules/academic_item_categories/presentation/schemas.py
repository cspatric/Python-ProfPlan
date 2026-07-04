"""Request/response schemas for academic item categories."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CategoryCreate(BaseModel):
    """Payload to create a category."""

    name: str = Field(min_length=1, max_length=255)
    icon_id: UUID | None = None


class CategoryUpdate(BaseModel):
    """Payload to update a category (all fields optional)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    icon_id: UUID | None = None


class CategoryResponse(BaseModel):
    """Public representation of a category."""

    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    name: str
    icon_id: UUID | None


class CategoryTypeCreate(BaseModel):
    """Payload to create a category type."""

    academic_item_category_id: UUID
    name: str = Field(min_length=1, max_length=255)
    icon_id: UUID | None = None


class CategoryTypeUpdate(BaseModel):
    """Payload to update a category type (all fields optional)."""

    academic_item_category_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    icon_id: UUID | None = None


class CategoryTypeResponse(BaseModel):
    """Public representation of a category type."""

    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    academic_item_category_id: UUID
    name: str
    icon_id: UUID | None
