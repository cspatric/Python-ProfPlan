"""Audit trail API (admin-only)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.modules.audit.domain.entities import AuditAction
from app.modules.audit.presentation.dependencies import AuditQueryServiceDep
from app.modules.audit.presentation.schemas import AuditLogResponse
from app.modules.auth.presentation.dependencies import CurrentAdmin

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("", response_model=list[AuditLogResponse])
async def list_audit_logs(
    _admin: CurrentAdmin,
    service: AuditQueryServiceDep,
    entity: Annotated[str | None, Query()] = None,
    entity_id: Annotated[UUID | None, Query()] = None,
    actor_id: Annotated[UUID | None, Query()] = None,
    action: Annotated[AuditAction | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AuditLogResponse]:
    """List audit entries. Filter by entity, entity_id, actor or action."""
    return await service.list(
        entity=entity,
        entity_id=entity_id,
        actor_id=actor_id,
        action=action,
        limit=limit,
        offset=offset,
    )
