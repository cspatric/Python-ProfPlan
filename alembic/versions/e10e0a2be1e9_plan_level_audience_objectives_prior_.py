"""plan: level, audience, objectives, prior knowledge and resources

Revision ID: e10e0a2be1e9
Revises: 31c3d165d76f
Create Date: 2026-08-12 22:26:38.114312

All five columns are nullable: plans created before this migration, and plans
created from the calendar fields alone, keep working untouched.

Autogenerate again proposed dropping ``uq_users_email_active`` and replacing it
with a plain unique index on ``users.email``. Those two lines were removed by
hand, for the second time. That index is *partial* (``WHERE deleted_at IS
NULL``) so a soft-deleted account's address can be registered again; a plain
unique index would silently take that away. Autogenerate cannot see the
predicate and will keep proposing it. Leave it out.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e10e0a2be1e9"
down_revision: str | None = "31c3d165d76f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# create_type=False: the type is created explicitly below. `op.add_column`
# does NOT emit CREATE TYPE on its own (unlike create_table), so relying on it
# leaves the second upgrade failing with "type plan_level does not exist".
_PLAN_LEVEL = postgresql.ENUM(
    "INTRODUCTORY",
    "INTERMEDIATE",
    "ADVANCED",
    name="plan_level",
    create_type=False,
)


def upgrade() -> None:
    _PLAN_LEVEL.create(op.get_bind(), checkfirst=True)
    op.add_column("plans", sa.Column("level", _PLAN_LEVEL, nullable=True))
    op.add_column("plans", sa.Column("audience", sa.Text(), nullable=True))
    op.add_column("plans", sa.Column("objectives", sa.Text(), nullable=True))
    op.add_column("plans", sa.Column("prior_knowledge", sa.Text(), nullable=True))
    op.add_column("plans", sa.Column("resources", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("plans", "resources")
    op.drop_column("plans", "prior_knowledge")
    op.drop_column("plans", "objectives")
    op.drop_column("plans", "audience")
    op.drop_column("plans", "level")
    # Dropped explicitly: the column going away does not remove the type,
    # and leaving it behind makes the next upgrade fail on CREATE TYPE.
    _PLAN_LEVEL.drop(op.get_bind(), checkfirst=True)
