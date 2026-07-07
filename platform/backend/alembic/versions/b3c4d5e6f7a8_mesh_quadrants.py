"""mesh_quadrants (JMA mesh maps)

Revision ID: b3c4d5e6f7a8
Revises: a7b8c9d0e1f2
Create Date: 2026-07-04 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mesh_quadrants",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("geometry", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("commune_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("barrio_codigos", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("hazard_grade", sa.String(length=64), nullable=True),
        sa.Column("n_barrios_alta", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("mesh_quadrants")
