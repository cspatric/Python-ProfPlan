"""SQLAlchemy model for a plan-generation run.

A run groups the subtasks (academic items) produced from one planner call. The
academic items themselves ARE the subtasks (they carry generation_status +
content); this table holds the roadmap and the overall run status.
"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.modules.generation.domain.entities import GenerationRunStatus


class PlanGeneration(Base):
    """One AI generation run for a teaching plan."""

    __tablename__ = "plan_generation"

    uuid: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    plan_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("plans.uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[GenerationRunStatus] = mapped_column(
        Enum(GenerationRunStatus, name="generation_run_status"),
        nullable=False,
        default=GenerationRunStatus.PLANNING,
        index=True,
    )
    # The teacher's raw input parameters for the plan.
    input: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # The validated planner roadmap (for display/audit).
    roadmap: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class PlanDocument(Base):
    """Links a document (uploaded to a subject) to a specific plan.

    Many-to-many: a teacher picks which of the subject's documents a plan should
    be generated from. Documents stay owned by the subject (reusable); this only
    records the selection per plan.
    """

    __tablename__ = "plan_document"
    __table_args__ = (
        UniqueConstraint("plan_id", "document_id", name="uq_plan_document"),
    )

    uuid: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    plan_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("plans.uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("document.uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
