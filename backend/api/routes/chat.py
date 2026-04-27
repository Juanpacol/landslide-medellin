from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AgentConversation
from db.session import get_async_db
from integrations.agent_contracts import chat as agent_chat

router = APIRouter()


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    session_id: str = Field(..., min_length=1, max_length=128)


class ChatResponse(BaseModel):
    reply: str
    session_id: str


@router.post("", response_model=ChatResponse)
@router.post("/message", response_model=ChatResponse)
async def post_message(body: ChatRequest, db: AsyncSession = Depends(get_async_db)) -> ChatResponse:
    user_row = AgentConversation(
        session_id=body.session_id,
        role="user",
        content=body.message,
    )
    db.add(user_row)
    reply = await agent_chat(body.message, body.session_id, db)
    assistant_row = AgentConversation(
        session_id=body.session_id,
        role="assistant",
        content=reply,
    )
    db.add(assistant_row)
    await db.commit()
    return ChatResponse(reply=reply, session_id=body.session_id)


@router.get("/history/{session_id}")
async def get_history(
    session_id: str,
    limit: int = 40,
    db: AsyncSession = Depends(get_async_db),
) -> dict[str, Any]:
    stmt = (
        select(AgentConversation)
        .where(AgentConversation.session_id == session_id)
        .order_by(AgentConversation.created_at.asc())
        .limit(min(limit, 200))
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {
        "session_id": session_id,
        "messages": [
            {"role": r.role, "content": r.content, "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in rows
        ],
    }
