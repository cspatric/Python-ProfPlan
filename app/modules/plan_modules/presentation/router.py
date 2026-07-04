"""Plan-module HTTP endpoints."""

from uuid import UUID

from fastapi import APIRouter, Query, status

from app.modules.auth.presentation.dependencies import CurrentUser
from app.modules.plan_modules.presentation.dependencies import ModuleServiceDep
from app.modules.plan_modules.presentation.schemas import (
    ModuleCreate,
    ModuleResponse,
    ModuleUpdate,
)

router = APIRouter(prefix="/modules", tags=["modules"])


@router.post("", response_model=ModuleResponse, status_code=status.HTTP_201_CREATED)
async def create_module(
    payload: ModuleCreate, user: CurrentUser, service: ModuleServiceDep
) -> ModuleResponse:
    """Create a module under a plan owned by the authenticated user."""
    module = await service.create(user_id=user.uuid, data=payload.model_dump())
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
    modules = await service.list(
        user_id=user.uuid, plan_id=plan_id, limit=limit, offset=offset
    )
    return [ModuleResponse.model_validate(m) for m in modules]


@router.get("/{module_id}", response_model=ModuleResponse)
async def get_module(
    module_id: UUID, user: CurrentUser, service: ModuleServiceDep
) -> ModuleResponse:
    """Return a single module."""
    module = await service.get(user_id=user.uuid, module_id=module_id)
    return ModuleResponse.model_validate(module)


@router.patch("/{module_id}", response_model=ModuleResponse)
async def update_module(
    module_id: UUID,
    payload: ModuleUpdate,
    user: CurrentUser,
    service: ModuleServiceDep,
) -> ModuleResponse:
    """Update a module."""
    module = await service.update(
        user_id=user.uuid,
        module_id=module_id,
        data=payload.model_dump(exclude_unset=True),
    )
    return ModuleResponse.model_validate(module)


@router.delete("/{module_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_module(
    module_id: UUID, user: CurrentUser, service: ModuleServiceDep
) -> None:
    """Delete a module."""
    await service.delete(user_id=user.uuid, module_id=module_id)
