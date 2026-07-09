"""create icon and color catalogs

Revision ID: c3e5a7b9d1f2
Revises: b2d4f6a8c0e1
Create Date: 2026-07-09 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c3e5a7b9d1f2"
down_revision: str | None = "b2d4f6a8c0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (name, file_path) — local SVGs served from /static/icons.
_ICONS = (
    ("Mathematics", "icons/mathematics.svg"),
    ("Biology", "icons/biology.svg"),
    ("Chemistry", "icons/chemistry.svg"),
    ("Physics", "icons/physics.svg"),
    ("History", "icons/history.svg"),
    ("Geography", "icons/geography.svg"),
    ("Literature", "icons/literature.svg"),
    ("Languages", "icons/languages.svg"),
    ("Art", "icons/art.svg"),
    ("Music", "icons/music.svg"),
    ("Physical Education", "icons/physical-education.svg"),
    ("Computer Science", "icons/computer-science.svg"),
    ("Philosophy", "icons/philosophy.svg"),
    ("Sociology", "icons/sociology.svg"),
    ("Geometry", "icons/geometry.svg"),
    ("Astronomy", "icons/astronomy.svg"),
    ("Economics", "icons/economics.svg"),
    ("Law", "icons/law.svg"),
    ("Environmental Science", "icons/environmental-science.svg"),
    ("General Education", "icons/general-education.svg"),
)

# (name, hex_code) — pastel palette.
_COLORS = (
    ("Pastel Pink", "#FFD1DC"),
    ("Pastel Peach", "#FFDAB9"),
    ("Pastel Orange", "#FFCBA4"),
    ("Pastel Yellow", "#FDFD96"),
    ("Pastel Lime", "#CBFFA9"),
    ("Pastel Green", "#B4F8C8"),
    ("Pastel Mint", "#A0E7E5"),
    ("Pastel Teal", "#A2D9CE"),
    ("Pastel Cyan", "#B5EAEA"),
    ("Pastel Sky Blue", "#AEE2FF"),
    ("Pastel Blue", "#A7C7E7"),
    ("Pastel Periwinkle", "#C3B1E1"),
    ("Pastel Lavender", "#E0BBE4"),
    ("Pastel Purple", "#D5AAFF"),
    ("Pastel Violet", "#C9A0DC"),
    ("Pastel Magenta", "#F6A6D3"),
    ("Pastel Rose", "#F8C8DC"),
    ("Pastel Coral", "#FFB7B2"),
    ("Pastel Gray", "#D3D3D3"),
    ("Pastel Beige", "#F5E1C8"),
)


def upgrade() -> None:
    op.create_table(
        "icons",
        sa.Column("uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("file_path", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("uuid", name=op.f("pk_icons")),
    )
    op.create_index(op.f("ix_icons_name"), "icons", ["name"], unique=True)

    op.create_table(
        "colors",
        sa.Column("uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("hex_code", sa.String(length=7), nullable=False),
        sa.PrimaryKeyConstraint("uuid", name=op.f("pk_colors")),
    )
    op.create_index(op.f("ix_colors_name"), "colors", ["name"], unique=True)

    for name, file_path in _ICONS:
        op.execute(
            f"INSERT INTO icons (uuid, name, file_path) "
            f"VALUES (gen_random_uuid(), '{name}', '{file_path}')"
        )
    for name, hex_code in _COLORS:
        op.execute(
            f"INSERT INTO colors (uuid, name, hex_code) "
            f"VALUES (gen_random_uuid(), '{name}', '{hex_code}')"
        )

    op.create_foreign_key(
        op.f("fk_subjects_icon_id_icons"),
        "subjects",
        "icons",
        ["icon_id"],
        ["uuid"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_subjects_color_id_colors"),
        "subjects",
        "colors",
        ["color_id"],
        ["uuid"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_subjects_color_id_colors"), "subjects", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_subjects_icon_id_icons"), "subjects", type_="foreignkey"
    )
    op.drop_index(op.f("ix_colors_name"), table_name="colors")
    op.drop_table("colors")
    op.drop_index(op.f("ix_icons_name"), table_name="icons")
    op.drop_table("icons")
