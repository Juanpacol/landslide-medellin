import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.rate_limit import rate_limit, rate_limit_by_session
from db.models import AgentConversation
from db.session import get_async_db
from integrations.agent_contracts import chat as agent_chat
from integrations.agent_contracts import chat_stream as agent_chat_stream

router = APIRouter()

# Cada mensaje de chat cuesta una llamada LLM: límite por IP contra abuso,
# spam y loops accidentales del frontend.
_chat_rate = rate_limit("chat", times=10, seconds=60)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    session_id: str = Field(..., min_length=1, max_length=128)


class ChatResponse(BaseModel):
    reply: str
    session_id: str


@router.post("", response_model=ChatResponse, dependencies=[Depends(_chat_rate)])
@router.post("/message", response_model=ChatResponse, dependencies=[Depends(_chat_rate)])
async def post_message(body: ChatRequest, db: AsyncSession = Depends(get_async_db)) -> ChatResponse:
    # Segundo nivel de límite, por sesión: protege contra una conversación
    # individual descontrolada más allá del límite compartido por IP (útil
    # detrás de NAT/proxy donde varias sesiones comparten la misma IP).
    rate_limit_by_session("chat_session", body.session_id, times=10, seconds=60)
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


@router.post("/stream", dependencies=[Depends(_chat_rate)])
async def stream_message(body: ChatRequest, db: AsyncSession = Depends(get_async_db)) -> StreamingResponse:
    """Variante en streaming (SSE) de `post_message()`.

    A diferencia de `post_message()`, aquí NO se guardan filas de
    `AgentConversation` en la ruta: `chat_stream()`/`chat_rag_stream()` ya
    hacen su propio `save_turn()` para el turno de usuario y el de asistente
    (igual que hace `chat()` hoy), así que la ruta solo retransmite los
    chunks como eventos SSE y comitea al final.
    """

    rate_limit_by_session("chat_session", body.session_id, times=10, seconds=60)

    async def event_source():
        async for chunk in agent_chat_stream(body.message, body.session_id, db):
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        await db.commit()
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream")


@router.get("/sessions")
async def list_sessions(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: str = Query("", max_length=200),
    db: AsyncSession = Depends(get_async_db),
) -> dict[str, Any]:
    """Lista sesiones de conversación agregando `agent_conversations`.

    No requiere tabla nueva: el título es el primer mensaje del usuario y el
    preview es el último mensaje de la sesión. `q` filtra sesiones cuyo
    contenido contenga el texto (case-insensitive).
    """
    base = select(
        AgentConversation.session_id,
        func.count().label("message_count"),
        func.min(AgentConversation.created_at).label("started_at"),
        func.max(AgentConversation.created_at).label("last_message_at"),
    ).group_by(AgentConversation.session_id)

    if q.strip():
        matching = (
            select(AgentConversation.session_id)
            .where(AgentConversation.content.ilike(f"%{q.strip()}%"))
            .distinct()
        )
        base = base.where(AgentConversation.session_id.in_(matching))

    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()

    rows = (
        await db.execute(
            base.order_by(desc("last_message_at")).limit(limit).offset(offset)
        )
    ).all()
    session_ids = [r.session_id for r in rows]

    first_user_msg: dict[str, str] = {}
    last_msg: dict[str, dict[str, str]] = {}
    if session_ids:
        rn_asc = (
            func.row_number()
            .over(
                partition_by=AgentConversation.session_id,
                order_by=AgentConversation.created_at.asc(),
            )
            .label("rn")
        )
        firsts = (
            select(AgentConversation.session_id, AgentConversation.content, rn_asc)
            .where(
                AgentConversation.session_id.in_(session_ids),
                AgentConversation.role == "user",
            )
            .subquery()
        )
        for sid, content in (
            await db.execute(
                select(firsts.c.session_id, firsts.c.content).where(firsts.c.rn == 1)
            )
        ).all():
            first_user_msg[sid] = content

        rn_desc = (
            func.row_number()
            .over(
                partition_by=AgentConversation.session_id,
                order_by=AgentConversation.created_at.desc(),
            )
            .label("rn")
        )
        lasts = (
            select(
                AgentConversation.session_id,
                AgentConversation.role,
                AgentConversation.content,
                rn_desc,
            )
            .where(AgentConversation.session_id.in_(session_ids))
            .subquery()
        )
        for sid, role, content in (
            await db.execute(
                select(lasts.c.session_id, lasts.c.role, lasts.c.content).where(
                    lasts.c.rn == 1
                )
            )
        ).all():
            last_msg[sid] = {"role": role, "content": content}

    def _truncate(text: str, length: int) -> str:
        text = " ".join(text.split())
        return text if len(text) <= length else text[: length - 1].rstrip() + "…"

    sessions = []
    for r in rows:
        title_src = first_user_msg.get(r.session_id, "Conversación sin título")
        last = last_msg.get(r.session_id, {})
        sessions.append(
            {
                "session_id": r.session_id,
                "title": _truncate(title_src, 80),
                "preview": _truncate(last.get("content", ""), 140),
                "preview_role": last.get("role"),
                "message_count": r.message_count,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "last_message_at": r.last_message_at.isoformat()
                if r.last_message_at
                else None,
            }
        )

    return {"sessions": sessions, "total": total, "limit": limit, "offset": offset}


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
