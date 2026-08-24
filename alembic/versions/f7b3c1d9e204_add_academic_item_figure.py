"""add academic_item_figure

Illustrations for generated items. The bytes live in object storage and only the
path is here, exactly as with an uploaded document.

``licence`` and ``attribution`` are NOT NULL-adjacent by intent: they are the
credit line that must be printed beside the image, and they are stored rather
than re-fetched so a handout reprinted next semester carries the same credit as
the one handed out today.

Revision ID: f7b3c1d9e204
Revises: c7d1e2f3a4b5
Create Date: 2026-08-23 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f7b3c1d9e204"
down_revision: str | None = "c7d1e2f3a4b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Created and dropped explicitly below. The column then references it with
#: ``create_type=False``: without that, ``op.create_table`` emits its own
#: CREATE TYPE for the same enum and the migration dies on a duplicate object.
_FIGURE_SOURCE_NAME = "figure_source"
_FIGURE_SOURCE = sa.Enum("wikimedia", name=_FIGURE_SOURCE_NAME)
_FIGURE_SOURCE_COLUMN = postgresql.ENUM(
    "wikimedia", name=_FIGURE_SOURCE_NAME, create_type=False
)


def upgrade() -> None:
    _FIGURE_SOURCE.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "academic_item_figure",
        sa.Column("uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("academic_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("query", sa.String(length=300), nullable=False),
        sa.Column("alt_text", sa.String(length=500), nullable=False),
        sa.Column("caption", sa.String(length=500), nullable=True),
        sa.Column("source", _FIGURE_SOURCE_COLUMN, nullable=False),
        sa.Column("source_url", sa.String(length=1024), nullable=True),
        sa.Column("figure_path", sa.String(length=1024), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("licence", sa.String(length=200), nullable=False),
        sa.Column("licence_url", sa.String(length=1024), nullable=True),
        sa.Column("attribution", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["academic_item_id"],
            ["academic_items.uuid"],
            name=op.f("fk_academic_item_figure_academic_item_id_academic_items"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.uuid"],
            name=op.f("fk_academic_item_figure_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("uuid", name=op.f("pk_academic_item_figure")),
    )
    # Every read is "this item's figures, in order".
    op.create_index(
        "ix_academic_item_figure_item_position",
        "academic_item_figure",
        ["academic_item_id", "position"],
    )
    # And every read is also scoped to the owner, which is what the repository
    # filters on without a join.
    op.create_index(
        op.f("ix_academic_item_figure_user_id"),
        "academic_item_figure",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_academic_item_figure_user_id"), table_name="academic_item_figure"
    )
    op.drop_index(
        "ix_academic_item_figure_item_position", table_name="academic_item_figure"
    )
    op.drop_table("academic_item_figure")
    _FIGURE_SOURCE.drop(op.get_bind(), checkfirst=True)
