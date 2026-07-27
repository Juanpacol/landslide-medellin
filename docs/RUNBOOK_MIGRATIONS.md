# Runbook — Drift de migraciones (Alembic ↔ Supabase)

Llegaste aquí desde una alerta de Slack de `migration-drift-guard` o de un
workflow fallido. Este documento es para resolver eso rápido.

## Diagnóstico

```bash
cd platform/backend && export PYTHONPATH=.
python -m monitoring.migration_guard --json
```

El campo `kind` dice qué pasa:

| `kind` | Qué significa | Gravedad |
|---|---|---|
| `ok` | Repo y BD sincronizados | — |
| `db_ahead` | La BD tiene una revisión que **no existe en el repo** | 🚨 crítico |
| `multiple_heads` | El repo tiene 2+ heads; `upgrade head` es ambiguo | 🚨 crítico |
| `pending` | Hay migraciones del repo sin aplicar en la BD | ⚠️ normal si es reciente |
| `empty_db` | La BD no tiene tabla `alembic_version` | ⚠️ |

---

## `db_ahead` — el caso más común

**Qué pasó:** alguien aplicó una migración a Supabase sin commitear el archivo.
`alembic_version` apunta a una revisión que GitHub Actions no encuentra al hacer
checkout de `main`.

**Impacto:** los 6 crons con `alembic upgrade head` fallarían. Gracias al guard
**la ingesta sigue corriendo** (se omite el upgrade), pero cualquier migración
nueva queda bloqueada hasta arreglarlo.

**Arreglo normal** — el archivo existe en local, solo falta subirlo:

```bash
# La revisión que falta viene en detail.unknown_revisions de la alerta.
git status --short platform/backend/alembic/versions/
git add platform/backend/alembic/versions/<revision>_*.py
git commit -m "fix(db): commitear migración <revision> aplicada a Supabase"
git push origin main
```

Con eso repo y BD vuelven a converger solos en el siguiente cron. Verificar:

```bash
python -m monitoring.migration_guard --json   # debe decir kind: ok
```

**Si el archivo se perdió** (no está en ninguna máquina): hay que decidir si la
BD retrocede o el repo avanza.

- Si el esquema que introdujo esa migración **no se necesita**, apuntar
  `alembic_version` a la última revisión que sí está en el repo:
  ```sql
  UPDATE alembic_version SET version_num = '<revision_del_repo>';
  ```
  ⚠️ Solo si el esquema real de la BD coincide con esa revisión. Si no, hay que
  revertir a mano los objetos que creó la migración perdida.
- Si el esquema **sí se necesita**, escribir una migración nueva que lo declare
  y usar `alembic stamp` para reconciliar.

---

## `multiple_heads`

Pasa al mergear dos ramas que agregaron migraciones en paralelo.

```bash
cd platform/backend && export PYTHONPATH=.
alembic heads                       # ver los heads
alembic merge -m "merge heads" <head1> <head2>
```

Commitear la migración de merge resultante. El job `migration-guard` de CI
bloquea los PRs que introduzcan este estado.

---

## `pending`

Normal justo después de mergear una migración: el siguiente cron la aplica sola
(≤30 min con SIATA). El guard **no alerta en la primera detección** por eso.

Si persiste, algo impide aplicarlas — revisar el log del último cron. Para
forzar:

```bash
cd platform/backend && export PYTHONPATH=. && alembic upgrade head
```

---

## Regla operativa que evita todo esto

> **Aplicar migraciones a Supabase solo desde `main` ya pusheado.**

La secuencia correcta es: escribir la migración → commit → push → dejar que el
cron la aplique (o correr `alembic upgrade head` **después** del push). Aplicar
primero y commitear después es exactamente lo que causó el incidente del
2026-07-26.

Nota: la BD es **una sola** (Supabase) para GitHub Actions, Docker local y
desarrollo a mano. No hay entorno de staging donde equivocarse sin consecuencias.

---

## Cómo está armada la protección

| Pieza | Dónde | Qué hace |
|---|---|---|
| `migration_guard` | `platform/backend/monitoring/migration_guard.py` | Diagnostica; alerta a Slack solo en transición o cada 6 h |
| Lectura de estado | `platform/backend/infrastructure/migrations/` | `alembic_state.py` (I/O) + `diagnosis.py` (puro) |
| Pre-flight en crons | `.github/actions/db-migrate/` | Omite el upgrade si no es seguro; la ingesta no se detiene |
| Vigilancia independiente | `.github/workflows/monitor-api-health.yml` | Cada 30 min, aunque los crons de ingesta estén caídos |
| Chequeo estático en PRs | job `migration-guard` de `ci-tests.yml` | Bloquea heads múltiples; sin BD ni secretos |
| Aviso de cron rojo | `.github/actions/notify-failure/` | Slack cuando cualquier workflow falla |
| Arranque del contenedor | `platform/backend/docker-entrypoint.sh` | Arranca igual en vez de crash loop |

### Lo que esto NO previene

Nada en el repo impide aplicar una migración desde un portátil a la BD
compartida. La prevención real sería un rol de Supabase separado para DDL,
revocándoselo al rol de desarrollo. Queda como mejora pendiente.
