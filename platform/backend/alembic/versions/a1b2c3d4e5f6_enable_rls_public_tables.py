"""enable RLS en tablas públicas — cierra el hueco de exposición vía PostgREST

El backend se conecta siempre con el rol `postgres.<ref>` del connection
pooler de Supabase, que tiene BYPASSRLS, así que activar RLS no afecta el
acceso normal de la app. Lo que sí bloquea es la lectura/escritura directa
de estas tablas vía la API REST autogenerada de Supabase (anon/authenticated
keys), que es la única vía de exposición real: esta app no usa el cliente
Supabase, solo Postgres directo.

No se agregan policies: sin ellas, RLS activado deniega todo a roles que no
tengan BYPASSRLS, que es el comportamiento deseado (nadie debe leer estas
tablas por PostgREST).

Revision ID: a1b2c3d4e5f6
Revises: f8g9c0d1e2f3
Create Date: 2026-07-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f8g9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = [
    "seismic_events",
    "alembic_version",
    "agent_conversations",
    "ml_features",
    "risk_predictions",
    "landslide_events",
    "scraping_logs",
    "rainfall_timeseries",
    "commune_thresholds",
    "alert_log",
    "app_settings",
    "risk_explanations",
    "barrio_hazard",
    "citizen_reports",
    "mesh_quadrants",
    "safe_zones",
    "audit_log",
    "agent_run_logs",
]


def upgrade() -> None:
    for table in TABLES:
        op.execute(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    for table in TABLES:
        op.execute(f'ALTER TABLE public."{table}" DISABLE ROW LEVEL SECURITY')
