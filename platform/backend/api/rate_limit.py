"""
Rate limiting in-memory por IP — ventana fija, sin dependencias externas.

Suficiente para el despliegue actual (un solo proceso uvicorn detrás de
CORS restringido): protege el chat (costo LLM por request) y los endpoints
de predicción (costo CPU) de abuso o loops accidentales del frontend.

Limitación explícita: el contador vive en memoria del proceso. Con varios
workers/réplicas cada uno cuenta por separado — si se escala horizontalmente,
migrar a Redis (mismo interfaz, cambiar el backend de _hits).

Uso:
    from api.rate_limit import rate_limit
    @router.post("", dependencies=[Depends(rate_limit("chat", times=10, seconds=60))])
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

# clave (scope, ip) → timestamps de requests dentro de la ventana
_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_MAX_KEYS = 10_000  # tope defensivo de memoria


def _client_ip(request: Request) -> str:
    # Detrás de un proxy honesto, el primer hop de X-Forwarded-For es el cliente.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(scope: str, *, times: int, seconds: int):
    """Dependencia FastAPI: máx `times` requests por `seconds` por IP."""

    async def _dependency(request: Request) -> None:
        now = time.monotonic()
        key = (scope, _client_ip(request))
        window = _hits[key]

        while window and now - window[0] > seconds:
            window.popleft()

        if len(window) >= times:
            retry_after = max(1, int(seconds - (now - window[0])))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Demasiadas solicitudes; reintenta en {retry_after}s.",
                headers={"Retry-After": str(retry_after)},
            )
        window.append(now)

        # Poda defensiva: si el mapa crece demasiado (IPs efímeras), soltar
        # las claves vacías primero y, en el extremo, resetear.
        if len(_hits) > _MAX_KEYS:
            for k in [k for k, v in _hits.items() if not v]:
                _hits.pop(k, None)
            if len(_hits) > _MAX_KEYS:
                _hits.clear()

    return _dependency
