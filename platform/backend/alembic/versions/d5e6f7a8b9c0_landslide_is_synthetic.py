"""landslide_events.is_synthetic — separar señal sintética de la real

Los eventos generados por scraper/ingest_synthetic_events.py (Snake Line
retro-aplicado sobre lluvia histórica) sirven para calibrar Snake Line, pero
NO deben entrar al training set del clasificador ML: fueron creados con la
misma heurística que luego se usa para validar (contaminación circular).

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-07-07 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "landslide_events",
        sa.Column("is_synthetic", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Backfill: los sintéticos ya insertados se identifican por su source_row_id.
    op.execute(
        "UPDATE landslide_events SET is_synthetic = true WHERE source_row_id LIKE 'synthetic:%'"
    )


def downgrade() -> None:
    op.drop_column("landslide_events", "is_synthetic")
