"""Notifications API."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.modules.auth.presentation.dependencies import CurrentUser
from app.modules.notifications.presentation.dependencies import (
    NotificationServiceDep,
)
from app.modules.notifications.presentation.schemas import (
    MarkAllReadResponse,
    NotificationPageResponse,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationPageResponse)
async def list_notifications(
    user: CurrentUser,
    service: NotificationServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> NotificationPageResponse:
    """This user's notifications, newest first, with the unread count.

    Both in one answer because the bell needs both to draw itself once: the list
    fills the panel and the count is the badge. Two endpoints would put a second
    round trip in front of a menu that opens on a click.
    """
    page = await service.page(user_id=user.uuid, limit=limit, offset=offset)
    return NotificationPageResponse.model_validate(
        {"items": page.items, "unread": page.unread}, from_attributes=True
    )


@router.patch("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(
    notification_id: UUID, user: CurrentUser, service: NotificationServiceDep
) -> None:
    """Mark one as read. Idempotent — reading it twice is not an error."""
    await service.mark_read(user_id=user.uuid, notification_id=notification_id)


@router.post("/read-all", response_model=MarkAllReadResponse)
async def mark_all_read(
    user: CurrentUser, service: NotificationServiceDep
) -> MarkAllReadResponse:
    """Clear the badge in one call, which is what opening the panel means."""
    return MarkAllReadResponse(updated=await service.mark_all_read(user_id=user.uuid))
