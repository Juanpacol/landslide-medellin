"""sismos multi-fuente: seismic_events.source + cluster_id + seismic_event_clusters

Prepara la entrada de USGS y del SGC junto a SIATA. La deduplicación NO es
pulido opcional: es un prerrequisito.

**El bug que esto evita.** `ml/seismic_features.py` deduplica hoy por
`(event_local_at.isoformat(), epicenter_label)`. Eso funciona solo porque todas
las filas de estaciones SIATA de un mismo sismo comparten tiempo y etiqueta
calculados idénticos. En cuanto lleguen USGS y SGC eso se rompe: los tiempos de
origen difieren en segundos y las etiquetas son textos distintos
("12 km NE of Betulia, Colombia" vs el municipio del SGC vs "Sismo en Medellín -
Antioquia"). NINGÚN duplicado entre fuentes colapsaría. Y como la feature es una
**Σ de magnitud²**, cada sismo contaría 2-3 veces y la señal se infla de forma
cuadrática, en silencio.

**Por qué una tabla de clústeres y no una FK a sí misma.** Se evaluaron tres
opciones:
- Clave calculada (bucket de tiempo + geohash): gratis, pero los límites de
  bucket separan eventos a 10 s de distancia y no puede expresar una tolerancia
  transitiva (SIATA↔USGS 18 km, USGS↔SGC 20 km, SIATA↔SGC 35 km).
- `canonical_event_id` como FK a sí misma: DDL mínima, pero la magnitud del
  clúster sería la de una agencia (no un consenso trazable), un cambio de
  precedencia tardío obliga a re-apuntar todas las filas miembro, y "¿cuántas
  fuentes lo confirman?" pasa a ser un GROUP BY en cada lectura.
- **Tabla `seismic_event_clusters` (elegida):** es la superficie que consume el
  ML, así que la heurística desaparece del código de features; un cambio de
  precedencia es un UPDATE de una fila; y `sources`/`source_count` son columnas,
  con lo que "confirmado por 3 agencias" sale gratis y sirve para matizar la
  confianza de una alerta.

Las filas crudas de `seismic_events` **nunca se borran ni se mutan**: los
números de cada agencia quedan auditables.

**No hay backfill de datos aquí.** Las migraciones corren en CI contra
producción y no deben hacer trabajo de clustering de miles de filas; eso lo hace
`scraper/seismic_cluster_backfill.py`, a mano, y DEBE correr antes de que
`ml/seismic_features.py` pase a leer clústeres — si no, desaparecen 30 días de
historia sísmica de la feature.

Revision ID: b1c2d3e4f502
Revises: b1c2d3e4f501
Create Date: 2026-07-29 16:15:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f502"
down_revision: Union[str, None] = "b1c2d3e4f501"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "seismic_event_clusters",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        # Tiempo de origen de consenso: el de la fuente que gana por precedencia.
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=False),
        # Magnitud de consenso = la del ganador de precedencia, NO el máximo ni
        # la media. El máximo sesga al alza y la feature eleva al cuadrado, así
        # que el sesgo se amplifica; la media mezcla escalas incompatibles
        # (ML vs Mw vs Mb, que difieren 0.3-0.7 de rutina).
        sa.Column("magnitude", sa.Float(), nullable=True),
        # Escala de la magnitud. Imprescindible, no decorativo: el SGC publica
        # `MLr`/`MLr_1..4`/`MLr_vmm` (ML regional con calibración por región) y
        # USGS publica `mb` para los eventos colombianos. NO son comparables, y
        # guardar la magnitud sin su escala invita a promediarlas.
        sa.Column("mag_type", sa.String(length=16), nullable=True),
        sa.Column("depth_km", sa.Float(), nullable=True),
        sa.Column("epicenter_lat", sa.Float(), nullable=True),
        sa.Column("epicenter_lon", sa.Float(), nullable=True),
        sa.Column("epicenter_label", sa.Text(), nullable=True),
        sa.Column("canonical_source", sa.String(length=32), nullable=False),
        # Fuentes distintas que reportaron este sismo: ["siata_sismos","usgs"].
        sa.Column(
            "sources",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="1"),
        # member_count incluye las K filas de estación de SIATA; source_count no.
        sa.Column("member_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # La búsqueda de candidatos es por ventana de ±120 s sobre event_at.
    op.create_index("ix_seismic_clusters_event_at", "seismic_event_clusters", ["event_at"])

    # ── seismic_events: source + cluster_id ───────────────────────────────────
    op.add_column(
        "seismic_events",
        sa.Column(
            "source", sa.String(length=32), nullable=False, server_default="siata_sismos"
        ),
    )
    op.create_index("ix_seismic_events_source", "seismic_events", ["source"])

    # Escala de magnitud del reporte crudo (ver comentario en el clúster).
    op.add_column("seismic_events", sa.Column("mag_type", sa.String(length=16), nullable=True))

    op.add_column("seismic_events", sa.Column("cluster_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_seismic_events_cluster",
        "seismic_events",
        "seismic_event_clusters",
        ["cluster_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_seismic_events_cluster_id", "seismic_events", ["cluster_id"])

    # station_code / station_name pasan a NULLABLE: son NOT NULL desde
    # a7b8c9d0e1f2 porque SIATA es una red de estaciones, pero un evento de USGS
    # o del SGC es una solución de agencia y no tiene estación. Sin esto, el
    # primer INSERT de USGS falla con NotNullViolation.
    op.alter_column("seismic_events", "station_code", existing_type=sa.String(32), nullable=True)
    op.alter_column("seismic_events", "station_name", existing_type=sa.Text(), nullable=True)

    op.execute('ALTER TABLE public."seismic_event_clusters" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    op.execute('ALTER TABLE public."seismic_event_clusters" DISABLE ROW LEVEL SECURITY')

    # Volver a NOT NULL falla si ya entraron eventos sin estación (USGS/SGC).
    # Se rellenan con un centinela en vez de borrarlos: el dato sísmico crudo es
    # auditable y perderlo es peor que un '-' explícito.
    op.execute("UPDATE seismic_events SET station_code = '-' WHERE station_code IS NULL")
    op.execute("UPDATE seismic_events SET station_name = '-' WHERE station_name IS NULL")
    op.alter_column("seismic_events", "station_name", existing_type=sa.Text(), nullable=False)
    op.alter_column("seismic_events", "station_code", existing_type=sa.String(32), nullable=False)

    op.drop_index("ix_seismic_events_cluster_id", table_name="seismic_events")
    op.drop_constraint("fk_seismic_events_cluster", "seismic_events", type_="foreignkey")
    op.drop_column("seismic_events", "cluster_id")

    op.drop_column("seismic_events", "mag_type")
    op.drop_index("ix_seismic_events_source", table_name="seismic_events")
    op.drop_column("seismic_events", "source")

    op.drop_index("ix_seismic_clusters_event_at", table_name="seismic_event_clusters")
    op.drop_table("seismic_event_clusters")
