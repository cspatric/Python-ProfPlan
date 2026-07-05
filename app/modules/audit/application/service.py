"""Audit query use cases (read side)."""

from uuid import UUID

from app.modules.audit.domain.entities import AuditAction
from app.modules.audit.infrastructure.models import AuditLog
from app.modules.audit.infrastructure.repository import AuditRepository


class AuditQueryService:
    """Read-only access to the audit trail."""

    def __init__(self, repository: AuditRepository) -> None:
        self._repo = repository

    async def list(
        self,
        *,
        entity: str | None = None,
        entity_id: UUID | None = None,
        actor_id: UUID | None = None,
        action: AuditAction | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditLog]:
        """List audit entries (most recent first) for the given filters."""
        return await self._repo.list(
            entity=entity,
            entity_id=entity_id,
            actor_id=actor_id,
            action=action,
            limit=limit,
            offset=offset,
        )
