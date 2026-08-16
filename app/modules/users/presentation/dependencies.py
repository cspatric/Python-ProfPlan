"""FastAPI dependencies for the account data endpoints."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_session
from app.infrastructure.storage.minio import get_object_storage
from app.modules.users.application.account_data_service import AccountDataService


def get_account_data_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AccountDataService:
    """Build the service that exports and erases an account."""
    return AccountDataService(session, get_object_storage())


AccountDataServiceDep = Annotated[AccountDataService, Depends(get_account_data_service)]
