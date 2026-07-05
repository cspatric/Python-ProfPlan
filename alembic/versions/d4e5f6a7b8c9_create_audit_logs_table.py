"""create audit_logs table

Revision ID: d4e5f6a7b8c9
Revises: 4b6ee551c961
Create Date: 2026-07-05 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "4b6ee551c961"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    audit_action = postgresql.ENUM(
        "CREATE", "UPDATE", "DELETE", name="audit_action"
    )
    audit_action.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "audit_logs",
        sa.Column("uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_email", sa.String(length=320), nullable=True),
        sa.Column(
            "action",
            postgresql.ENUM(
                "CREATE", "UPDATE", "DELETE", name="audit_action", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("entity", sa.String(length=64), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.uuid"],
            name="fk_audit_logs_actor_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("uuid", name="pk_audit_logs"),
    )
    op.create_index(
        op.f("ix_audit_logs_actor_id"), "audit_logs", ["actor_id"], unique=False
    )
    op.create_index(
        op.f("ix_audit_logs_created_at"), "audit_logs", ["created_at"], unique=False
    )
    op.create_index(
        "ix_audit_logs_entity_entity_id",
        "audit_logs",
        ["entity", "entity_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_entity_entity_id", table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_created_at"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_actor_id"), table_name="audit_logs")
    op.drop_table("audit_logs")
    postgresql.ENUM(name="audit_action").drop(op.get_bind(), checkfirst=True)
