"""Agente: valida integridad de datos tras cada ingesta de scraper.

Corre automáticamente después de `scraper/siata.py`, `scraper/dagrd.py`, etc.

## Por qué se endureció (2026-07-29)

La versión anterior solo comprobaba rango [0, 500] mm, timestamps futuros y
cobertura por comuna. Dejó pasar en verde **tres** problemas de datos graves:

1. **Lluvia congelada.** `max(precip_mm)` era 0.003 en las 8.721 filas de la
   tabla, y todos los valores no-cero eran exactamente ese. En una comuna, el
   mismo 0.003 se repitió 41 snapshots seguidos, de 00:26 a 20:58. 0.003 está
   dentro de [0, 500], así que pasaba. Consecuencia: `alert_log` llevaba 30 días
   vacío porque el umbral de 35 mm es inalcanzable — el sistema de alertas por
   lluvia nunca se disparó.
2. **Lluvia histórica absurda.** `ml_features.precip_sum_mm_day` llegaba a 92.202
   mm/día (el récord mundial son ~1.825). Esa tabla no se validaba en absoluto.
3. **Sismos parados.** El feed no producía eventos nuevos desde el 1 de marzo y
   el scraper reportaba `ok` en 93 corridas seguidas, porque `records_valid=0`
   significa "sin eventos nuevos" y es indistinguible de "el parser se rompió".

El patrón común: **un dato dentro de rango puede seguir siendo imposible.** Las
comprobaciones nuevas son de PLAUSIBILIDAD, no solo de rango.

Resultado → `agent_run_logs` siempre. Slack SOLO si hay hallazgos: en `ok` se usa
`log_agent_run`, nunca `fire_agent_alert` (regla anti-ruido de CLAUDE.md — este
agente corre tras cada scraper, ~380 veces por semana, y postear "OK" cada vez
ahogaría las alertas reales). Nunca bloquea la corrida del scraper.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.ml_feature import MLFeature
from db.models.rainfall_timeseries import RainfallTimeseries
from db.models.seismic_event import SeismicEvent
from db.session import AsyncSessionLocal
from domain.communes import COMMUNES
from domain.quality import (
    MAX_PLAUSIBLE_DAILY_MM,
    MIN_PLAUSIBLE_MAX_MM,  # noqa: F401 -- re-exported; see test_scraper_validator_quality_wiring.py
    MIN_ROWS_FOR_DISTINCT_CHECK,
    SEISMIC_STALE_DAYS,
    is_frozen_signal,
    is_implausibly_high_daily,
    is_implausibly_low_max,
    is_stale,
)
from monitoring.notify import fire_agent_alert, log_agent_run

logger = logging.getLogger(__name__)

# Umbrales de validación (mover a constants.py si empiezan a variar)
MIN_PRECIP_MM = 0.0
MAX_PRECIP_MM = 500.0
MIN_SEISMIC_MAG = 0.0
MAX_SEISMIC_MAG = 10.0

# ── Plausibilidad de la lluvia ────────────────────────────────────────────────
# Ventana larga a propósito: Medellín tiene temporadas secas (dic-feb, jul-ago),
# así que un día sin lluvia es normal y no debe alertar. Dos semanas en las que
# NINGUNA de las 21 comunas registra una lectura por encima de 1 mm no lo es: la
# ciudad promedia ~4-5 mm/día. Es una cota deliberadamente baja para que solo
# salte ante un fallo de campo o de unidad, no ante un periodo seco.
#
# MIN_PLAUSIBLE_MAX_MM, MIN_ROWS_FOR_DISTINCT_CHECK, MAX_PLAUSIBLE_DAILY_MM y
# SEISMIC_STALE_DAYS vienen de domain/quality.py — antes estaban duplicados aquí
# (mismos valores, dos sitios), lo que exactamente `domain/quality.py`'s
# docstring advierte que puede divergir sin que nadie lo note.
PLAUSIBILITY_WINDOW_DAYS = 14

DAILY_RAIN_KEYS = ("precip_daily_mm", "precip_sum_mm_day")


async def validate_rainfall_data(session: AsyncSession) -> tuple[str, dict]:
    """Rango, timestamps y PLAUSIBILIDAD de la lluvia observada."""
    stmt = select(RainfallTimeseries).order_by(RainfallTimeseries.snapshot_at.desc()).limit(1000)
    rows = (await session.scalars(stmt)).all()

    now = datetime.now(timezone.utc)
    out_of_range = 0
    future_timestamps = 0
    for row in rows:
        if not (MIN_PRECIP_MM <= row.precip_mm <= MAX_PRECIP_MM):
            out_of_range += 1
            logger.warning(
                "Rainfall out of range: %.1fmm commune=%s at %s",
                row.precip_mm,
                row.commune_id,
                row.snapshot_at,
            )
        if row.snapshot_at and row.snapshot_at > now:
            future_timestamps += 1

    checks: dict = {
        "total_checked": len(rows),
        "out_of_range": out_of_range,
        "future_timestamps": future_timestamps,
        "range": f"{MIN_PRECIP_MM}-{MAX_PRECIP_MM}mm",
    }
    problems: list[str] = []
    if out_of_range:
        problems.append(f"{out_of_range} lecturas fuera de rango")
    if future_timestamps:
        problems.append(f"{future_timestamps} timestamps futuros")

    # ── Constante congelada ───────────────────────────────────────────────────
    # Un feed sano varía. Si en cientos de lecturas hay 2 o menos valores
    # distintos, no es meteorología: es un campo que no cambia.
    values = {round(r.precip_mm, 6) for r in rows}
    checks["distinct_values"] = len(values)
    if is_frozen_signal([r.precip_mm for r in rows], min_rows=MIN_ROWS_FOR_DISTINCT_CHECK):
        problems.append(
            f"solo {len(values)} valor(es) distinto(s) en {len(rows)} lecturas "
            f"({sorted(values)}): el campo parece congelado, no una medición"
        )

    # ── Máximo implausiblemente bajo en una ventana larga ─────────────────────
    cutoff = now - timedelta(days=PLAUSIBILITY_WINDOW_DAYS)
    agg = (
        await session.execute(
            select(
                func.max(RainfallTimeseries.precip_mm),
                func.sum(RainfallTimeseries.precip_mm),
                func.count(),
            ).where(RainfallTimeseries.snapshot_at >= cutoff)
        )
    ).one()
    max_mm, sum_mm, n_window = (agg[0] or 0.0), (agg[1] or 0.0), (agg[2] or 0)
    checks["window_days"] = PLAUSIBILITY_WINDOW_DAYS
    checks["window_rows"] = n_window
    checks["window_max_mm"] = round(float(max_mm), 4)
    checks["window_sum_mm"] = round(float(sum_mm), 4)
    if is_implausibly_low_max(window_max_mm=max_mm, window_rows=n_window):
        problems.append(
            f"en {PLAUSIBILITY_WINDOW_DAYS} días la lectura MÁXIMA de todas las "
            f"comunas fue {max_mm:.4f} mm (suma {sum_mm:.2f} mm en {n_window} "
            "lecturas): implausible para Medellín, revisar unidad o campo de origen"
        )

    if problems:
        checks["problems"] = problems
    return ("warning" if problems else "ok"), {"rainfall_checks": checks}


async def validate_daily_rain_features(session: AsyncSession) -> tuple[str, dict]:
    """Plausibilidad de la lluvia DIARIA en `ml_features`.

    El camino histórico no se validaba en absoluto, y estaba roto en la dirección
    contraria al de tiempo real: valores de hasta 92.202 mm/día, cuando el récord
    mundial en 24 h son ~1.825 mm. Apunta a sumar un contador acumulado.
    """
    checks: dict = {"max_plausible_mm": MAX_PLAUSIBLE_DAILY_MM}
    problems: list[str] = []

    for key in DAILY_RAIN_KEYS:
        value = MLFeature.features[key].as_float()
        row = (
            await session.execute(
                select(func.max(value), func.avg(value), func.count()).where(
                    MLFeature.features.has_key(key)  # noqa: W601 — operador JSONB de SQLAlchemy
                )
            )
        ).one()
        max_v, avg_v, n = row[0], row[1], (row[2] or 0)
        if not n:
            continue
        checks[key] = {
            "n": n,
            "max": round(float(max_v or 0.0), 3),
            "avg": round(float(avg_v or 0.0), 3),
        }
        if max_v is not None and is_implausibly_high_daily(float(max_v)):
            problems.append(
                f"{key}: máximo {float(max_v):.1f} mm/día en {n} filas "
                f"(límite plausible {MAX_PLAUSIBLE_DAILY_MM}); "
                "posible acumulado sumado como si fuera diario"
            )

    if problems:
        checks["problems"] = problems
    return ("warning" if problems else "ok"), {"daily_rain_checks": checks}


async def validate_seismic_data(session: AsyncSession) -> tuple[str, dict]:
    """Rango de magnitudes y FRESCURA del feed sísmico."""
    stmt = select(SeismicEvent).order_by(SeismicEvent.ingested_at.desc()).limit(500)
    rows = (await session.scalars(stmt)).all()

    out_of_range = 0
    for row in rows:
        if row.magnitude is not None and not (MIN_SEISMIC_MAG <= row.magnitude <= MAX_SEISMIC_MAG):
            out_of_range += 1
            logger.warning(
                "Seismic event out of range: magnitude=%s at %s",
                row.magnitude,
                row.event_local_at,
            )

    checks: dict = {
        "total_checked": len(rows),
        "out_of_range": out_of_range,
        "range": f"{MIN_SEISMIC_MAG}-{MAX_SEISMIC_MAG}",
    }
    problems: list[str] = []
    if out_of_range:
        problems.append(f"{out_of_range} magnitudes fuera de rango")

    # ── Frescura ──────────────────────────────────────────────────────────────
    # El scraper reportaba `ok` en 93 corridas seguidas mientras el feed llevaba
    # 5 meses sin producir eventos nuevos: `records_valid=0` es indistinguible
    # de "el parser dejó de encajar". Esto lo distingue.
    latest = (await session.execute(select(func.max(SeismicEvent.event_local_at)))).scalar()
    checks["latest_event_at"] = latest.isoformat() if latest else None
    if latest is not None:
        days = (datetime.now(timezone.utc) - latest).days
        checks["days_since_last_event"] = days
        if is_stale(days, threshold_days=SEISMIC_STALE_DAYS):
            problems.append(
                f"el sismo más reciente es de hace {days} días "
                f"(umbral {SEISMIC_STALE_DAYS}): el feed o el parser parecen rotos"
            )
    elif rows:
        problems.append("hay filas sísmicas pero ninguna con fecha de evento")

    if problems:
        checks["problems"] = problems
    return ("warning" if problems else "ok"), {"seismic_checks": checks}


async def validate_geo_coverage(session: AsyncSession) -> tuple[str, dict]:
    """Detecta comunas sin datos de lluvia en las últimas 24h."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    stmt = select(RainfallTimeseries.commune_id).where(RainfallTimeseries.snapshot_at >= cutoff)
    covered = {row[0] for row in (await session.execute(stmt)).all()}

    all_communes = {c.id for c in COMMUNES}
    missing = sorted(all_communes - covered)

    findings = {
        "coverage_checks": {
            "covered_communes": len(covered),
            "total_communes": len(all_communes),
            "missing_communes": missing,
        }
    }
    status = "warning" if missing else "ok"
    return status, findings


