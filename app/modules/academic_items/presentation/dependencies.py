"""FastAPI dependencies for the academic items module."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_session
from app.modules.academic_items.application.service import AcademicItemService
from app.modules.academic_items.infrastructure.repository import (
    AcademicItemRepository,
)
from app.modules.plan_modules.infrastructure.repository import ModuleRepository


def get_academic_item_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AcademicItemService:
    """Build an AcademicItemService wired to the request-scoped session."""
    return AcademicItemService(
        session, AcademicItemRepository(session), ModuleRepository(session)
    )


AcademicItemServiceDep = Annotated[
    AcademicItemService, Depends(get_academic_item_service)
]
