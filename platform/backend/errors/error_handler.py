"""Manejo de errores estratificado en 3 categorías, más un retry genérico.

- ValidationError: entrada inválida. Rechazo inmediato, sin retry, sin fallback.
- BusinessError: falla de dominio esperada (ej. comuna sin predicción). Log +
  fallback humano, nunca retry, nunca 5xx.
- TransientError: falla de dependencia externa (red, timeout, 5xx). Candidata
  a retry con backoff exponencial.

No reemplaza `scraper/common.py::with_retries` (ya probado en producción,
scrapers no se tocan) ni el "nunca lanza" deliberado de
`infrastructure/external/slack_client.py::post_webhook` — este módulo da la
primitiva de retry que `post_webhook` usa internamente, ver ahí.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Awaitable, Callable
from typing import Any, ClassVar, TypeVar

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

T = TypeVar("T")


class TeyvaError(Exception):
    """Base de la jerarquía. No instanciar directamente."""

    http_status: ClassVar[int] = 500


class ValidationError(TeyvaError):
    """Dato de entrada inválido. Rechazo inmediato, sin retry, sin fallback."""

    http_status: ClassVar[int] = 422


class BusinessError(TeyvaError):
    """Falla de dominio esperada (ej. comuna sin predicción, umbral fuera de
    rango). Se loggea y responde con un fallback legible; nunca se reintenta
    y nunca es 5xx — es un estado válido del negocio, no una falla del sistema."""

    http_status: ClassVar[int] = 404


class TransientError(TeyvaError):
    """Falla de una dependencia externa (timeout, conexión, 5xx). Candidata a
    retry con backoff exponencial vía `retry_transient_call`."""

    http_status: ClassVar[int] = 503


async def retry_transient_call(
    factory: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay_s: float = 1.0,
    exceptions: tuple[type[BaseException], ...] = (TransientError,),
) -> T:
    """Backoff exponencial genérico (mismo algoritmo de scraper/common.py::with_retries,
    reescrito como primitiva de propósito general para código nuevo — Slack,
    orquestador). Solo reintenta las excepciones listadas en `exceptions`;
    cualquier otra se re-lanza de inmediato sin consumir intentos."""
    delay = base_delay_s
    last: BaseException | None = None
    for attempt in range(attempts):
        try:
            return await factory()
        except exceptions as exc:
            last = exc
            if attempt == attempts - 1:
                raise
            logger.warning(
                "retry_transient_call: intento %d/%d falló (%s), reintentando en %.1fs",
                attempt + 1,
                attempts,
                exc,
                delay,
            )
            await asyncio.sleep(delay)
            delay *= 2.0
    assert last is not None
    raise last


def handle_errors(op_name: str, *, fallback: Any = None, retries: int = 0):
    """Decorador para funciones async de application/agent/.

    - ValidationError se re-lanza tal cual (rechazo inmediato, el llamador o
      el manejador HTTP global decide qué hacer).
    - TransientError: si retries>0 se reintenta con backoff; al agotar los
      intentos se loggea ERROR estructurado (op_name, categoría, excepción)
      y se devuelve `fallback` en vez de propagar — mismo espíritu del
      try/except disperso hoy en el repo, pero con categoría visible en logs.
    - BusinessError y cualquier excepción no clasificada: se loggean
      (WARNING para BusinessError, ERROR para el resto) y se devuelve
      `fallback` — nunca tumban al llamador.
    """

    def decorator(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T | Any]]:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> T | Any:
            async def _call() -> T:
                return await fn(*args, **kwargs)

            try:
                if retries > 0:
                    return await retry_transient_call(
                        _call, attempts=retries, exceptions=(TransientError,)
                    )
                return await _call()
            except ValidationError:
                raise
            except TransientError as exc:
                logger.error(
                    "handle_errors[%s]: transient tras agotar reintentos: %s",
                    op_name,
                    exc,
                    extra={"op": op_name, "category": "transient"},
                )
                return fallback
            except BusinessError as exc:
                logger.warning(
                    "handle_errors[%s]: business: %s",
                    op_name,
                    exc,
                    extra={"op": op_name, "category": "business"},
                )
                return fallback
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "handle_errors[%s]: no clasificada: %s",
                    op_name,
                    exc,
                    extra={"op": op_name, "category": "unclassified"},
                    exc_info=True,
                )
                return fallback

        return wrapper

    return decorator


def install_exception_handlers(app: FastAPI) -> None:
    """Registra handlers globales para la jerarquía TeyvaError.

    No interfiere con las HTTPException que ya lanzan api/auth.py y
    api/rate_limit.py: FastAPI mantiene su manejador default para
    excepciones no registradas explícitamente aquí.
    """

    @app.exception_handler(ValidationError)
    async def _validation_handler(request: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content={"detail": str(exc)})

    @app.exception_handler(BusinessError)
    async def _business_handler(request: Request, exc: BusinessError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content={"detail": str(exc)})

    @app.exception_handler(TransientError)
    async def _transient_handler(request: Request, exc: TransientError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content={"detail": str(exc)},
            headers={"Retry-After": "5"},
        )
