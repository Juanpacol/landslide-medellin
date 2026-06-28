"""rain_monitor_tables

Revision ID: c2f3a8d1e9bb
Revises: b791d657baae
Create Date: 2026-06-27 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c2f3a8d1e9bb"
down_revision: Union[str, None] = "b791d657baae"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rainfall_timeseries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("commune_id", sa.String(length=64), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("precip_mm", sa.Float(), nullable=False),
        sa.Column("station_count", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_rainfall_ts_commune_snap",
        "rainfall_timeseries",
        ["commune_id", "snapshot_at"],
        unique=True,
    )
    op.create_table(
        "commune_thresholds",
        sa.Column("commune_id", sa.String(length=64), nullable=False),
        sa.Column("threshold_mm", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("commune_id"),
    )
    op.create_table(
        "alert_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("commune_id", sa.String(length=64), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("precip_acum_mm", sa.Float(), nullable=True),
        sa.Column("threshold_mm", sa.Float(), nullable=True),
        sa.Column("risk_score", sa.Float(), nullable=True),
        sa.Column("risk_category", sa.String(length=32), nullable=True),
        sa.Column("webhook_url", sa.String(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("response_code", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_log_commune_id", "alert_log", ["commune_id"])
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_index("ix_alert_log_commune_id", table_name="alert_log")
    op.drop_table("alert_log")
    op.drop_table("commune_thresholds")
    op.drop_index("ix_rainfall_ts_commune_snap", table_name="rainfall_timeseries")
    op.drop_table("rainfall_timeseries")
