"""SQLAlchemy model for the notifications table.

``entity_id`` is a plain, unconstrained UUID, exactly as in the audit trail and
for the same reason: the table is polymorphic across entities, and a
notification about a document must survive that document being deleted. A
client that follows a dead link gets a 404, which is the honest answer; a
foreign key would instead delete the notification and leave the person
wondering what the alert they half-read had been about.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.modules.notifications.domain.entities import NotificationKind


class Notification(Base):
    """One event reported to one user."""

    __tablename__ = "notifications"

    uuid: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    #: The recipient, and the ownership scope every read filters on.
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.uuid", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[NotificationKind] = mapped_column(
        Enum(
            NotificationKind,
            name="notification_kind",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    #: What the message interpolates: a plan's title, a document's name, a count.
    #: Stored rather than joined, so a notification still reads correctly after
    #: the thing it describes has been renamed or deleted.
    params: Mapped[dict | None] = mapped_column(JSONB)
    entity: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    #: Null means unread. A timestamp rather than a boolean: "when did they see
    #: this" is a question that gets asked, and it costs the same to store.
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # The listing: this user's notifications, newest first.
        Index("ix_notifications_user_created", "user_id", created_at.desc()),
        # The badge. Partial, because the count only ever asks about unread
        # rows and a full index would grow with every notification ever sent
        # while answering a question about the handful that are still new.
        Index(
            "ix_notifications_user_unread",
            "user_id",
            postgresql_where=read_at.is_(None),
        ),
    )
