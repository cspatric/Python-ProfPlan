"""SQLAlchemy model for the users table."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.modules.users.domain.entities import UserRole, UserStatus


class User(Base):
    """A registered user account."""

    __tablename__ = "users"

    uuid: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(
        String(320), nullable=False, unique=True, index=True
    )
    # Null for an account that signs in with a provider and has no password of
    # its own. A placeholder hash would make "does this account have a
    # password" a question nothing can answer.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    profile_picture: Mapped[str | None] = mapped_column(String(1024))
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status"),
        nullable=False,
        default=UserStatus.ACTIVE,
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"),
        nullable=False,
        default=UserRole.USER,
        # SQLAlchemy stores the enum NAME, so the server default is "USER".
        server_default=UserRole.USER.name,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Null until the address is proven. Whether an unverified account may log
    # in is a policy switch (REQUIRE_EMAIL_VERIFICATION), not a schema one.
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
