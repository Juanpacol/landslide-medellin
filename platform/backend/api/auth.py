"""
Bearer-token authentication with two levels: admin and viewer.

Tokens (environment variables):
- API_TOKEN         → admin role: mutating/operational endpoints
                      (thresholds, webhooks, manual predictions, reports).
- API_TOKEN_VIEWER  → viewer role (optional): authenticated reads where
                      required. An admin token always satisfies viewer.

Behavior per environment:
- Development (ENV != production and no API_TOKEN): access is allowed
  with a log warning, same as before.
- Production (ENV/ENVIRONMENT == "production"): API_TOKEN is MANDATORY.
  `assert_production_auth()` runs at FastAPI startup and aborts startup
  if it's missing — a misconfigured deployment can't stay open.

Usage:
    from api.auth import require_token, require_viewer
    @router.post("/predict-all", dependencies=[Depends(require_token)])   # admin
    @router.get("/algo",         dependencies=[Depends(require_viewer)])  # viewer or admin
"""

from __future__ import annotations

import hmac
import logging

from fastapi import Header, HTTPException, status

from config import settings

logger = logging.getLogger(__name__)


def _env() -> str:
    return (settings.ENV or settings.ENVIRONMENT or "development").strip().lower()


def is_production() -> bool:
    return _env() in {"production", "prod"}


def assert_production_auth() -> None:
    """Call at app startup: in production without API_TOKEN, abort."""
    if is_production() and not settings.API_TOKEN:
        raise RuntimeError(
            "ENV=production without API_TOKEN set: mutating endpoints would be "
            "left open. Set API_TOKEN (and optionally API_TOKEN_VIEWER) before starting."
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
    """Admin role: requires the API_TOKEN token."""
    expected = settings.API_TOKEN

    if not expected:
        if is_production():
            # assert_production_auth() should already have aborted startup;
            # defense in depth in case the app was mounted without that hook.
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth no configurada."
            )
        logger.warning(
            "API_TOKEN not set: critical endpoint reachable without auth (dev mode). "
            "Set API_TOKEN in production."
        )
        return

    if not _matches(_bearer(authorization), expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o ausente.",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def require_viewer(authorization: str | None = Header(default=None)) -> None:
    """Viewer role: accepts API_TOKEN_VIEWER or API_TOKEN (admin ⊇ viewer)."""
    admin = settings.API_TOKEN
    viewer = settings.API_TOKEN_VIEWER

    if not admin and not viewer:
        if is_production():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth no configurada."
            )
        logger.warning("No tokens configured: viewer access without auth (dev mode).")
        return

    provided = _bearer(authorization)
    if _matches(provided, admin) or _matches(provided, viewer):
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido o ausente.",
        headers={"WWW-Authenticate": "Bearer"},
    )
