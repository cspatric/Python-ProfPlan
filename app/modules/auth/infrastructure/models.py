"""SQLAlchemy models for authentication: providers, sessions and audit logs."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class AuthEvent(StrEnum):
    """Auditable authentication events."""

    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    LOGIN_RATE_LIMITED = "login_rate_limited"
    TOKEN_REFRESHED = "token_refreshed"
    TOKEN_REUSE_DETECTED = "token_reuse_detected"
    LOGOUT = "logout"
    LOGOUT_ALL = "logout_all"
    PASSWORD_RESET_REQUESTED = "password_reset_requested"
    PASSWORD_RESET_COMPLETED = "password_reset_completed"
    EMAIL_VERIFICATION_SENT = "email_verification_sent"
    EMAIL_VERIFIED = "email_verified"


class VerificationPurpose(StrEnum):
    """What a one-time token is allowed to do.

    The purpose is part of the lookup, so a token minted to verify an address
    can never be replayed to reset a password.
    """

    PASSWORD_RESET = "password_reset"
    EMAIL_VERIFICATION = "email_verification"


class Provider(Base):
    """An external identity provider (OAuth), modelled for future use."""

    __tablename__ = "providers"

    uuid: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UserProvider(Base):
    """Link between a user and an external provider identity."""

    __tablename__ = "user_providers"
    __table_args__ = (UniqueConstraint("provider_id", "provider_user_id"),)

    uuid: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("providers.uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RefreshToken(Base):
    """A refresh-token session. The token is stored only as a hash."""

    __tablename__ = "refresh_tokens"

    uuid: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Looked up only by primary key (session id), never by the hash itself,
    # so token_hash is intentionally not indexed.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(512))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    # Indexed to support pruning of expired sessions.
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AuthLog(Base):
    """Audit trail of authentication events."""

    __tablename__ = "auth_logs"

    uuid: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.uuid", ondelete="SET NULL"),
        index=True,
    )
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    event: Mapped[AuthEvent] = mapped_column(
        Enum(AuthEvent, name="auth_event"), nullable=False
    )
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    # Indexed for time-ranged audit queries and log pruning.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )


class VerificationToken(Base):
    """A single-use, expiring token for password reset or email verification.

    Only the SHA-256 hash is stored, the same discipline as refresh tokens: a
    database leak must not hand an attacker the ability to reset accounts. The
    raw value exists exactly once, in the email that was sent.
    """

    __tablename__ = "verification_tokens"
    __table_args__ = (
        # Every lookup is "find the live token with this hash for this
        # purpose", so that pair is the index.
        Index("ix_verification_tokens_hash_purpose", "token_hash", "purpose"),
    )

    uuid: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    purpose: Mapped[VerificationPurpose] = mapped_column(
        Enum(VerificationPurpose, name="verification_purpose"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Set the moment the token is spent. Single use is what stops a reset link
    # forwarded to the wrong inbox, or sitting in a mail archive, from working
    # a second time.
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
