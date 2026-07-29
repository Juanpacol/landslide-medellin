# SPEC-003 — plan.md

## Architecture

`application/` layer: orchestrates `domain/rules` (pure) and `ml/hazard.py` (I/O), so it is the
correct home per the existing dependency direction (`api/scraper → application → domain/infrastructure`).

## Files touched

- `application/neurosymbolic/__init__.py`
- `application/neurosymbolic/infer.py` — `Verdict`, `infer_commune()`, `infer_all()`.
- `application/predict_risk.py` — wired to call `infer_all()` instead of using `hazard_by_commune`
  directly.
- `alembic/versions/xxxx_add_derivation_columns.py` — new migration, nullable JSON columns on
  `risk_predictions` (`derivation`, `confidence`, `conflicts`).
- `api/routes/risk.py` — extend `/comuna/{id}/detalle`, add `/derivation/{id}`.
- `docs/adr/0003-conflict-resolution-precedence.md`.

## Interfaces

```python
@dataclass(frozen=True)
class Verdict:
    commune_id: str
    score: float | None
    level: str
    confidence: float
    derivation: dict[str, Any]
    conflicts: list[dict[str, Any]]
    calibration_status: str

async def infer_commune(session: AsyncSession, commune_id: str, *, as_of: date | None = None) -> Verdict: ...
async def infer_all(session: AsyncSession, *, as_of: date | None = None) -> dict[str, Verdict]: ...
```

## Sequencing

Depends on SPEC-002 (`domain/rules`). Blocks SPEC-004 (explanations consume `Verdict.derivation`).
Migration must be created and tested against local compose Postgres only, applied via GitHub
Actions from pushed `main` per `docs/RUNBOOK_MIGRATIONS.md`.
