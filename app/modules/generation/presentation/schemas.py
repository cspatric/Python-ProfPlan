"""Request/response schemas for the generation API."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.academic_items.infrastructure.models import AcademicItem
from app.modules.generation.domain.entities import (
    GenerationItemStatus,
    GenerationRunStatus,
)
from app.modules.generation.infrastructure.models import PlanGeneration


class GenerateRequest(BaseModel):
    """The teacher's request that drives the plan generation."""

    input: str = Field(
        min_length=1, description="what the teacher wants the plan to be"
    )


class GeneratedItemResponse(BaseModel):
    """One generated academic item (a subtask)."""

    uuid: UUID
    module_id: UUID
    title: str
    kind: str | None
    when: str | None
    generation_status: GenerationItemStatus | None
    content: dict[str, Any] | None
    error: str | None


class GenerationResponse(BaseModel):
    """A generation run with its items (used for polling)."""

    uuid: UUID
    plan_id: UUID
    status: GenerationRunStatus
    summary: str | None
    item_count: int
    items: list[GeneratedItemResponse]


def _item_response(item: AcademicItem) -> GeneratedItemResponse:
    meta = item.item_metadata or {}
    return GeneratedItemResponse(
        uuid=item.uuid,
        module_id=item.module_id,
        title=item.title,
        kind=meta.get("kind"),
        when=meta.get("when"),
        generation_status=item.generation_status,
        content=item.content,
        error=item.generation_error,
    )


def build_generation_response(
    run: PlanGeneration, items: list[AcademicItem]
) -> GenerationResponse:
    """Assemble the polling payload from a run and its items."""
    summary = (run.roadmap or {}).get("summary") if run.roadmap else None
    return GenerationResponse(
        uuid=run.uuid,
        plan_id=run.plan_id,
        status=run.status,
        summary=summary,
        item_count=len(items),
        items=[_item_response(i) for i in items],
    )
