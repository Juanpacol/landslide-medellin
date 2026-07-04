"""
Autenticación mínima por bearer token para endpoints críticos.

Uso:
    from api.auth import require_token
    @router.post("/predict-all", dependencies=[Depends(require_token)])

Comportamiento:
- Si la variable de entorno API_TOKEN está definida, exige el header
  `Authorization: Bearer <API_TOKEN>`; si falta o no coincide → 401.
- Si API_TOKEN NO está definida (entorno de desarrollo), permite el acceso
  pero deja una advertencia en logs. Para producción, definir API_TOKEN.
"""

from __future__ import annotations

import logging
import os

from fastapi import Header, HTTPException, status

logger = logging.getLogger(__name__)


async def require_token(authorization: str | None = Header(default=None)) -> None:
    expected_token = os.getenv("API_TOKEN")

    if not expected_token:
        logger.warning(
            "API_TOKEN no configurado: endpoint crítico accesible sin auth (modo dev). "
            "Definir API_TOKEN en producción."
        )
        return

    if authorization != f"Bearer {expected_token}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o ausente.",
            headers={"WWW-Authenticate": "Bearer"},
        )
