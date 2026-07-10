"""SQLAlchemy models for the icon and color catalogs."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class Icon(Base):
    """A local SVG icon, served from /static/icons, usable by any catalog."""

    __tablename__ = "icons"
    __table_args__ = (
        # Only active (non-deleted) names must be unique, so a deleted icon's
        # name can be reused.
        Index(
            "uq_icons_name_active",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    uuid: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Relative path under app/static, e.g. "icons/mathematics.svg".
    file_path: Mapped[str] = mapped_column(String(255), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Color(Base):
    """A pastel color, usable by any catalog."""

    __tablename__ = "colors"
    __table_args__ = (
        Index(
            "uq_colors_name_active",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    uuid: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # "#RRGGBB".
    hex_code: Mapped[str] = mapped_column(String(7), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
