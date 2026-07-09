"""create plan_generation and academic item generation fields

Revision ID: f1a2b3c4d5e6
Revises: a1c2e3f4b5d6
Create Date: 2026-07-07 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "a1c2e3f4b5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    run_status = postgresql.ENUM(
        "PLANNING", "RUNNING", "COMPLETED", "PARTIAL", "FAILED",
        name="generation_run_status",
    )
    run_status.create(op.get_bind(), checkfirst=True)
    item_status = postgresql.ENUM(
        "PENDING", "PROCESSING", "COMPLETED", "FAILED",
        name="generation_item_status",
    )
    item_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "plan_generation",
        sa.Column("uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "PLANNING", "RUNNING", "COMPLETED", "PARTIAL", "FAILED",
                name="generation_run_status", create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("roadmap", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["plans.uuid"],
            name="fk_plan_generation_plan_id_plans", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.uuid"],
            name="fk_plan_generation_user_id_users", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("uuid", name="pk_plan_generation"),
    )
    op.create_index(op.f("ix_plan_generation_plan_id"), "plan_generation", ["plan_id"])
    op.create_index(op.f("ix_plan_generation_user_id"), "plan_generation", ["user_id"])
    op.create_index(op.f("ix_plan_generation_status"), "plan_generation", ["status"])

    op.add_column(
        "academic_items",
        sa.Column("generation_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "academic_items",
        sa.Column(
            "generation_status",
            postgresql.ENUM(
                "PENDING", "PROCESSING", "COMPLETED", "FAILED",
                name="generation_item_status", create_type=False,
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "academic_items", sa.Column("generation_prompt", sa.Text(), nullable=True)
    )
    op.add_column(
        "academic_items", sa.Column("generation_error", sa.Text(), nullable=True)
    )
    op.create_foreign_key(
        "fk_academic_items_generation_id_plan_generation",
        "academic_items", "plan_generation",
        ["generation_id"], ["uuid"], ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_academic_items_generation_id"), "academic_items", ["generation_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_academic_items_generation_id"), table_name="academic_items")
    op.drop_constraint(
        "fk_academic_items_generation_id_plan_generation",
        "academic_items", type_="foreignkey",
    )
    op.drop_column("academic_items", "generation_error")
    op.drop_column("academic_items", "generation_prompt")
    op.drop_column("academic_items", "generation_status")
    op.drop_column("academic_items", "generation_id")

    op.drop_index(op.f("ix_plan_generation_status"), table_name="plan_generation")
    op.drop_index(op.f("ix_plan_generation_user_id"), table_name="plan_generation")
    op.drop_index(op.f("ix_plan_generation_plan_id"), table_name="plan_generation")
    op.drop_table("plan_generation")

    postgresql.ENUM(name="generation_item_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="generation_run_status").drop(op.get_bind(), checkfirst=True)
