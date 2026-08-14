"""record what each generation run cost

The aggregate metrics answer "what is the AI costing us"; these columns answer
"what did *that* plan cost", which is the question somebody asks about one
teacher, one run, one surprise.

NOT NULL with a server default: existing runs get zero, which is honest. Their
cost was never measured and pretending otherwise, with a NULL that every query
then has to remember to coalesce, buys nothing.

Note for whoever regenerates a migration here: autogenerate proposes dropping
``uq_users_email_active`` and creating a plain ``ix_users_email``. It is wrong.
That index is partial (``WHERE deleted_at IS NULL``) so a soft-deleted account
frees its address; a plain unique index would forbid ever reusing it. The
proposal was removed by hand, as in every migration before this.

Revision ID: 92d818987519
Revises: 902bc620092e
Create Date: 2026-08-14 19:51:00.056095

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "92d818987519"
down_revision: str | None = "902bc620092e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "plan_generation",
        sa.Column("llm_calls", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "plan_generation",
        sa.Column(
            "llm_input_tokens", sa.BigInteger(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "plan_generation",
        sa.Column(
            "llm_output_tokens", sa.BigInteger(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "plan_generation",
        sa.Column(
            "llm_cost_usd",
            sa.Numeric(precision=12, scale=6),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("plan_generation", "llm_cost_usd")
    op.drop_column("plan_generation", "llm_output_tokens")
    op.drop_column("plan_generation", "llm_input_tokens")
    op.drop_column("plan_generation", "llm_calls")
