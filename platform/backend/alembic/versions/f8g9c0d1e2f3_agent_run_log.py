"""agent_run_log — resultados de ejecución de agentes de monitoreo

Revision ID: f8g9c0d1e2f3
Revises: e6f7a8b9c0d1
Create Date: 2026-07-08 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f8g9c0d1e2f3"
down_revision: Union[str, None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_run_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("agent_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("run_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("run_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_run_logs_agent_name", "agent_run_logs", ["agent_name"])
    op.create_index("ix_agent_run_logs_status", "agent_run_logs", ["status"])
    op.create_index("ix_agent_run_logs_created_at", "agent_run_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_run_logs_created_at", table_name="agent_run_logs")
    op.drop_index("ix_agent_run_logs_status", table_name="agent_run_logs")
    op.drop_index("ix_agent_run_logs_agent_name", table_name="agent_run_logs")
    op.drop_table("agent_run_logs")
