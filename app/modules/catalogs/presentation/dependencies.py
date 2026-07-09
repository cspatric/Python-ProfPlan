"""FastAPI dependencies for the catalogs module."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_session
from app.modules.catalogs.application.service import ColorService, IconService
from app.modules.catalogs.infrastructure.repository import (
    ColorRepository,
    IconRepository,
)


def get_icon_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IconService:
    """Build an IconService wired to the request-scoped session."""
    return IconService(session, IconRepository(session))


def get_color_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ColorService:
    """Build a ColorService wired to the request-scoped session."""
    return ColorService(session, ColorRepository(session))


IconServiceDep = Annotated[IconService, Depends(get_icon_service)]
ColorServiceDep = Annotated[ColorService, Depends(get_color_service)]
