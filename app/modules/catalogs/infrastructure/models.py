"""SQLAlchemy models for the icon and color catalogs."""

from uuid import UUID, uuid4

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class Icon(Base):
    """A local SVG icon, served from /static/icons, usable by any catalog."""

    __tablename__ = "icons"

    uuid: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    # Relative path under app/static, e.g. "icons/mathematics.svg".
    file_path: Mapped[str] = mapped_column(String(255), nullable=False)


class Color(Base):
    """A pastel color, usable by any catalog."""

    __tablename__ = "colors"

    uuid: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    # "#RRGGBB".
    hex_code: Mapped[str] = mapped_column(String(7), nullable=False)
