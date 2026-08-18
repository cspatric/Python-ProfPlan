"""Plan-generation HTTP endpoints (planner sync + fan-out + polling)."""

from uuid import UUID

from fastapi import APIRouter, status

from app.modules.auth.presentation.dependencies import CurrentAdmin, CurrentUser
from app.modules.generation.presentation.dependencies import GenerationServiceDep
from app.modules.generation.presentation.schemas import (
    AccountUsageResponse,
    GenerateRequest,
    GenerationResponse,
    UsageResponse,
    build_generation_response,
)

router = APIRouter(tags=["generation"])


@router.post(
    "/plans/{plan_id}/generate",
    response_model=GenerationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_plan(
    plan_id: UUID,
    payload: GenerateRequest,
    user: CurrentUser,
    service: GenerationServiceDep,
) -> GenerationResponse:
    """Run the planner (sync) and queue one generation task per item.

    Returns immediately with the roadmap and the pending items; the client
    polls GET /generations/{id} while the items fill in.
    """
    # Imported lazily: pulling the Celery task graph at module load time creates
    # an import cycle that truncates the API router.
    from app.infrastructure.celery.tasks.generate import run_item

    # The other door into the AI, and it needs the same lock as plan creation.
    await service.ensure_budget(user.uuid)

    run, items = await service.start(
        user_id=user.uuid,
        plan_id=plan_id,
        teacher_input=payload.input,
        language=payload.language,
    )
    for item in items:
        run_item.delay(str(item.uuid))
    return build_generation_response(run, items)


@router.get("/usage/me", response_model=UsageResponse)
async def my_usage(user: CurrentUser, service: GenerationServiceDep) -> UsageResponse:
    """What this account has spent on the AI this month, and what is left.

    Available to the account itself, not only to an admin: a limit somebody
    cannot see is a limit they can only discover by hitting it.
    """
    spent, limit = await service.budget(user.uuid)
    return UsageResponse(
        spent_usd=float(spent),
        budget_usd=float(limit),
        remaining_usd=float(max(limit - spent, 0)) if limit > 0 else None,
    )


@router.get("/usage", response_model=list[AccountUsageResponse])
async def usage_by_account(
    admin: CurrentAdmin, service: GenerationServiceDep
) -> list[AccountUsageResponse]:
    """What every account has spent this month, dearest first.

    Admin only, and it is the answer to "who is costing us money", which the
    Prometheus metrics deliberately cannot give: a per-user label on a counter
    is an unbounded number of time series, and the first thing it breaks is
    Prometheus itself.
    """
    return [
        AccountUsageResponse(
            user_id=user_id,
            email=email,
            runs=runs,
            tokens=tokens,
            spent_usd=float(spent),
        )
        for user_id, email, runs, tokens, spent in await service.usage_by_account()
    ]


@router.get("/generations/{generation_id}", response_model=GenerationResponse)
async def get_generation(
    generation_id: UUID,
    user: CurrentUser,
    service: GenerationServiceDep,
) -> GenerationResponse:
    """Return a generation run and its items (poll until status is terminal)."""
    run, items = await service.get(user_id=user.uuid, generation_id=generation_id)
    return build_generation_response(run, items)
