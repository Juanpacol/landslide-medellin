from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AgentConversation


async def get_history(session_id: str, db: AsyncSession, limit: int = 10) -> list[dict[str, str]]:
    stmt = (
        select(AgentConversation)
        .where(AgentConversation.session_id == session_id)
        .order_by(AgentConversation.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    rows.reverse()
    return [{"role": r.role, "content": r.content} for r in rows]


async def save_turn(session_id: str, role: str, content: str, db: AsyncSession) -> None:
    row = AgentConversation(session_id=session_id, role=role, content=content)
    db.add(row)
    await db.flush()
