"""Teaching plan HTTP endpoints."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.modules.auth.presentation.dependencies import CurrentUser
from app.modules.teaching_plans.domain.exceptions import (
    InvalidSubjectError,
    PlanNotFoundError,
)
from app.modules.teaching_plans.presentation.dependencies import PlanServiceDep
from app.modules.teaching_plans.presentation.schemas import (
    PlanCreate,
    PlanResponse,
    PlanUpdate,
)

router = APIRouter(prefix="/plans", tags=["plans"])

_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found"
)
_INVALID_SUBJECT = HTTPException(
    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    detail="Subject not found or not owned by the user",
)


@router.post("", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
async def create_plan(
    payload: PlanCreate, user: CurrentUser, service: PlanServiceDep
) -> PlanResponse:
    """Create a plan owned by the authenticated user."""
    try:
        plan = await service.create(user_id=user.uuid, data=payload.model_dump())
    except InvalidSubjectError as exc:
        raise _INVALID_SUBJECT from exc
    return PlanResponse.model_validate(plan)


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
    try:
        plan = await service.get(user_id=user.uuid, plan_id=plan_id)
    except PlanNotFoundError as exc:
        raise _NOT_FOUND from exc
    return PlanResponse.model_validate(plan)


@router.patch("/{plan_id}", response_model=PlanResponse)
async def update_plan(
    plan_id: UUID,
    payload: PlanUpdate,
    user: CurrentUser,
    service: PlanServiceDep,
) -> PlanResponse:
    """Update a plan."""
    try:
        plan = await service.update(
            user_id=user.uuid,
            plan_id=plan_id,
            data=payload.model_dump(exclude_unset=True),
        )
    except PlanNotFoundError as exc:
        raise _NOT_FOUND from exc
    except InvalidSubjectError as exc:
        raise _INVALID_SUBJECT from exc
    return PlanResponse.model_validate(plan)


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan(
    plan_id: UUID, user: CurrentUser, service: PlanServiceDep
) -> None:
    """Delete a plan."""
    try:
        await service.delete(user_id=user.uuid, plan_id=plan_id)
    except PlanNotFoundError as exc:
        raise _NOT_FOUND from exc
