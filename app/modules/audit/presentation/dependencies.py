"""FastAPI dependencies for the audit module."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_session
from app.modules.audit.application.recorder import AuditRecorder
from app.modules.audit.application.service import AuditQueryService
from app.modules.audit.domain.entities import AuditContext
from app.modules.audit.infrastructure.repository import AuditRepository
from app.modules.auth.presentation.dependencies import CurrentUser


def get_audit_recorder(
    request: Request,
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuditRecorder:
    """Build a recorder bound to the acting user and current request.

    Uses the same request-scoped session as the business service (FastAPI caches
    `get_session` per request), so audit rows commit in the same transaction.
    """
    context = AuditContext(
        actor_id=user.uuid,
        actor_email=user.email,
        request_id=getattr(request.state, "request_id", None),
    )
    return AuditRecorder(AuditRepository(session), context)


AuditRecorderDep = Annotated[AuditRecorder, Depends(get_audit_recorder)]


def get_audit_query_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuditQueryService:
    """Build the read-side audit query service."""
    return AuditQueryService(AuditRepository(session))


AuditQueryServiceDep = Annotated[AuditQueryService, Depends(get_audit_query_service)]
