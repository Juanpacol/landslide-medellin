"""Alembic migration state: repo vs. database.

`alembic_state` does the I/O (reads `alembic/versions/` and the
`alembic_version` table); `diagnosis` classifies the result with a pure
function. The separation is what lets the logic be tested without a DB.
"""
