"""consolidate remote llms on bedrock

The fallback chain keeps running across several model families — Anthropic's
Claude, Amazon's Nova, OpenAI's open-weight models — but every one of them is
now reached through Amazon Bedrock instead of through a direct vendor API. One
account, one bill, one credential, one quota.

Two consequences for this table, which is the source of truth for whether a
link of the chain is turned on:

* ``gemini`` goes. Bedrock does not serve Google's models, so that family has
  no route any more and its row is a switch that turns off nothing.
* ``nova`` arrives. It heads the fast chain, and without a row an admin could
  not disable the family that answers most of the calls.

``claude`` and ``openai`` keep their rows: the names are model families, not
vendors, and both families still answer — over Bedrock now.

Revision ID: c7d1e2f3a4b5
Revises: 359ce9c315f4
Create Date: 2026-08-21 22:30:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7d1e2f3a4b5"
down_revision: str | None = "359ce9c315f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Families that answer through Bedrock, plus the local floor. Anything else in
#: the table has no route and is removed.
_CHAIN = ("claude", "nova", "openai", "ollama")


def upgrade() -> None:
    for name in _CHAIN:
        op.execute(
            "INSERT INTO ai_provider (uuid, name, enabled) "
            f"VALUES (gen_random_uuid(), '{name}', true) "
            "ON CONFLICT (name) DO NOTHING"
        )
    names = ", ".join(f"'{name}'" for name in _CHAIN)
    op.execute(f"DELETE FROM ai_provider WHERE name NOT IN ({names})")


def downgrade() -> None:
    # Back to the direct-vendor chain: Gemini returns, Nova (which only ever
    # existed as a Bedrock family) goes.
    op.execute(
        "INSERT INTO ai_provider (uuid, name, enabled) "
        "VALUES (gen_random_uuid(), 'gemini', true) "
        "ON CONFLICT (name) DO NOTHING"
    )
    op.execute("DELETE FROM ai_provider WHERE name = 'nova'")
