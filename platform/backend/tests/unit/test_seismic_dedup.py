"""
Tests de la deduplicación canónica de sismos.

Lo que está en juego: `ml/seismic_features.py` calcula una Σ de magnitud². Si el
mismo sismo cuenta 2-3 veces (una por agencia), la feature se infla de forma
CUADRÁTICA y en silencio. Estos tests son la única cosa que impide que eso
vuelva a pasar cuando alguien retoque una tolerancia.

Los casos usan coordenadas y magnitudes realistas de sismos que afectan al Valle
de Aburrá, no valores de juguete.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from domain.seismic_dedup import (
    MATCH_DISTANCE_KM,
    MATCH_TIME_WINDOW_S,
    SOURCE_PRECEDENCE,
    EventKey,
    best_match,
    events_match,
    km_apart,
    merge_sources,
    pick_canonical,
    source_rank,
)

T0 = datetime(2026, 7, 20, 14, 30, 0, tzinfo=timezone.utc)


def ev(
    *,
    source: str = "usgs",
    offset_s: float = 0.0,
    mag: float | None = 4.2,
    lat: float | None = 6.30,
    lon: float | None = -75.60,
    depth: float | None = 20.0,
) -> EventKey:
    return EventKey(
        event_at=T0 + timedelta(seconds=offset_s),
        source=source,
        magnitude=mag,
        depth_km=depth,
        lat=lat,
        lon=lon,
    )


# ── El caso que motiva todo: un sismo, tres agencias ──────────────────────────


def test_un_sismo_reportado_por_tres_fuentes_colapsa() -> None:
    """SIATA, USGS y SGC ven el mismo sismo con tiempos, magnitudes y epicentros
    ligeramente distintos. Deben agruparse en UNO."""
    siata = ev(source="siata_sismos", offset_s=38, mag=4.0, lat=6.34, lon=-75.55)
    usgs = ev(source="usgs", offset_s=0, mag=4.2, lat=6.30, lon=-75.60)
    sgc = ev(source="sgc", offset_s=-3, mag=4.4, lat=6.28, lon=-75.63)

    assert events_match(usgs, siata)
    assert events_match(usgs, sgc)
    assert events_match(siata, sgc)


def test_la_dedup_anterior_habria_fallado_con_estos_datos() -> None:
    """Documenta POR QUÉ hacía falta esto: la clave vieja era
    (event_local_at.isoformat(), epicenter_label), y aquí difieren ambas."""
    usgs = EventKey(
        event_at=T0,
        source="usgs",
        magnitude=4.2,
        lat=6.30,
        lon=-75.60,
        label="12 km NE of Betulia, Colombia",
    )
    siata = EventKey(
        event_at=T0 + timedelta(seconds=38),
        source="siata_sismos",
        magnitude=4.0,
        lat=6.34,
        lon=-75.55,
        label="Sismo en Medellín - Antioquia",
    )
    clave_vieja_usgs = (usgs.event_at.isoformat(), usgs.label)
    clave_vieja_siata = (siata.event_at.isoformat(), siata.label)
    assert clave_vieja_usgs != clave_vieja_siata  # no colapsaba
    assert events_match(usgs, siata)  # ahora sí


# ── Lo que NO debe fusionarse ─────────────────────────────────────────────────


def test_dos_sismos_distintos_a_90s_en_regiones_distintas_no_colapsan() -> None:
    a = ev(offset_s=0, lat=6.30, lon=-75.60)
    b = ev(offset_s=90, lat=7.80, lon=-73.10)  # Nido de Bucaramanga, ~300 km
    assert not events_match(a, b)


def test_magnitudes_incompatibles_descartan() -> None:
    """Un M2.0 y un M5.5 no son el mismo sismo aunque coincidan en tiempo y sitio."""
    assert not events_match(ev(mag=2.0), ev(mag=5.5, offset_s=1))


def test_fuera_de_la_ventana_temporal_no_colapsa() -> None:
    assert not events_match(ev(offset_s=0), ev(offset_s=MATCH_TIME_WINDOW_S + 1))


def test_fuera_del_radio_no_colapsa() -> None:
    # ~1.5 grados de latitud ≈ 167 km, muy por encima de los 60 km.
    assert not events_match(ev(lat=6.30), ev(lat=7.80, offset_s=1))


# ── Coordenadas ausentes ──────────────────────────────────────────────────────


def test_sin_coordenadas_se_aprieta_la_ventana_temporal() -> None:
    sin = ev(lat=None, lon=None)
    assert events_match(sin, ev(offset_s=30))  # dentro de 45 s
    assert not events_match(sin, ev(offset_s=60))  # fuera de 45 s, aunque <120 s


def test_km_apart_devuelve_none_sin_coordenadas() -> None:
    assert km_apart(ev(lat=None), ev()) is None
    assert km_apart(ev(), ev()) == pytest.approx(0.0, abs=1e-6)


# ── El footgun de haversine ───────────────────────────────────────────────────


def test_la_distancia_usa_lat_lon_en_el_orden_correcto() -> None:
    """`haversine_km` es lon-primero; invertirlo da un número plausible pero mal.
    Este test detecta esa inversión: comuna 1 → comuna 14 son ~10.6 km."""
    a = ev(lat=6.291857, lon=-75.542108, offset_s=0)
    b = ev(lat=6.197583, lon=-75.554248, offset_s=0)
    d = km_apart(a, b)
    assert d is not None
    assert 10.0 < d < 11.5, f"distancia {d} km — ¿lat/lon invertidos?"


# ── Precedencia ───────────────────────────────────────────────────────────────


def test_orden_de_precedencia() -> None:
    assert source_rank("sgc") < source_rank("usgs") < source_rank("siata_sismos")


def test_fuente_desconocida_va_al_final() -> None:
    assert source_rank("otra") == len(SOURCE_PRECEDENCE)
    assert source_rank(None) == len(SOURCE_PRECEDENCE)
    assert source_rank("otra") > source_rank("siata_sismos")


def test_el_sgc_gana_los_valores_canonicos() -> None:
    siata = ev(source="siata_sismos", mag=4.0)
    sgc = ev(source="sgc", mag=4.4)
    assert pick_canonical(siata, sgc).source == "sgc"
    # y no al revés: una fuente peor no desplaza a una mejor
    assert pick_canonical(sgc, siata).source == "sgc"


def test_a_igualdad_de_fuente_se_conserva_el_actual() -> None:
    """Reprocesar no debe cambiar el canónico sin motivo (idempotencia)."""
    primera = ev(source="usgs", mag=4.2)
    segunda = ev(source="usgs", mag=4.3, offset_s=2)
    assert pick_canonical(primera, segunda) is primera


def test_la_magnitud_canonica_no_es_el_maximo() -> None:
    """El máximo sesgaría al alza, y la feature eleva al cuadrado."""
    siata = ev(source="siata_sismos", mag=4.9)
    sgc = ev(source="sgc", mag=4.1)
    assert pick_canonical(siata, sgc).magnitude == 4.1  # gana el SGC, no el mayor


# ── Agrupamiento ──────────────────────────────────────────────────────────────


def test_best_match_elige_el_mas_cercano_en_tiempo() -> None:
    clusters = [ev(offset_s=100), ev(offset_s=10), ev(offset_s=-95)]
    assert best_match(ev(offset_s=0), clusters) == 1


def test_best_match_sin_candidatos() -> None:
    assert best_match(ev(offset_s=0), []) is None
    assert best_match(ev(offset_s=0), [ev(offset_s=9999)]) is None


def test_best_match_es_determinista_ante_empate() -> None:
    """Mismo delta temporal en dos clústeres → gana el índice más bajo."""
    clusters = [ev(offset_s=30), ev(offset_s=-30)]
    assert best_match(ev(offset_s=0), clusters) == 0


def test_agrupar_no_depende_del_orden_de_llegada() -> None:
    a = ev(source="siata_sismos", offset_s=38, mag=4.0, lat=6.34, lon=-75.55)
    b = ev(source="usgs", offset_s=0, mag=4.2, lat=6.30, lon=-75.60)
    c = ev(source="sgc", offset_s=-3, mag=4.4, lat=6.28, lon=-75.63)
    for orden in ([a, b, c], [c, b, a], [b, a, c]):
        clusters: list[EventKey] = []
        for e in orden:
            i = best_match(e, clusters)
            if i is None:
                clusters.append(e)
            else:
                clusters[i] = pick_canonical(clusters[i], e)
        assert len(clusters) == 1, f"orden {[x.source for x in orden]} → {len(clusters)} clústeres"
        assert clusters[0].source == "sgc"  # y el canónico siempre es el mismo


def test_un_sismo_local_solo_de_siata_forma_su_propio_cluster() -> None:
    """SIATA detecta sismos pequeños que USGS y SGC no ven. Deben conservarse
    como clúster de una sola fuente, no descartarse."""
    regional = ev(source="usgs", mag=4.2, offset_s=0)
    local = ev(source="siata_sismos", mag=1.9, offset_s=600, lat=6.25, lon=-75.57)
    assert best_match(local, [regional]) is None


# ── merge_sources ─────────────────────────────────────────────────────────────


def test_merge_sources_sin_duplicados_y_ordenado() -> None:
    assert merge_sources(["siata_sismos"], "usgs") == ["usgs", "siata_sismos"]
    assert merge_sources(["usgs", "siata_sismos"], "sgc") == ["sgc", "usgs", "siata_sismos"]


def test_merge_sources_es_idempotente() -> None:
    assert merge_sources(["usgs"], "usgs") == ["usgs"]


# ── Coherencia de las constantes ──────────────────────────────────────────────


def test_las_tolerancias_son_positivas_y_razonables() -> None:
    assert 0 < MATCH_TIME_WINDOW_S <= 600
    assert 0 < MATCH_DISTANCE_KM <= 200


def test_dominio_no_importa_infraestructura() -> None:
    """`domain/` no puede importar nada con I/O (regla de capas de CLAUDE.md).
    Si esto falla, alguien metió httpx o la BD en la capa de dominio."""
    import domain.seismic_dedup as mod

    src = mod.__doc__ or ""
    assert src  # el módulo documenta su contrato
    import inspect

    code = inspect.getsource(mod)
    for prohibido in ("httpx", "sqlalchemy", "db.models", "infrastructure."):
        assert prohibido not in code, f"domain/seismic_dedup.py importa {prohibido}"
