from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AgentConversation
from infrastructure.cache import _MISSING, TTLCache

# TTL 5 min: cada turno de chat pega Postgres para leer el historial. El
# caché se invalida activamente en save_turn (no pasivamente por TTL) en
# cuanto la sesión recibe un turno nuevo, así que servir una versión vieja
# solo puede pasar si dos requests concurrentes de la MISMA sesión llegan
# a la vez — caso raro para un chat 1:1 por sesión.
_history_cache = TTLCache(ttl_seconds=300)


async def get_history(session_id: str, db: AsyncSession, limit: int = 10) -> list[dict[str, str]]:
    cache_key = (session_id, limit)
    cached = _history_cache.get(cache_key)
    if cached is not _MISSING:
        return cached

    stmt = (
        select(AgentConversation)
        .where(AgentConversation.session_id == session_id)
        .order_by(AgentConversation.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    rows.reverse()
    history = [{"role": r.role, "content": r.content} for r in rows]
    _history_cache.set(cache_key, history)
    return history


async def save_turn(session_id: str, role: str, content: str, db: AsyncSession) -> None:
    row = AgentConversation(session_id=session_id, role=role, content=content)
    db.add(row)
    await db.flush()
    # Invalida TODAS las claves (session_id, *) — una pregunta nueva en la
    # misma sesión no debe ver el historial cacheado antes de este turno.
    _history_cache.invalidate_prefix(session_id)
