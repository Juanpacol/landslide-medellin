"""
In-memory per-IP rate limiting — fixed window, no external dependencies.

Enough for the current deployment (a single uvicorn process behind
restricted CORS): protects chat (LLM cost per request) and prediction
endpoints (CPU cost) from abuse or accidental frontend loops.

Explicit limitation: the counter lives in the process's memory. With
several workers/replicas, each counts separately — if scaled horizontally,
migrate to Redis (same interface, swap _hits's backend).

Usage:
    from api.rate_limit import rate_limit
    @router.post("", dependencies=[Depends(rate_limit("chat", times=10, seconds=60))])
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

# key (scope, ip) → request timestamps within the window
_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_MAX_KEYS = 10_000  # defensive memory cap


def _client_ip(request: Request) -> str:
    # Behind an honest proxy, X-Forwarded-For's first hop is the client.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_and_record(scope: str, key: str, *, times: int, seconds: int) -> None:
    """Rate limit core, parametrized by a generic key (IP or session_id).

    Extracted from what used to be `_dependency`'s body so it can be reused
    both from the FastAPI dependency (key = IP) and from
    `rate_limit_by_session` (key = session_id, called by hand).
    """
    now = time.monotonic()
    full_key = (scope, key)
    window = _hits[full_key]

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

    # Defensive pruning: if the map grows too large (ephemeral IPs/sessions),
    # drop empty keys first and, in the extreme case, reset it.
    if len(_hits) > _MAX_KEYS:
        for k in [k for k, v in _hits.items() if not v]:
            _hits.pop(k, None)
        if len(_hits) > _MAX_KEYS:
            _hits.clear()


def rate_limit(scope: str, *, times: int, seconds: int):
    """FastAPI dependency: max `times` requests per `seconds` per IP."""

    async def _dependency(request: Request) -> None:
        _check_and_record(scope, _client_ip(request), times=times, seconds=seconds)

    return _dependency


def rate_limit_by_session(scope: str, session_id: str, *, times: int, seconds: int) -> None:
    """Limit by `session_id`, called by hand inside the handler.

    Can't be a `Depends` like `rate_limit()`: session_id is only available
    after parsing the body (same reason `log_audit_event` in api/audit.py
    is also called by hand). Shares the `_hits` dict with the per-IP limit
    — the (scope, session_id) key is indistinguishable from (scope, ip) to
    the rest of the logic, so they coexist without collision as long as the
    `scope`s used are distinct.
    """
    _check_and_record(scope, session_id, times=times, seconds=seconds)
