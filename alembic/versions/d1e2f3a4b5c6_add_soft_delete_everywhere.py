"""add soft delete (deleted_at) everywhere

Revision ID: d1e2f3a4b5c6
Revises: c3e5a7b9d1f2
Create Date: 2026-07-10 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: str | None = "c3e5a7b9d1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "subjects",
    "plans",
    "modules",
    "academic_item_category",
    "academic_item_category_types",
    "icons",
    "colors",
)


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table, sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
        )

    # icons/colors/users.email were plain-unique; once "deleted" rows keep
    # occupying their name/email, only ACTIVE rows need to stay unique so a
    # deleted one's name/email can be reused.
    op.drop_index(op.f("ix_icons_name"), table_name="icons")
    op.create_index(
        "uq_icons_name_active", "icons", ["name"], unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.drop_index(op.f("ix_colors_name"), table_name="colors")
    op.create_index(
        "uq_colors_name_active", "colors", ["name"], unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.create_index(
        "uq_users_email_active", "users", ["email"], unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_users_email_active", table_name="users")
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.drop_index("uq_colors_name_active", table_name="colors")
    op.create_index(op.f("ix_colors_name"), "colors", ["name"], unique=True)

    op.drop_index("uq_icons_name_active", table_name="icons")
    op.create_index(op.f("ix_icons_name"), "icons", ["name"], unique=True)

    for table in reversed(_TABLES):
        op.drop_column(table, "deleted_at")
