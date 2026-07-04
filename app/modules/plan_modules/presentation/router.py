"""Plan-module HTTP endpoints."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.modules.auth.presentation.dependencies import CurrentUser
from app.modules.plan_modules.domain.exceptions import (
    InvalidPlanError,
    ModuleNotFoundError,
)
from app.modules.plan_modules.presentation.dependencies import ModuleServiceDep
from app.modules.plan_modules.presentation.schemas import (
    ModuleCreate,
    ModuleResponse,
    ModuleUpdate,
)

router = APIRouter(prefix="/modules", tags=["modules"])

_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Module not found"
)
_INVALID_PLAN = HTTPException(
    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    detail="Plan not found or not owned by the user",
)


@router.post("", response_model=ModuleResponse, status_code=status.HTTP_201_CREATED)
async def create_module(
    payload: ModuleCreate, user: CurrentUser, service: ModuleServiceDep
) -> ModuleResponse:
    """Create a module under a plan owned by the authenticated user."""
    try:
        module = await service.create(user_id=user.uuid, data=payload.model_dump())
    except InvalidPlanError as exc:
        raise _INVALID_PLAN from exc
    return ModuleResponse.model_validate(module)


@router.get("", response_model=list[ModuleResponse])
async def list_modules(
    plan_id: UUID,
    user: CurrentUser,
    service: ModuleServiceDep,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[ModuleResponse]:
    """List the modules of a plan owned by the authenticated user."""
    try:
        modules = await service.list(
            user_id=user.uuid, plan_id=plan_id, limit=limit, offset=offset
        )
    except InvalidPlanError as exc:
        raise _INVALID_PLAN from exc
    return [ModuleResponse.model_validate(m) for m in modules]


@router.get("/{module_id}", response_model=ModuleResponse)
async def get_module(
    module_id: UUID, user: CurrentUser, service: ModuleServiceDep
) -> ModuleResponse:
    """Return a single module."""
    try:
        module = await service.get(user_id=user.uuid, module_id=module_id)
    except ModuleNotFoundError as exc:
        raise _NOT_FOUND from exc
    return ModuleResponse.model_validate(module)


@router.patch("/{module_id}", response_model=ModuleResponse)
async def update_module(
    module_id: UUID,
    payload: ModuleUpdate,
    user: CurrentUser,
    service: ModuleServiceDep,
) -> ModuleResponse:
    """Update a module."""
    try:
        module = await service.update(
            user_id=user.uuid,
            module_id=module_id,
            data=payload.model_dump(exclude_unset=True),
        )
    except ModuleNotFoundError as exc:
        raise _NOT_FOUND from exc
    except InvalidPlanError as exc:
        raise _INVALID_PLAN from exc
    return ModuleResponse.model_validate(module)


@router.delete("/{module_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_module(
    module_id: UUID, user: CurrentUser, service: ModuleServiceDep
) -> None:
    """Delete a module."""
    try:
        await service.delete(user_id=user.uuid, module_id=module_id)
    except ModuleNotFoundError as exc:
        raise _NOT_FOUND from exc
