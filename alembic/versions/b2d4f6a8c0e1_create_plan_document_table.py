"""create plan_document link table

Revision ID: b2d4f6a8c0e1
Revises: f1a2b3c4d5e6
Create Date: 2026-07-09 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b2d4f6a8c0e1"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plan_document",
        sa.Column("uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["plans.uuid"],
            name="fk_plan_document_plan_id_plans", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["document.uuid"],
            name="fk_plan_document_document_id_document", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("uuid", name="pk_plan_document"),
        sa.UniqueConstraint("plan_id", "document_id", name="uq_plan_document"),
    )
    op.create_index(op.f("ix_plan_document_plan_id"), "plan_document", ["plan_id"])
    op.create_index(
        op.f("ix_plan_document_document_id"), "plan_document", ["document_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_plan_document_document_id"), table_name="plan_document")
    op.drop_index(op.f("ix_plan_document_plan_id"), table_name="plan_document")
    op.drop_table("plan_document")
