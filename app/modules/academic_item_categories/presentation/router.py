"""Academic item category HTTP endpoints (global catalogs, auth-protected)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.modules.academic_item_categories.domain.exceptions import (
    CategoryNotFoundError,
    CategoryTypeNotFoundError,
    InvalidCategoryError,
)
from app.modules.academic_item_categories.presentation.dependencies import (
    CategoryServiceDep,
    CategoryTypeServiceDep,
)
from app.modules.academic_item_categories.presentation.schemas import (
    CategoryCreate,
    CategoryResponse,
    CategoryTypeCreate,
    CategoryTypeResponse,
    CategoryTypeUpdate,
    CategoryUpdate,
)
from app.modules.auth.presentation.dependencies import CurrentUser

categories_router = APIRouter(
    prefix="/academic-item-categories", tags=["academic-item-categories"]
)
types_router = APIRouter(
    prefix="/academic-item-category-types",
    tags=["academic-item-category-types"],
)

_CATEGORY_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
)
_TYPE_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Category type not found"
)
_INVALID_CATEGORY = HTTPException(
    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    detail="Parent category not found",
)


# --------------------------------------------------------------------------- #
# Categories
# --------------------------------------------------------------------------- #
@categories_router.post(
    "", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED
)
async def create_category(
    payload: CategoryCreate, user: CurrentUser, service: CategoryServiceDep
) -> CategoryResponse:
    """Create a category."""
    category = await service.create(data=payload.model_dump())
    return CategoryResponse.model_validate(category)


@categories_router.get("", response_model=list[CategoryResponse])
async def list_categories(
    user: CurrentUser,
    service: CategoryServiceDep,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[CategoryResponse]:
    """List categories."""
    categories = await service.list(limit=limit, offset=offset)
    return [CategoryResponse.model_validate(c) for c in categories]


@categories_router.get("/{category_id}", response_model=CategoryResponse)
async def get_category(
    category_id: UUID, user: CurrentUser, service: CategoryServiceDep
) -> CategoryResponse:
    """Return a single category."""
    try:
        category = await service.get(category_id=category_id)
    except CategoryNotFoundError as exc:
        raise _CATEGORY_NOT_FOUND from exc
    return CategoryResponse.model_validate(category)


@categories_router.patch("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: UUID,
    payload: CategoryUpdate,
    user: CurrentUser,
    service: CategoryServiceDep,
) -> CategoryResponse:
    """Update a category."""
    try:
        category = await service.update(
            category_id=category_id, data=payload.model_dump(exclude_unset=True)
        )
    except CategoryNotFoundError as exc:
        raise _CATEGORY_NOT_FOUND from exc
    return CategoryResponse.model_validate(category)


@categories_router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: UUID, user: CurrentUser, service: CategoryServiceDep
) -> None:
    """Delete a category."""
    try:
        await service.delete(category_id=category_id)
    except CategoryNotFoundError as exc:
        raise _CATEGORY_NOT_FOUND from exc


# --------------------------------------------------------------------------- #
# Category types
# --------------------------------------------------------------------------- #
@types_router.post(
    "", response_model=CategoryTypeResponse, status_code=status.HTTP_201_CREATED
)
async def create_category_type(
    payload: CategoryTypeCreate,
    user: CurrentUser,
    service: CategoryTypeServiceDep,
) -> CategoryTypeResponse:
    """Create a category type under an existing category."""
    try:
        category_type = await service.create(data=payload.model_dump())
    except InvalidCategoryError as exc:
        raise _INVALID_CATEGORY from exc
    return CategoryTypeResponse.model_validate(category_type)


@types_router.get("", response_model=list[CategoryTypeResponse])
async def list_category_types(
    user: CurrentUser,
    service: CategoryTypeServiceDep,
    category_id: Annotated[UUID | None, Query()] = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[CategoryTypeResponse]:
    """List category types, optionally filtered by parent category."""
    types = await service.list(category_id=category_id, limit=limit, offset=offset)
    return [CategoryTypeResponse.model_validate(t) for t in types]


@types_router.get("/{type_id}", response_model=CategoryTypeResponse)
async def get_category_type(
    type_id: UUID, user: CurrentUser, service: CategoryTypeServiceDep
) -> CategoryTypeResponse:
    """Return a single category type."""
    try:
        category_type = await service.get(type_id=type_id)
    except CategoryTypeNotFoundError as exc:
        raise _TYPE_NOT_FOUND from exc
    return CategoryTypeResponse.model_validate(category_type)


@types_router.patch("/{type_id}", response_model=CategoryTypeResponse)
async def update_category_type(
    type_id: UUID,
    payload: CategoryTypeUpdate,
    user: CurrentUser,
    service: CategoryTypeServiceDep,
) -> CategoryTypeResponse:
    """Update a category type."""
    try:
        category_type = await service.update(
            type_id=type_id, data=payload.model_dump(exclude_unset=True)
        )
    except CategoryTypeNotFoundError as exc:
        raise _TYPE_NOT_FOUND from exc
    except InvalidCategoryError as exc:
        raise _INVALID_CATEGORY from exc
    return CategoryTypeResponse.model_validate(category_type)


@types_router.delete("/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category_type(
    type_id: UUID, user: CurrentUser, service: CategoryTypeServiceDep
) -> None:
    """Delete a category type."""
    try:
        await service.delete(type_id=type_id)
    except CategoryTypeNotFoundError as exc:
        raise _TYPE_NOT_FOUND from exc
