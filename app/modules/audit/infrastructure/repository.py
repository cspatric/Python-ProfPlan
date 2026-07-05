"""Data access for audit logs."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.domain.entities import AuditAction
from app.modules.audit.infrastructure.models import AuditLog


class AuditRepository:
    """Reads and writes audit_logs."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, log: AuditLog) -> None:
        """Stage an audit row in the caller's transaction (no commit here)."""
        self._session.add(log)

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
        """List audit rows (most recent first) matching the given filters."""
        stmt = select(AuditLog)
        if entity is not None:
            stmt = stmt.where(AuditLog.entity == entity)
        if entity_id is not None:
            stmt = stmt.where(AuditLog.entity_id == entity_id)
        if actor_id is not None:
            stmt = stmt.where(AuditLog.actor_id == actor_id)
        if action is not None:
            stmt = stmt.where(AuditLog.action == action)
        stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.scalars(stmt)
        return list(result.all())
