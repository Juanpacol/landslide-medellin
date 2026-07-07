"""seismic_events + barrio_hazard + citizen_reports

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-07-04 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "seismic_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source_row_id", sa.String(length=128), nullable=False),
        sa.Column("station_code", sa.String(length=32), nullable=False),
        sa.Column("station_name", sa.Text(), nullable=False),
        sa.Column("event_local_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("magnitude", sa.Float(), nullable=True),
        sa.Column("depth_km", sa.Float(), nullable=True),
        sa.Column("epicenter_lat", sa.Float(), nullable=True),
        sa.Column("epicenter_lon", sa.Float(), nullable=True),
        sa.Column("epicenter_label", sa.Text(), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_seismic_events_source_row_id",
        "seismic_events",
        ["source_row_id"],
        unique=True,
    )

    op.create_table(
        "barrio_hazard",
        sa.Column("barrio_codigo", sa.String(length=32), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("commune_id", sa.String(length=64), nullable=False),
        sa.Column("hazard_grade", sa.String(length=64), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("barrio_codigo"),
    )
    op.create_index("ix_barrio_hazard_commune_id", "barrio_hazard", ["commune_id"])

    op.create_table(
        "citizen_reports",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("commune_id", sa.String(length=64), nullable=False),
        sa.Column("barrio", sa.Text(), nullable=True),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending_review"),
        sa.Column("session_id", sa.String(length=128), nullable=True),
        sa.Column("latitud", sa.Float(), nullable=True),
        sa.Column("longitud", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_citizen_reports_commune_id", "citizen_reports", ["commune_id"])
    op.create_index("ix_citizen_reports_status", "citizen_reports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_citizen_reports_status", table_name="citizen_reports")
    op.drop_index("ix_citizen_reports_commune_id", table_name="citizen_reports")
    op.drop_table("citizen_reports")
    op.drop_index("ix_barrio_hazard_commune_id", table_name="barrio_hazard")
    op.drop_table("barrio_hazard")
    op.drop_index("ix_seismic_events_source_row_id", table_name="seismic_events")
    op.drop_table("seismic_events")
