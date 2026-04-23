from __future__ import annotations

import asyncio
import html
import re
from datetime import datetime, timezone
from typing import Any

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.landslide_event import LandslideEvent
from db.session import AsyncSessionLocal
from scraper.common import httpx_client, log_scrape_run, utcnow, with_retries

DAGRD_PORTAL = "https://www.medellin.gov.co/es/dagrd/"
WP_SEARCH_URL = "https://www.medellin.gov.co/es/wp-json/wp/v2/posts"

LANDSLIDE_KEYWORDS = (
    "deslizamiento",
    "deslizamientos",
    "movimiento en masa",
    "movimientos en masa",
    "derrumbe",
    "derrumbes",
)


def _strip_html(text: str) -> str:
    return BeautifulSoup(text, "html.parser").get_text(" ", strip=True)


def _parse_commune_from_text(text: str) -> str | None:
    m = re.search(r"comuna\s*(\d{1,2})\b", text, flags=re.IGNORECASE)
    if m:
        return str(int(m.group(1)))
    m2 = re.search(r"corregimiento\s*(\d{2,3})\b", text, flags=re.IGNORECASE)
    if m2:
        code = m2.group(1)
        mapping = {"50": "17", "60": "18", "70": "19", "80": "20", "90": "21"}
        return mapping.get(code)
    return None


def _event_date_from_wp(post: dict[str, Any]) -> str:
    dt_s = post.get("date_gmt") or post.get("date") or ""
    if not dt_s:
        return utcnow().date().isoformat()
    try:
        dt = datetime.fromisoformat(dt_s.replace("Z", "+00:00"))
        return dt.date().isoformat()
    except ValueError:
        return utcnow().date().isoformat()


async def _fetch_wp_posts(client: httpx.AsyncClient, term: str) -> list[dict[str, Any]]:
    params = {"search": term, "per_page": 20, "page": 1}

    async def _call():
        r = await client.get(WP_SEARCH_URL, params=params)
        r.raise_for_status()
        return r.json()

    data = await with_retries(_call)
    return data if isinstance(data, list) else []


async def _fetch_dagrd_home(client: httpx.AsyncClient) -> str:
    async def _call():
        r = await client.get(DAGRD_PORTAL)
        r.raise_for_status()
        return r.text

    return await with_retries(_call)


async def _collect_dagrd_events() -> tuple[list[dict[str, Any]], int, str | None]:
    detail_parts: list[str] = []
    posts: list[dict[str, Any]] = []
    async with httpx_client() as client:
        html_home = await _fetch_dagrd_home(client)
        soup = BeautifulSoup(html_home, "html.parser")
        alert_candidates = []
        for tag in soup.find_all(string=re.compile("alerta|emergencia|desliz", re.I)):
            parent = tag.parent
            if parent:
                alert_candidates.append(_strip_html(str(parent))[:500])
        detail_parts.append(f"dagrd_html_blocks={len(alert_candidates)}")

        seen_ids: set[int] = set()
        for term in ("deslizamiento", "movimiento en masa", "DAGRD emergencia"):
            batch = await _fetch_wp_posts(client, term)
            for p in batch:
                pid = int(p["id"])
                if pid in seen_ids:
                    continue
                seen_ids.add(pid)
                posts.append(p)

        events: list[dict[str, Any]] = []
        for post in posts:
            title = html.unescape(_strip_html(post.get("title", {}).get("rendered", "")))
            body = html.unescape(_strip_html(post.get("content", {}).get("rendered", "")))
            blob = f"{title} {body}".lower()
            if not any(k in blob for k in LANDSLIDE_KEYWORDS):
                continue
            fecha = _event_date_from_wp(post)
            commune = _parse_commune_from_text(f"{title} {body}")
            sid = f"wp:{post.get('id')}"
            events.append(
                {
                    "source_row_id": sid,
                    "fecha": fecha,
                    "tipo_emergencia": title[:500]
                    if title
                    else "Evento relacionado con movimiento en masa",
                    "commune_id": commune,
                }
            )

    detail = " | ".join(detail_parts) if detail_parts else None
    return events, len(posts), detail


async def _event_exists(
    session: AsyncSession,
    *,
    fecha: str,
    commune_id: str | None,
    source_row_id: str | None,
) -> bool:
    if source_row_id:
        stmt = select(LandslideEvent.id).where(LandslideEvent.source_row_id == source_row_id).limit(1)
        if await session.scalar(stmt):
            return True
    if commune_id:
        stmt = (
            select(LandslideEvent.id)
            .where(LandslideEvent.fecha == fecha, LandslideEvent.commune_id == commune_id)
            .limit(1)
        )
        return bool(await session.scalar(stmt))
    return False


async def _run_dagrd(session: AsyncSession) -> int:
    started = utcnow()
    status = "error"
    downloaded = 0
    discarded = 0
    inserted = 0
    detail: str | None = None
    try:
        events, downloaded, detail = await _collect_dagrd_events()
        for ev in events:
            if await _event_exists(
                session,
                fecha=ev["fecha"],
                commune_id=ev["commune_id"],
                source_row_id=ev["source_row_id"],
            ):
                discarded += 1
                continue
            session.add(
                LandslideEvent(
                    source_row_id=ev["source_row_id"],
                    fecha=ev["fecha"],
                    tipo_emergencia=ev["tipo_emergencia"],
                    commune_id=ev["commune_id"],
                    barrio=None,
                    latitud=None,
                    longitud=None,
                    has_coords=False,
                )
            )
            inserted += 1
        await session.commit()
        status = "ok"
    except Exception as exc:  # noqa: BLE001
        detail = (detail + " | " if detail else "") + repr(exc)
        await session.rollback()
        raise
    finally:
        await log_scrape_run(
            session,
            source="dagrd",
            status=status,
            run_started_at=started,
            records_downloaded=downloaded,
            records_valid=inserted,
            records_discarded=discarded,
            detail=detail,
        )
    return inserted


async def run_dagrd_scraper(session: AsyncSession | None = None) -> int:
    if session is None:
        async with AsyncSessionLocal() as s:
            return await _run_dagrd(s)
    return await _run_dagrd(session)


async def main():
    n = await run_dagrd_scraper()
    print("dagrd_inserted", n)


if __name__ == "__main__":
    asyncio.run(main())
