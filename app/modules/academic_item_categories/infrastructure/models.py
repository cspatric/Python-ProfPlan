"""SQLAlchemy models for academic item category catalogs."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class AcademicItemCategory(Base):
    """A category of academic items (global catalog)."""

    __tablename__ = "academic_item_category"

    uuid: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Soft reference (no target table yet): icons catalog.
    icon_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AcademicItemCategoryType(Base):
    """A type belonging to an academic item category (global catalog)."""

    __tablename__ = "academic_item_category_types"

    uuid: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    academic_item_category_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("academic_item_category.uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    icon_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
