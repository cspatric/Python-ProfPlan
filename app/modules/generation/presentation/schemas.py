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
    #: The day the item lands on, ISO. Replaces the old free-text `when`,
    #: which held things like "semana 2" and could not be put on a calendar.
    date: str | None
    generation_status: GenerationItemStatus | None
    content: dict[str, Any] | None
    error: str | None


class GenerationUsageResponse(BaseModel):
    """What this run spent on the AI.

    Exposed rather than left in the database: "what did this plan cost" is a
    question about one run, and answering it should not require SQL access.
    The teacher does not have to be shown it; whoever pays for it does.
    """

    calls: int
    input_tokens: int
    output_tokens: int
    #: List price in USD. Six decimals, because a cheap call rounds to zero at
    #: four and a report of zeroes teaches nothing.
    cost_usd: float


class GenerationResponse(BaseModel):
    """A generation run with its items (used for polling)."""

    uuid: UUID
    plan_id: UUID
    status: GenerationRunStatus
    summary: str | None
    item_count: int
    items: list[GeneratedItemResponse]
    usage: GenerationUsageResponse


def _item_response(item: AcademicItem) -> GeneratedItemResponse:
    meta = item.item_metadata or {}
    return GeneratedItemResponse(
        uuid=item.uuid,
        module_id=item.module_id,
        title=item.title,
        kind=meta.get("kind"),
        date=meta.get("starts_at"),
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
        usage=GenerationUsageResponse(
            calls=run.llm_calls,
            input_tokens=run.llm_input_tokens,
            output_tokens=run.llm_output_tokens,
            cost_usd=float(run.llm_cost_usd),
        ),
    )
