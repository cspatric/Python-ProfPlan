"""SQLAlchemy model for the academic_items table."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
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
