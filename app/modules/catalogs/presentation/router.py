"""Icon and color catalog HTTP endpoints (global catalogs, auth-protected)."""

from uuid import UUID

from fastapi import APIRouter, Query, status

from app.modules.auth.presentation.dependencies import CurrentAdmin, CurrentUser
from app.modules.catalogs.presentation.dependencies import (
    ColorServiceDep,
    IconServiceDep,
)
from app.modules.catalogs.presentation.schemas import (
    ColorCreate,
    ColorResponse,
    ColorUpdate,
    IconCreate,
    IconResponse,
    IconUpdate,
)

icons_router = APIRouter(prefix="/icons", tags=["icons"])
colors_router = APIRouter(prefix="/colors", tags=["colors"])


# --------------------------------------------------------------------------- #
# Icons
# --------------------------------------------------------------------------- #
@icons_router.post("", response_model=IconResponse, status_code=status.HTTP_201_CREATED)
async def create_icon(
    payload: IconCreate, user: CurrentAdmin, service: IconServiceDep
) -> IconResponse:
    """Create an icon (admin only)."""
    icon = await service.create(data=payload.model_dump())
    return IconResponse.model_validate(icon)


@icons_router.get("", response_model=list[IconResponse])
async def list_icons(
    user: CurrentUser,
    service: IconServiceDep,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[IconResponse]:
    """List icons."""
    icons = await service.list(limit=limit, offset=offset)
    return [IconResponse.model_validate(i) for i in icons]


@icons_router.get("/{icon_id}", response_model=IconResponse)
async def get_icon(
    icon_id: UUID, user: CurrentUser, service: IconServiceDep
) -> IconResponse:
    """Return a single icon."""
    icon = await service.get(icon_id=icon_id)
    return IconResponse.model_validate(icon)


@icons_router.patch("/{icon_id}", response_model=IconResponse)
async def update_icon(
    icon_id: UUID, payload: IconUpdate, user: CurrentAdmin, service: IconServiceDep
) -> IconResponse:
    """Update an icon (admin only)."""
    icon = await service.update(
        icon_id=icon_id, data=payload.model_dump(exclude_unset=True)
    )
    return IconResponse.model_validate(icon)


@icons_router.delete("/{icon_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_icon(
    icon_id: UUID, user: CurrentAdmin, service: IconServiceDep
) -> None:
    """Delete an icon (admin only)."""
    await service.delete(icon_id=icon_id)


# --------------------------------------------------------------------------- #
# Colors
# --------------------------------------------------------------------------- #
@colors_router.post(
    "", response_model=ColorResponse, status_code=status.HTTP_201_CREATED
)
async def create_color(
    payload: ColorCreate, user: CurrentAdmin, service: ColorServiceDep
) -> ColorResponse:
    """Create a color (admin only)."""
    color = await service.create(data=payload.model_dump())
    return ColorResponse.model_validate(color)


@colors_router.get("", response_model=list[ColorResponse])
async def list_colors(
    user: CurrentUser,
    service: ColorServiceDep,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[ColorResponse]:
    """List colors."""
    colors = await service.list(limit=limit, offset=offset)
    return [ColorResponse.model_validate(c) for c in colors]


@colors_router.get("/{color_id}", response_model=ColorResponse)
async def get_color(
    color_id: UUID, user: CurrentUser, service: ColorServiceDep
) -> ColorResponse:
    """Return a single color."""
    color = await service.get(color_id=color_id)
    return ColorResponse.model_validate(color)


@colors_router.patch("/{color_id}", response_model=ColorResponse)
async def update_color(
    color_id: UUID, payload: ColorUpdate, user: CurrentAdmin, service: ColorServiceDep
) -> ColorResponse:
    """Update a color (admin only)."""
    color = await service.update(
        color_id=color_id, data=payload.model_dump(exclude_unset=True)
    )
    return ColorResponse.model_validate(color)


@colors_router.delete("/{color_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_color(
    color_id: UUID, user: CurrentAdmin, service: ColorServiceDep
) -> None:
    """Delete a color (admin only)."""
    await service.delete(color_id=color_id)
