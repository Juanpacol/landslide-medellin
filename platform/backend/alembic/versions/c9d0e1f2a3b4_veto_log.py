"""veto_log — append-only record of fired Veto rules during inference

Revision ID: c9d0e1f2a3b4
Revises: b1c2d3e4f503
Create Date: 2026-07-30 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, None] = "b1c2d3e4f503"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "veto_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("commune_id", sa.String(length=16), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rule_id", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=128), nullable=False),
        sa.Column("neural_level", sa.String(length=16), nullable=True),
        sa.Column("neural_score", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_veto_log_commune_id", "veto_log", ["commune_id"])
    op.create_index("ix_veto_log_run_at", "veto_log", ["run_at"])
    op.create_index("ix_veto_log_rule_id", "veto_log", ["rule_id"])


def downgrade() -> None:
    op.drop_index("ix_veto_log_rule_id", table_name="veto_log")
    op.drop_index("ix_veto_log_run_at", table_name="veto_log")
    op.drop_index("ix_veto_log_commune_id", table_name="veto_log")
    op.drop_table("veto_log")
