"""
Root conftest for the test suite.

DB/Ollama integration fixtures (`db_session`, `require_ollama`) live in
`tests/integration/conftest.py` — importing `db.session` at collection time
requires `DATABASE_URL`/`DATABASE_URL_SYNC` to be set, which would break
`pytest tests/unit --collect-only` with no DB env vars / no network.

This file intentionally stays free of I/O-touching imports so that
`tests/unit/` can be collected and run with zero external dependencies.
"""

from __future__ import annotations
