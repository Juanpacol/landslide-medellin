"""
Autenticación por bearer token con dos niveles: admin y viewer.

Tokens (variables de entorno):
- API_TOKEN         → rol admin: endpoints mutantes/operativos (umbrales,
                      webhooks, predicciones manuales, reportes).
- API_TOKEN_VIEWER  → rol viewer (opcional): lectura autenticada donde se
                      exija. Un token admin siempre satisface viewer.

Comportamiento por entorno:
- Desarrollo (ENV != production y sin API_TOKEN): se permite el acceso con
  warning en logs, igual que antes.
- Producción (ENV/ENVIRONMENT == "production"): API_TOKEN es OBLIGATORIO.
  `assert_production_auth()` corre en el startup de FastAPI y tumba el
  arranque si falta — un despliegue mal configurado no puede quedar abierto.

Uso:
    from api.auth import require_token, require_viewer
    @router.post("/predict-all", dependencies=[Depends(require_token)])   # admin
    @router.get("/algo",         dependencies=[Depends(require_viewer)])  # viewer o admin
"""

from __future__ import annotations

import hmac
import logging
import os

from fastapi import Header, HTTPException, status

logger = logging.getLogger(__name__)


def _env() -> str:
    return (os.getenv("ENV") or os.getenv("ENVIRONMENT") or "development").strip().lower()


def is_production() -> bool:
    return _env() in {"production", "prod"}


def assert_production_auth() -> None:
    """Llamar en el startup de la app: en producción sin API_TOKEN, abortar."""
    if is_production() and not os.getenv("API_TOKEN"):
        raise RuntimeError(
            "ENV=production sin API_TOKEN definido: los endpoints mutantes quedarían "
            "abiertos. Definir API_TOKEN (y opcionalmente API_TOKEN_VIEWER) antes de arrancar."
        )


def _bearer(authorization: str | None) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization.removeprefix("Bearer ")


def _matches(provided: str | None, expected: str | None) -> bool:
    if not provided or not expected:
        return False
    return hmac.compare_digest(provided, expected)


async def require_token(authorization: str | None = Header(default=None)) -> None:
    """Rol admin: exige el token API_TOKEN."""
    expected = os.getenv("API_TOKEN")

    if not expected:
        if is_production():
            # assert_production_auth() ya debería haber tumbado el arranque;
            # defensa en profundidad por si la app se montó sin ese hook.
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth no configurada.")
        logger.warning(
            "API_TOKEN no configurado: endpoint crítico accesible sin auth (modo dev). "
            "Definir API_TOKEN en producción."
        )
        return

    if not _matches(_bearer(authorization), expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o ausente.",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def require_viewer(authorization: str | None = Header(default=None)) -> None:
    """Rol viewer: acepta API_TOKEN_VIEWER o API_TOKEN (admin ⊇ viewer)."""
    admin = os.getenv("API_TOKEN")
    viewer = os.getenv("API_TOKEN_VIEWER")

    if not admin and not viewer:
        if is_production():
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth no configurada.")
        logger.warning("Sin tokens configurados: acceso viewer sin auth (modo dev).")
        return

    provided = _bearer(authorization)
    if _matches(provided, admin) or _matches(provided, viewer):
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido o ausente.",
        headers={"WWW-Authenticate": "Bearer"},
    )
