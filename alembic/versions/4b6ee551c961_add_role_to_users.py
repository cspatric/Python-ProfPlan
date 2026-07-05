"""add role to users

Revision ID: 4b6ee551c961
Revises: 67031a2aa077
Create Date: 2026-07-05 00:31:22.074749

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '4b6ee551c961'
down_revision: str | None = '67031a2aa077'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    user_role = postgresql.ENUM("USER", "ADMIN", name="user_role")
    user_role.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "users",
        sa.Column(
            "role",
            postgresql.ENUM(
                "USER", "ADMIN", name="user_role", create_type=False
            ),
            server_default="USER",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "role")
    postgresql.ENUM(name="user_role").drop(op.get_bind(), checkfirst=True)
