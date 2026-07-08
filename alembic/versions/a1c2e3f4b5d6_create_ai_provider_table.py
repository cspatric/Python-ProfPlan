"""create ai_provider table

Revision ID: a1c2e3f4b5d6
Revises: e5a1b2c3d4f0
Create Date: 2026-07-08 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a1c2e3f4b5d6"
down_revision: str | None = "e5a1b2c3d4f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PROVIDERS = ("claude", "openai", "gemini", "ollama")


def upgrade() -> None:
    op.create_table(
        "ai_provider",
        sa.Column("uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("uuid", name="pk_ai_provider"),
    )
    op.create_index(
        op.f("ix_ai_provider_name"), "ai_provider", ["name"], unique=True
    )

    # Seed the fallback chain (all enabled by default).
    for name in _PROVIDERS:
        op.execute(
            f"INSERT INTO ai_provider (uuid, name, enabled) "
            f"VALUES (gen_random_uuid(), '{name}', true)"
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_ai_provider_name"), table_name="ai_provider")
    op.drop_table("ai_provider")
