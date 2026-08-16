"""SQLAlchemy model for a plan-generation run.

A run groups the subtasks (academic items) produced from one planner call. The
academic items themselves ARE the subtasks (they carry generation_status +
content); this table holds the roadmap and the overall run status.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
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

    # What this run cost. One plan is many calls (the planner, sometimes a
    # repair and a judge, then one per activity across several workers), so
    # these are accumulated with += rather than written once: the item workers
    # run at the same time and a read-modify-write in Python would lose most
    # of them.
    #
    # BigInteger for the token counts because a book-sized context times a
    # hundred activities passes two billion sooner than it sounds.
    llm_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    llm_input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    llm_output_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    # Numeric, not float: this is money, and it is summed across runs to answer
    # "what did this month cost". Six decimals because a cheap call on a cheap
    # model rounds to zero at four.
    llm_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, default=Decimal("0")
    )
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


class PlanGenerationModelUsage(Base):
    """What one model contributed to one generation run.

    A separate table rather than a column of JSON on the run, for one reason
    that decides it: a dozen activity workers finish at the same time and each
    has to add its own model's share. `INSERT ... ON CONFLICT DO UPDATE SET
    calls = calls + excluded.calls` is atomic; merging a JSON document from
    Python is a read-modify-write that loses most of them.

    It also makes the question "what does each model cost us" a GROUP BY
    instead of a document to parse.
    """

    __tablename__ = "plan_generation_model_usage"
    __table_args__ = (UniqueConstraint("generation_id", "model"),)

    uuid: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    generation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("plan_generation.uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: The id that was billed, profile prefix and all.
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, default=Decimal("0")
    )
