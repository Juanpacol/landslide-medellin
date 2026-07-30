"""True polygon-based commune adjacency via shapely, over the barrio polygon file
(`platform/frontend/lib/barrios-medellin.json`) — the real spatial adjacency
specs/005-knowledge-graph/spec.md calls for, replacing `kg/build.py`'s centroid-proximity
approximation wherever this file has coverage.

No DB, no network: the barrio GeoJSON is a static file already checked into the repo (the same
one `scraper/barrio_hazard.py` and `scraper/mesh_grid.py` read), so this module builds and tests
without any external dependency beyond `shapely` (already a project dependency).

## Method

Two communes are adjacent if any of their barrios' polygons touch or overlap (shapely's
`intersects`, which is true for shared boundaries as well as overlaps — landslide risk on a
shared ridge doesn't care which side of a surveyed line it's on). A commune's combined shape is
the union of its barrios' polygons; comparing unions rather than every barrio-pair is what keeps
this O(n²) over 16 communes instead of over ~400 barrios.

## Honest coverage limit

`barrios-medellin.json` covers only the 16 urban comunas — the 5 corregimientos (Palmitas, San
Cristóbal, Altavista, San Antonio de Prado, Santa Elena) have no barrio-level polygon data in
this file. `polygon_adjacency()` returns adjacency only for the communes it has coverage for;
`kg/build.py::build_static_graph()` is responsible for falling back to centroid-proximity for
the corregimientos, not this module silently guessing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_GEOJSON = Path(__file__).resolve().parents[2] / "frontend" / "lib" / "barrios-medellin.json"


def _load_features(geojson_path: Path) -> list[dict[str, Any]]:
    data = json.loads(geojson_path.read_text(encoding="utf-8"))
    return data.get("features") or []


def commune_union_shapes(geojson_path: Path = DEFAULT_GEOJSON) -> dict[str, Any]:
    """One shapely geometry per commune — the union of all its barrios' polygons.

    Returns {commune_id: shapely geometry}. Only communes present in the GeoJSON appear
    (the 16 urban comunas, not the 5 corregimientos — see module docstring).
    """
    from shapely.geometry import shape
    from shapely.ops import unary_union

    by_commune: dict[str, list[Any]] = {}
    for feat in _load_features(geojson_path):
        props = feat.get("properties") or {}
        commune_id = str(props.get("comuna") or "").strip()
        geom_raw = feat.get("geometry")
        if not commune_id or not geom_raw or not commune_id.isdigit():
            continue
        try:
            geom = shape(geom_raw)
            if not geom.is_valid:
                # Real data has self-intersecting rings (observed against the actual
                # barrios-medellin.json: a GEOSException "side location conflict" on
                # unary_union without this repair). buffer(0) is shapely's standard fix
                # for minor topology errors — it doesn't change valid geometry.
                geom = geom.buffer(0)
        except Exception:  # noqa: BLE001
            continue
        if geom.is_empty:
            continue
        by_commune.setdefault(commune_id, []).append(geom)

    return {cid: unary_union(geoms) for cid, geoms in by_commune.items()}


def polygon_adjacency(geojson_path: Path = DEFAULT_GEOJSON) -> dict[str, frozenset[str]]:
    """{commune_id: frozenset of adjacent commune_ids}, true polygon adjacency.

    Only covers the communes with barrio data (see module docstring) — a commune missing
    from the result has no polygon data to determine adjacency from, not "no neighbors".
    """
    shapes = commune_union_shapes(geojson_path)
    ids = sorted(shapes.keys())

    adjacency: dict[str, set[str]] = {cid: set() for cid in ids}
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            if shapes[a].intersects(shapes[b]):
                adjacency[a].add(b)
                adjacency[b].add(a)

    return {cid: frozenset(neighbors) for cid, neighbors in adjacency.items()}
