"""
Blindaje del registro de features y de los centroides.

Estos tests codifican decisiones, no comportamiento incidental. Cada uno
corresponde a un defecto real que ya ocurrió en producción:

- Las 4 features de ingeniería existían en el código y NUNCA entraron al
  modelo, porque la lista de claves vivía en dos sitios que divergieron.
- Las columnas identificadoras (centroid_lat/lon, conteos de filas) sí
  entraron, y con 26 positivos eso convierte el clasificador en una tabla de
  consulta por comuna.
- `_centroids_by_commune` leía los centroides SOLO de `ml_features`, así que en
  una base sin el scraper de 24 h las 21 comunas caían al centro del valle y la
  señal sísmica por comuna se degradaba a una constante, en silencio.
"""

from __future__ import annotations

from domain.communes import CENTROIDS, COMMUNES, VALLEY_CENTROID, centroid
from ml.feature_registry import (
    BY_KEY,
    DENY_KEYS,
    DENY_KEYS_PENDIENTE_LLUVIA,
    DENY_PREFIXES,
    FORCE_KEYS,
    REGISTRY,
    is_denied,
)
from ml.features import _numeric_from_json, row_to_numeric_parts


# ── Registro ──────────────────────────────────────────────────────────────────


def test_no_hay_claves_duplicadas_en_el_registro() -> None:
    keys = [s.key for s in REGISTRY]
    assert len(keys) == len(set(keys)), "clave declarada dos veces"
    assert len(BY_KEY) == len(REGISTRY)


def test_las_4_features_de_ingenieria_estan_forzadas() -> None:
    """Las que existían en el código pero nunca entrenaron."""
    for key in (
        "antecedent_precip_index",
        "soil_water_index_pct",
        "seismic_recent_intensity",
        "pct_barrios_alta_amenaza",
    ):
        assert key in FORCE_KEYS, f"{key} volvería a quedar fuera del modelo"


def test_force_keys_y_deny_keys_son_disjuntos() -> None:
    """Una clave forzada y negada a la vez es una contradicción silenciosa."""
    assert not (FORCE_KEYS & DENY_KEYS)


def test_ninguna_clave_forzada_mira_al_futuro() -> None:
    """Una feature de pronóstico en la matriz de entrenamiento filtra la causa
    física de la etiqueta ("evento en (ref_d, ref_d+7d]")."""
    for key in FORCE_KEYS:
        assert not BY_KEY[key].forward_looking


def test_las_columnas_identificadoras_estan_negadas() -> None:
    for key in ("centroid_lat", "centroid_lon", "precip_records", "station_count"):
        assert is_denied(key), f"{key} volvería a entrar al vector"


def test_prefijos_negados() -> None:
    assert is_denied("meta_seismic_source_ok")
    assert is_denied("fc_rain_sum_3d_mm")
    assert not is_denied("soil_water_index_pct")


def test_las_pendientes_de_lluvia_siguen_en_el_modelo() -> None:
    """`mean_precip_mm_snapshot` y `precip_sum_mm_day` son hoy la ÚNICA señal de
    lluvia. Retirarlas antes de que `precip_daily_mm` esté poblada dejaría al
    modelo sin lluvia, que es peor que el problema que resuelven."""
    assert not (DENY_KEYS_PENDIENTE_LLUVIA & DENY_KEYS)
    for key in DENY_KEYS_PENDIENTE_LLUVIA:
        assert key in FORCE_KEYS
        assert not is_denied(key)


# ── La deny-list se aplica de verdad ──────────────────────────────────────────


def test_numeric_from_json_filtra_las_negadas() -> None:
    raw = {
        "centroid_lat": 6.24,
        "centroid_lon": -75.58,
        "precip_records": 12,
        "station_count": 4,
        "meta_seismic_source_ok": 1,
        "fc_rain_sum_3d_mm": 41.0,
        "soil_water_index_pct": 61.2,
        "source": "siata",
    }
    out = _numeric_from_json(raw)
    assert out == {"soil_water_index_pct": 61.2}


def test_row_to_numeric_parts_no_emite_columnas_negadas() -> None:
    class _Row:
        features = {"soil_water_index_pct": 61.2}
        precip_acum_7d = 88.0  # negada: sería antecedent_precip_index con decay=1
        n_events_window = 3  # negada

    parts = row_to_numeric_parts(_Row())  # type: ignore[arg-type]
    assert "precip_acum_7d" not in parts
    assert "n_events_window" not in parts
    assert parts["soil_water_index_pct"] == 61.2


