"""risk_explanations table

Revision ID: e5f6a7b8c9d0
Revises: c2f3a8d1e9bb
Create Date: 2026-06-28 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "c2f3a8d1e9bb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "risk_explanations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("commune_id", sa.String(64), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("risk_category", sa.String(32), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("generated_by", sa.String(64), nullable=False, server_default="template"),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_risk_explanation_commune_at",
        "risk_explanations",
        ["commune_id", "generated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_risk_explanation_commune_at", table_name="risk_explanations")
    op.drop_table("risk_explanations")
