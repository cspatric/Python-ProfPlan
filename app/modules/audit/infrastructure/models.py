"""SQLAlchemy model for the audit_logs table.

The authoritative business-audit trail: who did what to which entity and when.
`entity_id` is a plain (unconstrained) UUID on purpose — the table is
polymorphic across entities, and a DELETE audit row must survive the deletion of
the row it describes, so there is no foreign key to the audited entity.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.modules.audit.domain.entities import AuditAction


class AuditLog(Base):
    """A single recorded business action (create/update/delete)."""

    __tablename__ = "audit_logs"

    uuid: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    # Kept nullable + SET NULL: deleting a user must not erase their audit trail;
    # actor_email is denormalized so the actor stays identifiable afterwards.
    actor_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.uuid", ondelete="SET NULL"),
        index=True,
    )
    actor_email: Mapped[str | None] = mapped_column(String(320))
    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction, name="audit_action"), nullable=False
    )
    entity: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    # Full snapshot (create/delete) or per-field {old, new} diff (update).
    changes: Mapped[dict | None] = mapped_column(JSONB)
    # Correlates to the HTTP access log (Loki) and trace (Tempo).
    request_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    __table_args__ = (
        # "Full history of entity X" is the primary query.
        Index("ix_audit_logs_entity_entity_id", "entity", "entity_id"),
    )
