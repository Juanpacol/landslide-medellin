"""Orquestador en proceso: composición nombrada de pasos con dependencias y
trazabilidad estructurada. Sin infraestructura nueva (sin Redis/Kafka/colas)
— decisión de arquitectura del proyecto.

Formaliza el patrón que ya vivía disperso en `fire_alerts.py` (cada función
envolvía sus llamadas en try/except + logger.exception por separado). No
reemplaza ese contrato, lo hace explícito: un paso no crítico que falla se
loggea y NO bloquea a sus dependientes — mismo comportamiento de hoy
("un Slack caído no debe tumbar alertas ni predicciones").

Alcance deliberado — qué NO orquesta este módulo:
- Cross-workflow (scraper → predict en GitHub Actions): los 6 crons siguen
  siendo independientes, sin `needs:`/`workflow_run`. Encadenarlos sería
  infraestructura de orquestación nueva, aunque no cueste dinero.
- El retry declarado en `Step.retries` es una capacidad del módulo, no algo
  usado hoy en los pasos de `fire_alerts.py`: esos checks no son idempotentes
  de forma segura a nivel de paso completo (podrían re-marcar cooldown). El
  retry real y seguro ya vive en `infrastructure/external/slack_client.py::post_webhook`.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from errors.error_handler import TransientError, retry_transient_call

logger = logging.getLogger(__name__)


@dataclass
class Step:
    name: str
    fn: Callable[[], Awaitable[Any]]
    depends_on: tuple[str, ...] = ()
    retries: int = 0
    critical: bool = False


@dataclass
class StepResult:
    name: str
    status: str  # "ok" | "skipped" | "error"
    error: str | None = None
    duration_ms: float = 0.0


def _topological_order(steps: list[Step]) -> list[Step]:
    """Orden simple sobre `depends_on`. Sin paralelismo: el volumen actual
    (2-3 pasos por composición) no lo justifica."""
    by_name = {s.name: s for s in steps}
    ordered: list[Step] = []
    seen: set[str] = set()

    def visit(step: Step) -> None:
        if step.name in seen:
            return
        for dep_name in step.depends_on:
            dep = by_name.get(dep_name)
            if dep is not None:
                visit(dep)
        seen.add(step.name)
        ordered.append(step)

    for step in steps:
        visit(step)
    return ordered


async def run_steps(steps: list[Step]) -> list[StepResult]:
    """Ejecuta los pasos en orden topológico. Un paso cuya dependencia falló
    (y esa dependencia es `critical=True`) se salta (`status="skipped"`); en
    caso contrario se ejecuta igual — mismo espíritu de "un check caído no
    tumba a los demás"."""
    ordered = _topological_order(steps)
    results: dict[str, StepResult] = {}

    for step in ordered:
        blocked_by = [
            dep
            for dep in step.depends_on
            if dep in results
            and results[dep].status == "error"
            and next((s for s in ordered if s.name == dep), None) is not None
            and next(s for s in ordered if s.name == dep).critical
        ]
        if blocked_by:
            results[step.name] = StepResult(
                name=step.name,
                status="skipped",
                error=f"dependencia crítica falló: {blocked_by}",
            )
            logger.warning(
                "orchestrator: paso '%s' omitido, dependencia crítica falló",
                step.name,
                extra={"step": step.name, "status": "skipped"},
            )
            continue

        started = time.monotonic()
        try:
            if step.retries > 0:
                await retry_transient_call(
                    step.fn, attempts=step.retries, exceptions=(TransientError,)
                )
            else:
                await step.fn()
            duration_ms = (time.monotonic() - started) * 1000
            results[step.name] = StepResult(name=step.name, status="ok", duration_ms=duration_ms)
            logger.info(
                "orchestrator: paso '%s' ok (%.0fms)",
                step.name,
                duration_ms,
                extra={"step": step.name, "status": "ok", "duration_ms": duration_ms},
            )
        except Exception as exc:  # noqa: BLE001
            duration_ms = (time.monotonic() - started) * 1000
            results[step.name] = StepResult(
                name=step.name, status="error", error=str(exc), duration_ms=duration_ms
            )
            logger.exception(
                "orchestrator: paso '%s' falló (%.0fms)",
                step.name,
                duration_ms,
                extra={"step": step.name, "status": "error", "duration_ms": duration_ms},
            )

    return [results[s.name] for s in ordered]
