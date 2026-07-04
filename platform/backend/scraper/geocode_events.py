from __future__ import annotations

import asyncio
import json
from typing import Any

from sqlalchemy import select

from db.models.landslide_event import LandslideEvent
from db.session import AsyncSessionLocal
from scraper.commune import lookup_commune_for_point
from scraper.common import httpx_client
from scraper.historical_backfill import _commune_from_text


async def main() -> None:
    async with AsyncSessionLocal() as session:
        null_events = (
            await session.execute(
                select(LandslideEvent).where(LandslideEvent.commune_id.is_(None)).order_by(LandslideEvent.id.asc())
            )
        ).scalars().all()

        total_null = len(null_events)
        geocoded_from_coords = 0
        resolved_from_text = 0

        async with httpx_client(timeout=60.0) as client:
            for idx, event in enumerate(null_events, start=1):
                resolved_commune: str | None = None

                if event.latitud is not None and event.longitud is not None:
                    try:
                        info = await lookup_commune_for_point(client, float(event.longitud), float(event.latitud))
                        resolved_commune = info.get("ml_commune_id")
                    except Exception:
                        resolved_commune = None
                    if resolved_commune:
                        geocoded_from_coords += 1
                else:
                    text = (event.tipo_emergencia or "").strip()
                    if text:
                        resolved_commune = _commune_from_text(text)
                        if resolved_commune:
                            resolved_from_text += 1

                if resolved_commune:
                    event.commune_id = str(resolved_commune)

                if idx % 250 == 0:
                    await session.commit()

        await session.commit()

        remaining_null = int(
            len(
                (
                    await session.execute(select(LandslideEvent.id).where(LandslideEvent.commune_id.is_(None)))
                ).scalars().all()
            )
        )

        result: dict[str, Any] = {
            "total_with_null_commune_id": total_null,
            "geocoded_with_coordinates": geocoded_from_coords,
            "resolved_from_text": resolved_from_text,
            "still_null": remaining_null,
        }
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
