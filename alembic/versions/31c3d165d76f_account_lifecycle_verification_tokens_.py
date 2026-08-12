"""account lifecycle: verification tokens and email_verified_at

Revision ID: 31c3d165d76f
Revises: d1e2f3a4b5c6
Create Date: 2026-08-12 18:51:09.344021

Autogenerate also proposed dropping ``uq_users_email_active`` and replacing it
with a plain unique index on ``users.email``. Those lines were removed by hand.
``uq_users_email_active`` is a *partial* unique index (``WHERE deleted_at IS
NULL``) introduced with soft delete, so that a deleted account's address can be
registered again while active addresses stay unique. A plain unique index would
silently take that away. Autogenerate cannot see the predicate, so it reports
the index as missing on every run: leave those two lines out again next time.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "31c3d165d76f"
down_revision: str | None = "d1e2f3a4b5c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "verification_tokens",
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "purpose",
            sa.Enum(
                "PASSWORD_RESET", "EMAIL_VERIFICATION", name="verification_purpose"
            ),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_ip", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.uuid"],
            name=op.f("fk_verification_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("uuid", name=op.f("pk_verification_tokens")),
    )
    # Every lookup is "the live token with this hash, for this purpose".
    op.create_index(
        "ix_verification_tokens_hash_purpose",
        "verification_tokens",
        ["token_hash", "purpose"],
        unique=False,
    )
    op.create_index(
        op.f("ix_verification_tokens_user_id"),
        "verification_tokens",
        ["user_id"],
        unique=False,
    )
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Autogenerate does not detect new members of an existing enum: it compares
    # tables and columns, not type labels. Without these four the app inserts a
    # label Postgres has never heard of and the request 500s, which is exactly
    # how this was found. Labels are the member NAMES because that is what
    # SQLAlchemy persists for Enum(AuthEvent).
    for label in (
        "PASSWORD_RESET_REQUESTED",
        "PASSWORD_RESET_COMPLETED",
        "EMAIL_VERIFICATION_SENT",
        "EMAIL_VERIFIED",
    ):
        op.execute(f"ALTER TYPE auth_event ADD VALUE IF NOT EXISTS '{label}'")


def downgrade() -> None:
    # The enum labels are deliberately left in place. Postgres cannot drop a
    # value from an enum, and rebuilding the type would mean rewriting every
    # auth_logs row for four unused labels that harm nothing.
    op.drop_column("users", "email_verified_at")
    op.drop_index(
        op.f("ix_verification_tokens_user_id"), table_name="verification_tokens"
    )
    op.drop_index(
        "ix_verification_tokens_hash_purpose", table_name="verification_tokens"
    )
    op.drop_table("verification_tokens")
    # The enum type is created implicitly with the table above, so it has to go
    # explicitly here or a re-upgrade fails with "type already exists".
    sa.Enum(name="verification_purpose").drop(op.get_bind(), checkfirst=True)
