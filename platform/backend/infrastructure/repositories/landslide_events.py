"""
Repositorio de LandslideEvent — el filtro is_synthetic=false es la regla de
oro del pipeline ML (los sintéticos calibran Snake Line, no entrenan el
clasificador). Centralizarlo evita que un consumidor nuevo lo olvide.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from db.models.landslide_event import LandslideEvent


def real_events_sync(session: Session) -> list[LandslideEvent]:
    """Eventos REALES (excluye sintéticos). Versión sync para ml/train y
    ml/benchmark, que corren fuera del event loop."""
    return list(
        session.scalars(
            select(LandslideEvent).where(LandslideEvent.is_synthetic.is_(False))
        ).all()
    )


async def real_events(session: AsyncSession) -> list[LandslideEvent]:
    result = await session.execute(
        select(LandslideEvent).where(LandslideEvent.is_synthetic.is_(False))
    )
    return list(result.scalars().all())
