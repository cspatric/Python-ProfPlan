"""SQLAlchemy model for the plans table."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class Plan(Base):
    """A teaching plan for a subject, owned by a user."""

    __tablename__ = "plans"

    uuid: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subject_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("subjects.uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    starts_at: Mapped[date] = mapped_column(Date, nullable=False)
    ends_at: Mapped[date] = mapped_column(Date, nullable=False)
    class_duration: Mapped[int] = mapped_column(Integer, nullable=False)
    class_per_week: Mapped[int] = mapped_column(Integer, nullable=False)
    total_weight: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    # Soft reference (no target table yet): academic items collection.
    academic_items_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
