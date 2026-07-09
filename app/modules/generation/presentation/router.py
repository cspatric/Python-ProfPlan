"""Plan-generation HTTP endpoints (planner sync + fan-out + polling)."""

from uuid import UUID

from fastapi import APIRouter, status

from app.modules.auth.presentation.dependencies import CurrentUser
from app.modules.generation.presentation.dependencies import GenerationServiceDep
from app.modules.generation.presentation.schemas import (
    GenerateRequest,
    GenerationResponse,
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

    run, items = await service.start(
        user_id=user.uuid, plan_id=plan_id, teacher_input=payload.input
    )
    for item in items:
        run_item.delay(str(item.uuid))
    return build_generation_response(run, items)


@router.get("/generations/{generation_id}", response_model=GenerationResponse)
async def get_generation(
    generation_id: UUID,
    user: CurrentUser,
    service: GenerationServiceDep,
) -> GenerationResponse:
    """Return a generation run and its items (poll until status is terminal)."""
    run, items = await service.get(user_id=user.uuid, generation_id=generation_id)
    return build_generation_response(run, items)
