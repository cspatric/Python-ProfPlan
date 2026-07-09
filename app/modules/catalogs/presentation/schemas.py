"""Request/response schemas for the icon and color catalogs."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class IconCreate(BaseModel):
    """Payload to create an icon."""

    name: str = Field(min_length=1, max_length=100)
    file_path: str = Field(min_length=1, max_length=255)


class IconUpdate(BaseModel):
    """Payload to update an icon (all fields optional)."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    file_path: str | None = Field(default=None, min_length=1, max_length=255)


class IconResponse(BaseModel):
    """Public representation of an icon."""

    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    name: str
    file_path: str


class ColorCreate(BaseModel):
    """Payload to create a color."""

    name: str = Field(min_length=1, max_length=100)
    hex_code: str = Field(min_length=4, max_length=7)


class ColorUpdate(BaseModel):
    """Payload to update a color (all fields optional)."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    hex_code: str | None = Field(default=None, min_length=4, max_length=7)


class ColorResponse(BaseModel):
    """Public representation of a color."""

    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    name: str
    hex_code: str
