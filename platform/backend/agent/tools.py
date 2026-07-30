from __future__ import annotations

import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import LandslideEvent, RiskPrediction

# Fuente única de verdad del territorio: domain/communes.py.
# Se re-exportan resolve_commune_id / commune_display_name / find_communes_in_text
# porque media docena de módulos (chat, rag_tools, alerts) los importan de aquí.
from domain.communes import COMMUNES as _COMMUNES
from domain.communes import display_name as commune_display_name  # noqa: F401
from domain.communes import find_communes_in_text  # noqa: F401
from domain.communes import resolve_commune_id  # noqa: F401


def _normalize_token(s: str) -> str:
    """Lowercase and strip diacritics from a token for loose matching."""
    s = s.strip().lower()
    nkfd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nkfd if unicodedata.category(c) != "Mn")


COMMUNE_LABELS: dict[str, str] = {c.id: c.nombre for c in _COMMUNES}


def _latest_per_commune_subquery() -> Any:
    """Build a subquery selecting each commune's most recent prediction timestamp."""
    return (
        select(
            RiskPrediction.commune_id.label("cid"),
            func.max(RiskPrediction.created_at).label("max_ca"),
        )
        .group_by(RiskPrediction.commune_id)
        .subquery()
    )


async def get_risk_by_comuna(nombre_o_id: str, db: AsyncSession) -> dict[str, Any] | None:
    """Fetch the latest risk prediction for a commune by name or id."""
    cid = resolve_commune_id(nombre_o_id)
    if cid is None:
        return None
    rp = RiskPrediction
    stmt = (
        select(rp).where(rp.commune_id == cid).order_by(rp.created_at.desc(), rp.id.desc()).limit(1)
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        return {
            "commune_id": cid,
            "nombre": commune_display_name(cid),
            "risk_score": None,
            "risk_category": None,
            "explanation": None,
            "created_at": None,
        }
    return {
        "commune_id": row.commune_id,
        "nombre": commune_display_name(row.commune_id),
        "risk_score": row.risk_score,
        "risk_category": row.risk_category,
        "explanation": row.explanation,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def get_historical_events(
    comuna_id: str, db: AsyncSession, limit: int = 10, *, days_back: int | None = None
) -> list[dict[str, Any]]:
    """Eventos recientes por comuna. ``days_back`` filtra por ``ingested_at`` (opcional)."""
    le = LandslideEvent
    stmt = select(le).where(le.commune_id == comuna_id)
    if days_back is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        stmt = stmt.where(le.ingested_at >= cutoff)
    stmt = stmt.order_by(le.ingested_at.desc()).limit(limit)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r.id,
                "fecha": r.fecha,
                "tipo_emergencia": r.tipo_emergencia,
                "commune_id": r.commune_id,
                "barrio": r.barrio,
                "ingested_at": r.ingested_at.isoformat() if r.ingested_at else None,
            }
        )
    return out


async def get_top_risk_comunas(n: int, db: AsyncSession) -> list[dict[str, Any]]:
    """Return the top ``n`` communes by latest risk score, descending."""
    sub = _latest_per_commune_subquery()
    rp = RiskPrediction
    stmt = (
        select(rp)
        .join(sub, (rp.commune_id == sub.c.cid) & (rp.created_at == sub.c.max_ca))
        .order_by(rp.risk_score.desc(), rp.commune_id.asc())
        .limit(n)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        {
            "commune_id": r.commune_id,
            "nombre": commune_display_name(r.commune_id),
            "risk_score": r.risk_score,
            "risk_category": r.risk_category,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


async def get_top_event_comunas(n: int, db: AsyncSession) -> list[dict[str, Any]]:
    """Top comunas por número de eventos históricos en landslide_events."""
    le = LandslideEvent
    stmt = (
        select(le.commune_id, func.count(le.id).label("n_eventos"))
        .where(le.commune_id.is_not(None))
        .group_by(le.commune_id)
        .order_by(func.count(le.id).desc(), le.commune_id.asc())
        .limit(n)
    )
    result = await db.execute(stmt)
    rows = result.all()
    return [
        {
            "commune_id": str(cid),
            "nombre": commune_display_name(str(cid)),
            "n_eventos": int(n_eventos or 0),
        }
        for cid, n_eventos in rows
    ]


async def compare_comunas(lista_comunas: list[str], db: AsyncSession) -> list[dict[str, Any]]:
    """Resolve a list of commune names/ids and fetch each one's latest risk."""
    resolved: list[str] = []
    for item in lista_comunas:
        cid = resolve_commune_id(item)
        if cid and cid not in resolved:
            resolved.append(cid)
    table: list[dict[str, Any]] = []
    for cid in resolved:
        row = await get_risk_by_comuna(cid, db)
        if row:
            table.append(row)
    return table


_ALERT_LEVELS = (
    "alto",
    "alta",
    "critico",
    "crítico",
    "critica",
    "crítica",
)


async def get_alert_status(db: AsyncSession) -> list[dict[str, Any]]:
    """List communes currently at alert-level risk (alto/critico), sorted by score."""
    sub = _latest_per_commune_subquery()
    rp = RiskPrediction
    stmt = select(rp).join(sub, (rp.commune_id == sub.c.cid) & (rp.created_at == sub.c.max_ca))
    result = await db.execute(stmt)
    rows = result.scalars().all()
    alerts: list[dict[str, Any]] = []
    for r in rows:
        cat = (r.risk_category or "").strip().lower()
        cat_norm = "".join(
            c for c in unicodedata.normalize("NFD", cat) if unicodedata.category(c) != "Mn"
        )
        if cat_norm in _ALERT_LEVELS:
            alerts.append(
                {
                    "commune_id": r.commune_id,
                    "nombre": commune_display_name(r.commune_id),
                    "risk_score": r.risk_score,
                    "risk_category": r.risk_category,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
            )
    alerts.sort(key=lambda x: (-(x["risk_score"] or 0), x["commune_id"]))
    return alerts
