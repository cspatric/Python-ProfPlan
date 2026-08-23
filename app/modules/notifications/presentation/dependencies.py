"""FastAPI dependencies for the notifications module."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_session
from app.modules.notifications.application.service import NotificationService
from app.modules.notifications.infrastructure.repository import (
    NotificationRepository,
)


def get_notification_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> NotificationService:
    """Build a NotificationService wired to the request-scoped session."""
    return NotificationService(session, NotificationRepository(session))


NotificationServiceDep = Annotated[
    NotificationService, Depends(get_notification_service)
]