def _worse(a: str, b: str) -> str:
    """Returns the more severe of two status strings by their fixed ordering."""
    order = {"ok": 0, "warning": 1, "critical": 2, "error": 3}
    return a if order.get(a, 0) >= order.get(b, 0) else b


_CHECKS = (
    validate_rainfall_data,
    validate_daily_rain_features,
    validate_seismic_data,
    validate_geo_coverage,
)


async def run() -> None:
    """Ejecuta todas las validaciones y reporta."""
    try:
        async with AsyncSessionLocal() as session:
            all_findings: dict = {}
            worst_status = "ok"

            for check in _CHECKS:
                try:
                    status, findings = await check(session)
                except Exception as exc:  # noqa: BLE001
                    # Un chequeo roto no debe anular a los demás: se registra
                    # como hallazgo y se sigue. La validación nunca tumba la
                    # ingesta (regla del repo), y tampoco se tumba a sí misma.
                    logger.exception("Check %s falló", check.__name__)
                    all_findings[check.__name__] = {"error": repr(exc)}
                    worst_status = _worse(worst_status, "error")
                    continue
                all_findings.update(findings)
                worst_status = _worse(worst_status, status)

            summary = f"Scraper data validation: {worst_status.upper()}"
            if worst_status == "ok":
                # Regla anti-ruido (CLAUDE.md): en `ok` NUNCA se postea a Slack.
                # Este agente corre tras cada scraper (~380 veces por semana);
                # un "OK" cada vez ahogaría las alertas reales.
                await log_agent_run(
                    session,
                    agent_name="scraper-data-validator",
                    status=worst_status,
                    summary=summary,
                    detail=all_findings,
                )
            else:
                await fire_agent_alert(
                    session,
                    agent_name="scraper-data-validator",
                    status=worst_status,
                    summary=summary,
                    detail=all_findings,
                )
    except Exception as e:
        logger.exception("Scraper validator failed")
        try:
            async with AsyncSessionLocal() as session:
                await fire_agent_alert(
                    session,
                    agent_name="scraper-data-validator",
                    status="error",
                    summary=f"Scraper validator error: {e}",
                )
        except Exception:
            logger.exception("Failed to report validator error")


if __name__ == "__main__":
    import asyncio

    from observability.logging_config import configure_logging

    configure_logging("monitoring-scraper-validator")
    asyncio.run(run())
