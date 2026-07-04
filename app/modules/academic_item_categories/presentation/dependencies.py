"""FastAPI dependencies for the academic item categories module."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_session
from app.modules.academic_item_categories.application.service import (
    CategoryService,
    CategoryTypeService,
)
from app.modules.academic_item_categories.infrastructure.repository import (
    CategoryRepository,
    CategoryTypeRepository,
)


def get_category_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CategoryService:
    """Build a CategoryService wired to the request-scoped session."""
    return CategoryService(session, CategoryRepository(session))


def get_category_type_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CategoryTypeService:
    """Build a CategoryTypeService wired to the request-scoped session."""
    return CategoryTypeService(
        session, CategoryTypeRepository(session), CategoryRepository(session)
    )


CategoryServiceDep = Annotated[CategoryService, Depends(get_category_service)]
CategoryTypeServiceDep = Annotated[
    CategoryTypeService, Depends(get_category_type_service)
]
