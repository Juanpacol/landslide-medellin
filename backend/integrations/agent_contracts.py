from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

try:
    from agent.chat import chat as _chat_impl  # type: ignore[import-not-found]
except ImportError:
    _chat_impl: Callable[..., Awaitable[str]] | None = None

try:
    from ml.predict import predict_all_comunas as _predict_all_impl  # type: ignore[import-not-found]
except ImportError:
    _predict_all_impl: Callable[..., Awaitable[None]] | None = None

try:
    from ml.predict import predict_risk as _predict_risk_impl  # type: ignore[import-not-found]
except ImportError:
    _predict_risk_impl: Callable[..., Awaitable[dict[str, Any]]] | None = None


async def chat(message: str, session_id: str, db: AsyncSession) -> str:
    if _chat_impl is not None:
        return await _chat_impl(message, session_id, db)
    return (
        "Asistente TEYVA (modo demo): el módulo del Agente 2 aún no está enlazado. "
        f"Mensaje recibido ({len(message)} caracteres), sesión `{session_id}`."
    )


async def predict_all_comunas(db: AsyncSession) -> None:
    if _predict_all_impl is not None:
        await _predict_all_impl(db)
        return
    return None


async def predict_risk_stub(comuna_id: str, db: AsyncSession) -> dict[str, Any]:
    """Hasta que exista predict_risk del Agente 1."""
    if _predict_risk_impl is not None:
        try:
            cid = int(str(comuna_id))
        except ValueError:
            return {
                "commune_id": comuna_id,
                "risk_score": None,
                "detail": f"commune_id inválido: {comuna_id!r}",
            }
        out = await _predict_risk_impl(cid, db)
        out["commune_id"] = str(comuna_id)
        return out

    return {
        "commune_id": comuna_id,
        "risk_score": None,
        "detail": "predict_risk del Agente 1 no está disponible en este despliegue",
    }
