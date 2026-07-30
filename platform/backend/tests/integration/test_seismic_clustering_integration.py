"""
Integración del clustering sísmico contra Postgres real.

La lógica pura se prueba en `test_seismic_dedup.py`; aquí se verifica lo que solo
se puede ver con base de datos: el upsert idempotente, el `flush` para obtener el
id del clúster, la agregación de `sources`/`source_count`/`member_count` y el
relevo de los valores canónicos por precedencia.

Escenario: un sismo regional visto por 2 estaciones SIATA + USGS + SGC, más un
sismo profundo y lejano, más un sismo local pequeño que solo ve SIATA.

Lo que está en juego, en números: sin agrupar, ese sismo regional aporta
4.0² + 3.9² + 4.2² + 4.4² = 68.2 a la Σ de magnitud² de
`ml/seismic_features.py`. Agrupado aporta 4.4² = 19.4. Un inflado de 3.5× en un
solo sismo, y de forma silenciosa.

Se salta si no hay Postgres local. NO usar contra Supabase: borra las tablas.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from db.models.seismic_event import SeismicEvent
from db.models.seismic_event_cluster import SeismicEventCluster
from db.session import DATABASE_URL
from infrastructure.migrations.ddl_url import is_local_target
from infrastructure.repositories.seismic_events import (
    assign_cluster,
    existing_source_row_ids,
    insert_events,
    recent_clusters,
    unclustered_events,
)

T0 = datetime(2026, 7, 20, 14, 30, tzinfo=timezone.utc)

# Guarda de seguridad: estos tests hacen DELETE, así que solo corren en local.
pytestmark = pytest.mark.skipif(
    not is_local_target(DATABASE_URL),
    reason="requiere Postgres local (docker compose up -d db); no se corre contra Supabase",
)


def _rows() -> list[dict]:
    return [
        # ── Un mismo sismo regional, cuatro reportes ──────────────────────────
        # Tiempos, magnitudes y epicentros distintos: la dedup vieja por
        # (event_local_at, epicenter_label) no habría colapsado ninguno.
        dict(
            source_row_id="EST1_2026-07-20",
            source="siata_sismos",
            station_code="EST1",
            station_name="Estación 1",
            event_local_at=T0 + timedelta(seconds=38),
            magnitude=4.0,
            depth_km=22.0,
            epicenter_lat=6.34,
            epicenter_lon=-75.55,
            epicenter_label="Sismo en Medellín - Antioquia",
        ),
        dict(
            source_row_id="EST2_2026-07-20",
            source="siata_sismos",
            station_code="EST2",
            station_name="Estación 2",
            event_local_at=T0 + timedelta(seconds=41),
            magnitude=3.9,
            depth_km=21.0,
            epicenter_lat=6.34,
            epicenter_lon=-75.55,
            epicenter_label="Sismo en Medellín - Antioquia",
        ),
        # USGS y SGC no tienen estación → prueba que las columnas son nullable y
        # que insert_events normaliza claves heterogéneas.
        dict(
            source_row_id="usgs:us7000zzzz",
            source="usgs",
            event_local_at=T0,
            magnitude=4.2,
            depth_km=20.0,
            epicenter_lat=6.30,
            epicenter_lon=-75.60,
            epicenter_label="12 km NE of Betulia, Colombia",
        ),
        dict(
            source_row_id="sgc:sgc-991",
            source="sgc",
            event_local_at=T0 - timedelta(seconds=3),
            magnitude=4.4,
            depth_km=19.0,
            epicenter_lat=6.28,
            epicenter_lon=-75.63,
            epicenter_label="Betulia, Antioquia",
        ),
        # ── Sismo profundo del Nido de Bucaramanga, ~300 km ───────────────────
        # A solo 90 s del anterior: si la ventana temporal mandara sola, se
        # fusionarían. La distancia lo impide.
        dict(
            source_row_id="usgs:us7000yyyy",
            source="usgs",
            event_local_at=T0 + timedelta(seconds=90),
            magnitude=4.1,
            depth_km=150.0,
            epicenter_lat=7.80,
            epicenter_lon=-73.10,
            epicenter_label="Los Santos, Colombia",
        ),
        # ── Sismo local pequeño que solo ve SIATA ─────────────────────────────
        dict(
            source_row_id="EST1_2026-07-20b",
            source="siata_sismos",
            station_code="EST1",
            station_name="Estación 1",
            event_local_at=T0 + timedelta(minutes=10),
            magnitude=1.9,
            depth_km=5.0,
            epicenter_lat=6.25,
            epicenter_lon=-75.57,
            epicenter_label="Sismo local",
        ),
    ]


async def _reset(session) -> None:
    await session.execute(delete(SeismicEvent))
    await session.execute(delete(SeismicEventCluster))
    await session.commit()


async def _cluster_all(session) -> None:
    for ev in await unclustered_events(session):
        await assign_cluster(session, ev)
    await session.commit()


@pytest.mark.asyncio
async def test_clustering_multifuente(db_session) -> None:
    await _reset(db_session)
    try:
        rows = _rows()
        assert await insert_events(db_session, rows) == 6
        await db_session.commit()

        # Idempotencia del upsert: reinsertar no crea nada.
        assert await insert_events(db_session, rows) == 0

        ya = await existing_source_row_ids(
            db_session, [r["source_row_id"] for r in rows] + ["no-existe"]
        )
        assert len(ya) == 6
        assert "no-existe" not in ya

        await _cluster_all(db_session)

        clusters = (
            (
                await db_session.execute(
                    select(SeismicEventCluster).order_by(SeismicEventCluster.event_at)
                )
            )
            .scalars()
            .all()
        )

        # 6 reportes → 3 sismos físicos.
        assert len(clusters) == 3

        regional, profundo, local = clusters

        # El regional agrupa los 4 reportes de 3 fuentes distintas.
        assert regional.member_count == 4
        assert regional.source_count == 3
        assert set(regional.sources) == {"sgc", "usgs", "siata_sismos"}
        # El canónico es el SGC por precedencia, con SUS valores.
        assert regional.canonical_source == "sgc"
        assert regional.magnitude == pytest.approx(4.4)
        assert regional.epicenter_lat == pytest.approx(6.28)

        # El sismo lejano no se fusionó pese a estar a solo 90 s.
        assert profundo.source_count == 1
        assert profundo.magnitude == pytest.approx(4.1)

        # El sismo local pequeño se conserva: SIATA ve cosas que las redes
        # globales no, y descartarlo sería perder señal real.
        assert local.source_count == 1
        assert local.canonical_source == "siata_sismos"

        # Ningún reporte queda huérfano.
        huerfanos = (
            (
                await db_session.execute(
                    select(SeismicEvent).where(SeismicEvent.cluster_id.is_(None))
                )
            )
            .scalars()
            .all()
        )
        assert huerfanos == []

        # Re-agrupar es un no-op: no aparecen clústeres nuevos.
        await _cluster_all(db_session)
        total = (await db_session.execute(select(SeismicEventCluster))).scalars().all()
        assert len(total) == 3
    finally:
        await _reset(db_session)


@pytest.mark.asyncio
async def test_recent_clusters_filtra_ventana_y_magnitud_nula(db_session) -> None:
    await _reset(db_session)
    try:
        await insert_events(
            db_session,
            [
                # Sin magnitud: no aporta a una Σ de magnitud², así que se excluye.
                dict(
                    source_row_id="usgs:sin-mag",
                    source="usgs",
                    event_local_at=T0,
                    magnitude=None,
                    epicenter_lat=6.3,
                    epicenter_lon=-75.6,
                ),
                dict(
                    source_row_id="usgs:con-mag",
                    source="usgs",
                    event_local_at=T0 + timedelta(hours=2),
                    magnitude=3.3,
                    epicenter_lat=6.9,
                    epicenter_lon=-74.2,
                ),
                # Muy antiguo: fuera de la ventana.
                dict(
                    source_row_id="usgs:viejo",
                    source="usgs",
                    event_local_at=T0 - timedelta(days=120),
                    magnitude=5.0,
                    epicenter_lat=6.3,
                    epicenter_lon=-75.6,
                ),
            ],
        )
        await db_session.commit()
        await _cluster_all(db_session)

        recientes = await recent_clusters(db_session, T0 - timedelta(days=30))
        mags = sorted(c.magnitude for c in recientes)
        assert mags == [pytest.approx(3.3)], f"esperado solo el de M3.3, salió {mags}"
    finally:
        await _reset(db_session)
