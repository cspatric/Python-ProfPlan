"""Request/response schemas for academic items."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.academic_items.infrastructure.models import AcademicItemFigure
from app.modules.generation.domain.entities import GenerationItemStatus


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


class AcademicItemSourceResponse(BaseModel):
    """One passage the AI was given before it wrote this item."""

    rank: int
    document_id: UUID | None
    #: None when the document has since been deleted. The passage is still
    #: shown: what was cited does not stop having been cited.
    document_title: str | None
    section: str | None
    excerpt: str
    #: Cosine similarity to the request, 1.0 being identical. Shown because a
    #: passage at 0.45 supports a claim far more weakly than one at 0.85, and a
    #: citation that hides that is a citation that flatters itself.
    similarity: float | None


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
    # Null on hand-made items; on generated ones it says whether the worker
    # has written the body yet. Without it the frontend cannot tell an item
    # still in the queue from one whose generation failed, and shows a
    # spinner that never stops for the second case.
    generation_status: GenerationItemStatus | None = None
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime


class AcademicItemFigureResponse(BaseModel):
    """One illustration of an item, and the credit that must be shown with it.

    ``path`` is the value that appears inside the item's Markdown, so a renderer
    matches an ``![](...)`` to this row by it. ``url`` is where to GET the bytes.

    The bytes are streamed by this API rather than handed out as a storage link,
    and that is not laziness: MinIO lives on the internal Docker network with no
    published port, and Traefik is on the edge network and cannot route to it. A
    presigned URL would be a URL the browser cannot open. The network decision
    from the architecture is what shapes this endpoint.
    """

    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    position: int
    path: str
    url: str
    alt_text: str
    #: What to print under the image. Already carries the credit line.
    caption: str | None
    source: str
    #: The page where the credit can be verified.
    source_url: str | None
    licence: str
    licence_url: str | None
    attribution: str | None
    width: int | None
    height: int | None
    mime_type: str

    @classmethod
    def of(
        cls, figure: AcademicItemFigure, *, url: str
    ) -> "AcademicItemFigureResponse":
        """Build from a row, adding the two fields a renderer needs."""
        return cls(
            uuid=figure.uuid,
            position=figure.position,
            path=figure.figure_path,
            url=url,
            alt_text=figure.alt_text,
            caption=figure.caption,
            source=figure.source.value,
            source_url=figure.source_url,
            licence=figure.licence,
            licence_url=figure.licence_url,
            attribution=figure.attribution,
            width=figure.width,
            height=figure.height,
            mime_type=figure.mime_type,
        )
