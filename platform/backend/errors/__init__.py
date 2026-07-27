"""Jerarquía de excepciones y manejo de errores estratificado.

Vive fuera de domain/application/infrastructure a propósito, igual que
constants.py: es plomería transversal (excepciones + retry genérico), sin
lógica de negocio, para poder importarse desde cualquier capa sin invertir
la dirección de dependencias.
"""

from errors.error_handler import (
    BusinessError,
    TeyvaError,
    TransientError,
    ValidationError,
    handle_errors,
    retry_transient_call,
)

__all__ = [
    "BusinessError",
    "TeyvaError",
    "TransientError",
    "ValidationError",
    "handle_errors",
    "retry_transient_call",
]
