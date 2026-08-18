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

#: Fields of PlanCreate that steer the generation and are not columns of the
#: plan. Dumping them into the model would try to set attributes that do not
#: exist on the table.
_GENERATION_ONLY_FIELDS = {
    "input",
    "language",
    "document_ids",
    "activity_count",
    "exam_count",
    "assignment_count",
    "item_kinds",
}


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
    """Create a plan; the AI drafts it in the background.

    The planner call costs up to a minute. It used to run inside this request,
    which meant a browser that lost the connection meanwhile left the teacher
    with nothing on screen and a plan in the database. The plan is created
    here, a generation run is opened as PLANNING, and the drafting is queued:
    the response comes back at once with the run to poll.

    The trade is deliberate. A plan can now exist before its roadmap does, and
    a planner failure lands on the run (FAILED, with the reason) instead of
    failing the request. That state is visible; a request nobody is waiting on
    is not.
    """
    # Imported lazily: pulling the Celery task graph at module load time
    # creates an import cycle that breaks the API router.
    from app.infrastructure.celery.tasks.generate import generate_plan

    # Money before work: an account that has spent its month is told so here,
    # before a plan row exists and before a task is queued. Checking later
    # would mean refusing a plan the teacher can already see.
    await generation_service.ensure_budget(user.uuid)

    # Validate the selected documents before anything is written: a 404 for an
    # unknown document belongs in the response, not in a worker log.
    await generation_service.resolve_documents(
        user_id=user.uuid, document_ids=payload.document_ids
    )

    plan = await service.create(
        user_id=user.uuid, data=payload.model_dump(exclude=_GENERATION_ONLY_FIELDS)
    )
    await generation_service.link_documents_and_commit(plan.uuid, payload.document_ids)

    # When generation is disabled (CI / no LLM configured), the plan is all
    # there is: no run, no queue, generation is null in the response.
    if not get_settings().plan_generation_enabled:
        return PlanCreatedResponse.model_validate(plan)

    teacher_input = payload.input or generation_service.default_input()
    run = await generation_service.begin(
        user_id=user.uuid,
        plan_id=plan.uuid,
        teacher_input=teacher_input,
        item_counts=payload.requested_counts(),
        item_kinds=payload.item_kinds,
        language=payload.language,
    )
    generate_plan.delay(str(plan.uuid), str(user.uuid), str(run.uuid), teacher_input)

    response = PlanCreatedResponse.model_validate(plan)
    # No items yet: the roadmap that decides them has not been drafted. The
    # run is what the client watches until they appear.
    response.generation = build_generation_response(run, [])
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
