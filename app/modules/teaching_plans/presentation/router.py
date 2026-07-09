"""Teaching plan HTTP endpoints."""

import logging
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response, status

from app.api.rate_limit import expensive_limit
from app.core.config import get_settings
from app.modules.auth.presentation.dependencies import CurrentUser
from app.modules.generation.presentation.dependencies import GenerationServiceDep
from app.modules.generation.presentation.schemas import build_generation_response
from app.modules.teaching_plans.presentation.dependencies import PlanServiceDep
from app.modules.teaching_plans.presentation.schemas import (
    PlanCreate,
    PlanCreatedResponse,
    PlanResponse,
    PlanUpdate,
)

logger = logging.getLogger("app.plans")

router = APIRouter(prefix="/plans", tags=["plans"])


@router.post(
    "", response_model=PlanCreatedResponse, status_code=status.HTTP_201_CREATED
)
@expensive_limit
async def create_plan(
    request: Request,
    response: Response,
    payload: PlanCreate,
    user: CurrentUser,
    service: PlanServiceDep,
    generation_service: GenerationServiceDep,
) -> PlanCreatedResponse:
    """Create a plan and automatically generate it with AI.

    The planner runs synchronously BEFORE anything is persisted — if the AI
    cannot produce a roadmap the request fails (502/503) and no plan is
    created. On success the roadmap comes back embedded in ``generation`` and
    the per-item generation is queued to workers — poll GET /generations/{id}
    to watch the items fill in.
    """
    # Imported lazily: pulling the Celery task graph at module load time
    # creates an import cycle that breaks the API router.
    from app.infrastructure.celery.tasks.generate import run_item

    # 1) AI first (no side effects) — failures surface as real errors.
    #    Validate the selected documents and scope RAG to them.
    content_ids = (
        await generation_service.resolve_documents(
            user_id=user.uuid, document_ids=payload.document_ids
        )
        or None
    )

    # When generation is disabled (CI / no LLM configured), create a plain plan:
    # no AI call, no fan-out, generation is null in the response.
    if not get_settings().plan_generation_enabled:
        plan = await service.create(
            user_id=user.uuid,
            data=payload.model_dump(exclude={"input", "document_ids"}),
        )
        await generation_service.link_documents_and_commit(
            plan.uuid, payload.document_ids
        )
        return PlanCreatedResponse.model_validate(plan)

    plan_info = (
        f"Period: {payload.starts_at} to {payload.ends_at}. "
        f"{payload.class_per_week} classes/week, {payload.class_duration} min each."
    )
    teacher_input = payload.input or generation_service.default_input()
    roadmap = await generation_service.plan_roadmap(
        user_id=user.uuid,
        subject_id=payload.subject_id,
        plan_info=plan_info,
        teacher_input=teacher_input,
        content_ids=content_ids,
    )

    # 2) Persist plan + document links + roadmap, then fan out to workers.
    plan = await service.create(
        user_id=user.uuid, data=payload.model_dump(exclude={"input", "document_ids"})
    )
    generation_service.link_documents(plan.uuid, payload.document_ids)
    run, items = await generation_service.materialize(
        user_id=user.uuid, plan=plan, roadmap=roadmap, teacher_input=teacher_input
    )
    for item in items:
        run_item.delay(str(item.uuid))

    response = PlanCreatedResponse.model_validate(plan)
    response.generation = build_generation_response(run, items)
    return response


@router.get("", response_model=list[PlanResponse])
async def list_plans(
    user: CurrentUser,
    service: PlanServiceDep,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[PlanResponse]:
    """List the authenticated user's plans."""
    plans = await service.list(user_id=user.uuid, limit=limit, offset=offset)
    return [PlanResponse.model_validate(p) for p in plans]


@router.get("/{plan_id}", response_model=PlanResponse)
async def get_plan(
    plan_id: UUID, user: CurrentUser, service: PlanServiceDep
) -> PlanResponse:
    """Return a single plan."""
    plan = await service.get(user_id=user.uuid, plan_id=plan_id)
    return PlanResponse.model_validate(plan)


@router.patch("/{plan_id}", response_model=PlanResponse)
async def update_plan(
    plan_id: UUID,
    payload: PlanUpdate,
    user: CurrentUser,
    service: PlanServiceDep,
) -> PlanResponse:
    """Update a plan."""
    plan = await service.update(
        user_id=user.uuid,
        plan_id=plan_id,
        data=payload.model_dump(exclude_unset=True),
    )
    return PlanResponse.model_validate(plan)


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan(
    plan_id: UUID, user: CurrentUser, service: PlanServiceDep
) -> None:
    """Delete a plan."""
    await service.delete(user_id=user.uuid, plan_id=plan_id)
