"""
Ensambla la amenaza por comuna desde la BD: susceptibilidad × disparador.

Sustituye al clasificador supervisado como fuente del `risk_score`. El motivo
está en `domain/susceptibility.py`: TEYVA no tiene etiquetas usables, y los 26
positivos con los que se entrenó el modelo en producción venían de eventos
sintéticos generados por la Snake Line.

Este módulo es el I/O; la fórmula y los pesos son puros y viven en
`domain/susceptibility.py`. Sigue el patrón de sus vecinos (`ml/precip_index.py`,
`ml/soil_water_index.py`, `ml/seismic_features.py`): una función
`*_by_commune(session)` que resuelve las 21 comunas en un solo paso.

**Calcular las 21 de golpe no es una optimización, es el diseño.** Las funciones
subyacentes ya agregan por comuna en una consulta; llamarlas por comuna dentro
del bucle de `run_predictions` multiplicaría por 21 el trabajo de BD. Por eso
`predict_risk` acepta un bundle precalculado.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.ml_feature import MLFeature
from domain.communes import COMMUNES
from domain.risk_rules import ANTECEDENT_INDEX_THRESHOLD_MM
from domain.susceptibility import (
    CALIBRATION_NOTE,
    CALIBRATION_STATUS,
    hazard_score,
    susceptibility_breakdown,
    trigger_breakdown,
)

logger = logging.getLogger(__name__)

# Clave de VM_05 muestreado en el centroide de la comuna, escrita por
# `scraper/medellin_datos.py`.
CENTROID_HAZARD_KEY = "geomorf_riesgo_grado_amenaza"


@dataclass(frozen=True)
class CommuneHazard:
    """Amenaza de una comuna, con todo lo necesario para auditarla."""

    commune_id: str
    score: float | None
    susceptibility: float | None
    trigger: float | None
    susceptibility_components: dict[str, float | None] = field(default_factory=dict)
    susceptibility_weights: dict[str, float] = field(default_factory=dict)
    susceptibility_coverage: float = 0.0
    trigger_components: dict[str, float | None] = field(default_factory=dict)
    # "barrios" (agregado de ~269 polígonos) | "centroide" (un punto) | None.
    hazard_source: str | None = None
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "susceptibility": self.susceptibility,
            "trigger": self.trigger,
            "susceptibility_components": self.susceptibility_components,
            "susceptibility_weights": self.susceptibility_weights,
            "susceptibility_coverage": self.susceptibility_coverage,
            "trigger_components": self.trigger_components,
            "hazard_source": self.hazard_source,
            "calibration": CALIBRATION_STATUS,
            "calibration_note": CALIBRATION_NOTE,
            "reason": self.reason,
        }


async def _centroid_hazard_grades(session: AsyncSession) -> dict[str, str]:
    """Grado VM_05 en el centroide de cada comuna, fila más reciente primero.

    Respaldo para las comunas sin desagregación por barrios: hoy los 5
    corregimientos (ids 17-21), que no aparecen en
    `platform/frontend/lib/barrios-medellin.json` y por tanto no están en
    `barrio_hazard` — precisamente los 5 territorios que son todos ladera.
    """
    stmt = (
        select(MLFeature.commune_id, MLFeature.features)
        .where(MLFeature.features.isnot(None))
        .order_by(MLFeature.reference_date.desc().nulls_last())
    )
    out: dict[str, str] = {}
    for commune_id, features in (await session.execute(stmt)).all():
        cid = str(commune_id)
        if cid in out or not isinstance(features, dict):
            continue
        grade = features.get(CENTROID_HAZARD_KEY)
        if isinstance(grade, str) and grade.strip():
            out[cid] = grade
    return out


async def _safe(label: str, coro: Any, default: Any) -> Any:
    """Ejecuta una fuente de datos sin que su fallo tumbe el resto.

    Mismo criterio que `scraper/siata.py`: una familia de features caída degrada
    el índice, no lo aborta. La degradación queda en `coverage`, así que es dato,
    no solo un log.
    """
    try:
        return await coro
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo calcular %s: %s", label, exc)
        return default


async def hazard_by_commune(
    session: AsyncSession, *, as_of: date | None = None
) -> dict[str, CommuneHazard]:
    """Amenaza de las 21 comunas en un solo paso."""
    from ml.barrio_hazard_features import pct_barrios_alta_amenaza
    from ml.precip_index import antecedent_indexes_for_all_communes
    from ml.seismic_features import seismic_intensity_by_commune
    from ml.soil_water_index import swi_for_all_communes

    hazard_frac: dict[str, float] = await _safe(
        "amenaza por barrios", pct_barrios_alta_amenaza(session), {}
    )
    centroid_grades: dict[str, str] = await _safe(
        "amenaza en centroide", _centroid_hazard_grades(session), {}
    )
    swi: dict[str, float] = await _safe(
        "índice de agua en suelo", swi_for_all_communes(session, as_of), {}
    )
    api: dict[str, float] = await _safe(
        "índice de lluvia antecedente", antecedent_indexes_for_all_communes(session, as_of), {}
    )
    seismic: dict[str, float] = await _safe(
        "intensidad sísmica", seismic_intensity_by_commune(session), {}
    )
    seismic_default = seismic.get("_default")

    out: dict[str, CommuneHazard] = {}
    for commune in COMMUNES:
        cid = commune.id

        # Los barrios agregan ~269 polígonos; el centroide es UN punto y engaña
        # (la comuna 1 sale "Baja" en su centroide con 3 de 12 barrios en Alta).
        # Por eso los barrios tienen prioridad y se registra qué se usó.
        frac = hazard_frac.get(cid)
        if frac is not None:
            hazard_source: str | None = "barrios"
        elif cid in centroid_grades:
            hazard_source = "centroide"
        else:
            hazard_source = None

        susc = susceptibility_breakdown(
            hazard_fraction=frac,
            hazard_grade=centroid_grades.get(cid) if frac is None else None,
            # Pendiente, TWI y NDVI llegan cuando se ingesten SRTM y MODIS
            # (`scraper/terrain_features.py`); `prior_event_count`, con SIMMA.
            # Ausentes, los pesos se renormalizan sobre lo disponible.
        )
        trig = trigger_breakdown(
            soil_water_index_pct=swi.get(cid),
            antecedent_precip_mm=api.get(cid),
            antecedent_reference_mm=ANTECEDENT_INDEX_THRESHOLD_MM,
            seismic_intensity=seismic.get(cid, seismic_default),
        )

        score = hazard_score(susc.index, trig["trigger"])
        reason = None
        if score is None:
            faltan = []
            if susc.index is None:
                faltan.append("susceptibilidad (sin amenaza VM_05)")
            if trig["trigger"] is None:
                faltan.append("disparador (sin lluvia reciente)")
            reason = "sin datos de " + " ni ".join(faltan)

        out[cid] = CommuneHazard(
            commune_id=cid,
            score=score,
            susceptibility=susc.index,
            trigger=trig["trigger"],
            susceptibility_components=susc.components,
            susceptibility_weights=susc.weights_used,
            susceptibility_coverage=susc.coverage,
            trigger_components=trig,
            hazard_source=hazard_source,
            reason=reason,
        )
    return out


async def hazard_for_commune(
    session: AsyncSession, commune_id: str, *, as_of: date | None = None
) -> CommuneHazard:
    """Amenaza de UNA comuna. Calcula las 21 por dentro (las consultas agregan
    por comuna de todos modos); para el lote usar `hazard_by_commune`."""
    everything = await hazard_by_commune(session, as_of=as_of)
    return everything.get(
        str(commune_id),
        CommuneHazard(
            commune_id=str(commune_id),
            score=None,
            susceptibility=None,
            trigger=None,
            reason=f"comuna {commune_id} no está en domain/communes.py",
        ),
    )