def test_prefijos_declarados_como_tupla_de_str() -> None:
    """`str.startswith` acepta una tupla; un str suelto haría match por letra."""
    assert isinstance(DENY_PREFIXES, tuple)
    assert all(isinstance(p, str) for p in DENY_PREFIXES)


# ── Centroides ────────────────────────────────────────────────────────────────


def test_las_21_comunas_tienen_centroide() -> None:
    faltan = [c.id for c in COMMUNES if c.id not in CENTROIDS]
    assert not faltan, f"sin centroide: {faltan} → caerían al centro del valle"


def test_ninguna_comuna_usa_el_centro_del_valle() -> None:
    """Si una comuna real cae al fallback, su señal sísmica es una constante."""
    for cid, coords in CENTROIDS.items():
        assert coords != VALLEY_CENTROID, f"comuna {cid} usa el fallback"


def test_centroides_dentro_del_area_de_medellin() -> None:
    """Caja de seguridad: detecta lat/lon invertidos o un signo perdido."""
    for cid, (lat, lon) in CENTROIDS.items():
        assert 6.10 <= lat <= 6.40, f"comuna {cid}: lat {lat} fuera de rango"
        assert -75.75 <= lon <= -75.45, f"comuna {cid}: lon {lon} fuera de rango"


def test_centroides_distintos_entre_si() -> None:
    assert len(set(CENTROIDS.values())) == len(CENTROIDS)


def test_centroid_acepta_codigo_oficial() -> None:
    """El borde con ArcGIS habla en código oficial ("60" = San Cristóbal = id 18)."""
    assert centroid("60") == CENTROIDS["18"]
    assert centroid("18") == CENTROIDS["18"]
    assert centroid(None) is None


def test_geografia_reconocible() -> None:
    """El Poblado (14) está al sur de Popular (1); Palmitas (17) al occidente
    de Santa Elena (21). Detecta un copiar-pegar de coordenadas."""
    assert CENTROIDS["14"][0] < CENTROIDS["1"][0]
    assert CENTROIDS["17"][1] < CENTROIDS["21"][1]


# ── Coherencia entre el ON CONFLICT y el índice único ─────────────────────────


def test_el_upsert_de_lluvia_incluye_source_en_el_conflicto() -> None:
    """El índice único de `rainfall_timeseries` es
    (commune_id, snapshot_at, source) desde la migración b1c2d3e4f501.

    Si el `on_conflict_do_nothing` de `scraper/siata.py` no nombra las TRES
    columnas, Postgres no encuentra un índice que case y aborta con
    `InvalidColumnReferenceError`, tumbando la ingesta de lluvia entera. Pasó en
    producción el 2026-07-29: la migración amplió el índice y el llamador se
    quedó con dos columnas.
    """
    import ast
    import inspect
    import textwrap

    import scraper.siata as siata
    from db.models.rainfall_timeseries import RainfallTimeseries

    # El modelo declara el índice de 3 columnas...
    idx = {i.name: [c.name for c in i.columns] for i in RainfallTimeseries.__table__.indexes}
    columnas = idx["ix_rainfall_ts_commune_snap_src"]
    assert columnas == ["commune_id", "snapshot_at", "source"]

    # ...y el ON CONFLICT del scraper nombra EXACTAMENTE esas tres. Se parsea el
    # AST en vez de buscar en el texto: una comprobación por substring pasaría
    # con cualquier mención suelta de "source" y no protegería nada.
    tree = ast.parse(textwrap.dedent(inspect.getsource(siata._run_siata)))
    encontrados: list[list[str]] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "on_conflict_do_nothing":
            continue
        for kw in node.keywords:
            if kw.arg == "index_elements" and isinstance(kw.value, ast.List):
                encontrados.append([e.value for e in kw.value.elts if isinstance(e, ast.Constant)])

    assert encontrados, "no se encontró ningún on_conflict_do_nothing en _run_siata"
    for elems in encontrados:
        assert elems == columnas, (
            f"el ON CONFLICT usa {elems} pero el índice único es {columnas}: "
            "Postgres abortaría con InvalidColumnReferenceError"
        )


def test_siata_usa_una_sola_constante_de_fuente() -> None:
    """`"siata"` estaba repetido en cuatro sitios (log, JSONB, ml_feature_exists
    y el upsert). Si divergen, el ON CONFLICT deja de casar con el índice."""
    import inspect

    import scraper.siata as siata

    assert siata.SOURCE_KEY == "siata"
    code = inspect.getsource(siata)
    cuerpo = code.split("SOURCE_KEY = ", 1)[1].split("\n", 1)[1]
    assert '"siata"' not in cuerpo, "queda un literal 'siata' fuera de SOURCE_KEY"
