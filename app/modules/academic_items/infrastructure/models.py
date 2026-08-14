"""SQLAlchemy models for academic items and the passages they were written from."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.modules.generation.domain.entities import GenerationItemStatus


class AcademicItem(Base):
    """An academic item (activity, evaluation, ...) inside a module."""

    __tablename__ = "academic_items"

    uuid: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    module_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("modules.uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Soft reference (no target table yet): item category catalog.
    item_category_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    content: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # AI generation lifecycle. Null on manually-created items; set only on items
    # produced by a plan-generation run. The generated content lands in `content`.
    generation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("plan_generation.uuid", ondelete="CASCADE"),
        index=True,
    )
    generation_status: Mapped[GenerationItemStatus | None] = mapped_column(
        Enum(GenerationItemStatus, name="generation_item_status")
    )
    generation_prompt: Mapped[str | None] = mapped_column(Text)
    generation_error: Mapped[str | None] = mapped_column(Text)
    # `metadata` is reserved by SQLAlchemy's Declarative API, so the attribute
    # is named `item_metadata` while the DB column stays `metadata`.
    item_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    created_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.uuid", ondelete="SET NULL"),
        index=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AcademicItemSource(Base):
    """A passage that fed the generation of one academic item.

    This is the difference between "the AI wrote this" and "the AI wrote this
    from page 41 of the book you uploaded". Without it the teacher has no way
    to tell a paragraph grounded in their own material from one the model
    produced out of its own memory, and both look equally confident.

    **The passage is copied, not referenced.** A citation that is only a
    foreign key to `chunks` breaks the next time the document is re-ingested,
    because re-ingestion replaces every chunk. What is being recorded here is
    not what the document says today: it is what was actually put in front of
    the model on the day it wrote this, which is the only thing that can honour
    or contradict the claim. `chunk_id` is kept alongside, nullable, so a live
    link exists while the chunk does.
    """

    __tablename__ = "academic_item_source"
    __table_args__ = (
        UniqueConstraint("academic_item_id", "rank"),
        # The one query this table has: every source of one item, in order.
        Index("ix_academic_item_source_item_rank", "academic_item_id", "rank"),
    )

    uuid: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    academic_item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("academic_items.uuid", ondelete="CASCADE"),
        nullable=False,
    )
    # A soft reference on purpose, with no foreign key. Two reasons, and the
    # second is the one that matters: the citation outlives the chunk, and a
    # re-ingestion that lands *between* retrieval and this insert would
    # otherwise fail the whole activity over a pointer that is a convenience.
    # Nothing may break the generation to record where it came from. Uuids are
    # never reused, so a dangling id is dangling, never wrong.
    chunk_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    document_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("document.uuid", ondelete="SET NULL"),
        index=True,
    )
    #: 1-based, and the same number the prompt used, so "[2]" in the generated
    #: text points at the second source here rather than at nothing.
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Cosine distance at retrieval time (lower is closer). Kept because a
    #: source at 0.55 is a much weaker claim than one at 0.15, and the reader
    #: deserves to see which kind they are looking at.
    distance: Mapped[float | None] = mapped_column(Float)
    #: The heading breadcrumb the chunker put on the passage, e.g.
    #: "Chapter 2 > Gradient Descent". This is what makes a citation readable
    #: instead of a uuid.
    section: Mapped[str | None] = mapped_column(String(512))
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
