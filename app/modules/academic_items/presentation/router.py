"""Academic item HTTP endpoints."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.modules.academic_items.domain.exceptions import (
    AcademicItemNotFoundError,
    InvalidModuleError,
)
from app.modules.academic_items.infrastructure.models import AcademicItem
from app.modules.academic_items.presentation.dependencies import (
    AcademicItemServiceDep,
)
from app.modules.academic_items.presentation.schemas import (
    AcademicItemCreate,
    AcademicItemResponse,
    AcademicItemUpdate,
)
from app.modules.auth.presentation.dependencies import CurrentUser

router = APIRouter(prefix="/academic-items", tags=["academic-items"])

_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Academic item not found"
)
_INVALID_MODULE = HTTPException(
    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    detail="Module not found or not owned by the user",
)


def _create_data(payload: AcademicItemCreate) -> dict[str, Any]:
    return {
        "module_id": payload.module_id,
        "item_category_id": payload.item_category_id,
        "title": payload.title,
        "description": payload.description,
        "content": payload.content,
        "item_metadata": (
            payload.metadata.model_dump(mode="json") if payload.metadata else None
        ),
    }


def _update_data(payload: AcademicItemUpdate) -> dict[str, Any]:
    fields = payload.model_dump(exclude_unset=True)
    data: dict[str, Any] = {}
    for key in ("module_id", "item_category_id", "title", "description", "content"):
        if key in fields:
            data[key] = getattr(payload, key)
    if "metadata" in fields:
        data["item_metadata"] = (
            payload.metadata.model_dump(mode="json") if payload.metadata else None
        )
    return data


def _to_response(item: AcademicItem) -> AcademicItemResponse:
    return AcademicItemResponse(
        uuid=item.uuid,
        user_id=item.user_id,
        module_id=item.module_id,
        item_category_id=item.item_category_id,
        title=item.title,
        description=item.description,
        content=item.content,
        metadata=item.item_metadata,
        created_by=item.created_by,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.post(
    "", response_model=AcademicItemResponse, status_code=status.HTTP_201_CREATED
)
async def create_academic_item(
    payload: AcademicItemCreate,
    user: CurrentUser,
    service: AcademicItemServiceDep,
) -> AcademicItemResponse:
    """Create an academic item under a module owned by the user."""
    try:
        item = await service.create(user_id=user.uuid, data=_create_data(payload))
    except InvalidModuleError as exc:
        raise _INVALID_MODULE from exc
    return _to_response(item)


@router.get("", response_model=list[AcademicItemResponse])
async def list_academic_items(
    module_id: UUID,
    user: CurrentUser,
    service: AcademicItemServiceDep,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[AcademicItemResponse]:
    """List the academic items of a module owned by the user."""
    try:
        items = await service.list(
            user_id=user.uuid, module_id=module_id, limit=limit, offset=offset
        )
    except InvalidModuleError as exc:
        raise _INVALID_MODULE from exc
    return [_to_response(item) for item in items]


@router.get("/{item_id}", response_model=AcademicItemResponse)
async def get_academic_item(
    item_id: UUID, user: CurrentUser, service: AcademicItemServiceDep
) -> AcademicItemResponse:
    """Return a single academic item."""
    try:
        item = await service.get(user_id=user.uuid, item_id=item_id)
    except AcademicItemNotFoundError as exc:
        raise _NOT_FOUND from exc
    return _to_response(item)


@router.patch("/{item_id}", response_model=AcademicItemResponse)
async def update_academic_item(
    item_id: UUID,
    payload: AcademicItemUpdate,
    user: CurrentUser,
    service: AcademicItemServiceDep,
) -> AcademicItemResponse:
    """Update an academic item."""
    try:
        item = await service.update(
            user_id=user.uuid, item_id=item_id, data=_update_data(payload)
        )
    except AcademicItemNotFoundError as exc:
        raise _NOT_FOUND from exc
    except InvalidModuleError as exc:
        raise _INVALID_MODULE from exc
    return _to_response(item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_academic_item(
    item_id: UUID, user: CurrentUser, service: AcademicItemServiceDep
) -> None:
    """Soft-delete an academic item."""
    try:
        await service.delete(user_id=user.uuid, item_id=item_id)
    except AcademicItemNotFoundError as exc:
        raise _NOT_FOUND from exc
