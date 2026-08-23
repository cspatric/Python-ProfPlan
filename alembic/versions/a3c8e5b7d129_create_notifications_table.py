"""create notifications table

Reports finished background work to the person who asked for it: a plan that is
ready, a document that is now searchable. Both happen in a worker, minutes after
the request that started them returned, so there is nothing in the HTTP response
that could have said so.

The row stores a kind and its params, never a rendered sentence. The
interface is offered in three languages and the text is built by whoever
displays it — the same reason an API error carries a code. A message written
here would be frozen in whatever language the worker was configured with.

Revision ID: a3c8e5b7d129
Revises: f7b3c1d9e204
Create Date: 2026-08-23 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a3c8e5b7d129"
down_revision: str | None = "f7b3c1d9e204"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KINDS = (
    "plan_ready",
    "plan_partial",
    "plan_failed",
    "document_indexed",
    "document_failed",
)

#: Created and dropped explicitly; the column then references it with
#: `create_type=False`. Without that, `op.create_table` emits its own CREATE
#: TYPE for the same enum and the migration dies on a duplicate object.
_KIND_ENUM = sa.Enum(*_KINDS, name="notification_kind")
_KIND_COLUMN = postgresql.ENUM(*_KINDS, name="notification_kind", create_type=False)


def upgrade() -> None:
    _KIND_ENUM.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "notifications",
        sa.Column("uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", _KIND_COLUMN, nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("entity", sa.String(length=64), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.uuid"],
            name=op.f("fk_notifications_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("uuid", name=op.f("pk_notifications")),
    )
    # The listing: this user's notifications, newest first.
    op.create_index(
        "ix_notifications_user_created",
        "notifications",
        ["user_id", sa.text("created_at DESC")],
    )
    # The badge. Partial on purpose: the count only ever asks about unread rows,
    # and a full index would grow with every notification ever sent while
    # answering a question about the handful that are still new.
    op.create_index(
        "ix_notifications_user_unread",
        "notifications",
        ["user_id"],
        postgresql_where=sa.text("read_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_user_unread", table_name="notifications")
    op.drop_index("ix_notifications_user_created", table_name="notifications")
    op.drop_table("notifications")
    _KIND_ENUM.drop(op.get_bind(), checkfirst=True)
