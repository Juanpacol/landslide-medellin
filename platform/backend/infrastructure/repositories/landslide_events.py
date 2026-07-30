"""
LandslideEvent repository — the is_synthetic=false filter is the ML
pipeline's golden rule (synthetic events calibrate Snake Line, they don't
train the classifier). Centralizing it stops a new consumer from forgetting it.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from db.models.landslide_event import LandslideEvent


def real_events_sync(session: Session) -> list[LandslideEvent]:
    """REAL events (excludes synthetic). Sync version for ml/train and
    ml/benchmark, which run outside the event loop."""
    return list(
        session.scalars(select(LandslideEvent).where(LandslideEvent.is_synthetic.is_(False))).all()
    )


async def real_events(session: AsyncSession) -> list[LandslideEvent]:
    result = await session.execute(
        select(LandslideEvent).where(LandslideEvent.is_synthetic.is_(False))
    )
    return list(result.scalars().all())
