# Contribuir a TEYVA

Guía práctica para trabajar en este repo. Para arquitectura, capas y contexto del proyecto, ver [CLAUDE.md](CLAUDE.md) — este documento no lo duplica.

## Alcance

- Todo el Python vive bajo `platform/backend/` como **un solo paquete**: los módulos se importan top-level (`from domain.communes...`, `from db.models...`). No crear carpetas raíz nuevas para Python — rompe imports y workflows de GitHub Actions.
- `domain/` no importa nada con I/O. Es la única fuente de verdad del territorio y las reglas de riesgo.
- Los entrypoints que invoca GitHub Actions (`python -m scraper.siata`, `python -m ml.predict`, etc.) no se mueven: son wrappers finos que delegan a `application/`.
- La dirección de dependencias es `api/scraper → application → domain/infrastructure`. Si tu cambio invierte esa dirección, probablemente está en la capa equivocada.

## Commits

Conventional Commits, en español, verificado contra el historial real del repo:

```
tipo(scope): mensaje breve en imperativo
```

Tipos usados: `feat`, `fix`, `refactor`, `docs`, `chore`, `ci`. El `scope` es el módulo tocado o el identificador de una serie de PRs relacionados (ej. `fix(db): ...`, `refactor(PR4): ...`).

**Hacer:**
- Mensajes claros y atómicos — un commit, un cambio conceptual.
- Explicar el *por qué* en el cuerpo cuando no sea obvio (una migración fallida, un bug reproducido, una decisión de arquitectura).

**No hacer:**
- `git commit -m "fix"` sin contexto.
- Mezclar varias features no relacionadas en un solo commit.

## Tests

```bash
cd platform/backend && export PYTHONPATH=.
pytest tests/ -v --tb=short
```

- **Filosofía "no mocks"** (documentada en `tests/conftest.py`): los tests de integración de agente/chat corren contra Postgres y Ollama reales, no contra mocks. Si tu cambio toca `agent/`, `rag/` o flujos de BD, verifica que esos servicios estén arriba antes de correr la suite completa.
- Los tests **puros** (sin BD, sin red) van igual en `tests/` sin subcarpetas — es el estilo del repo. `tests/test_migration_guard.py` es la plantilla de referencia: lógica separada de I/O, testeable en milisegundos.
- Evals de prompts: `/eval-prompt chat_rag|risk_explanations|slack_webhooks` (reportes en `tests/eval_results/`).
- No testear solo el happy path. Los scrapers en particular se prueban contra datos reales, no solo contra el caso feliz.
- **Correr los tests antes de pushear**, no después de que falle el CI.

## Code Style

```bash
cd platform/backend
ruff check .
ruff format .
```

Configuración en `ruff.toml`: Python 3.11, line-length 100, reglas `E`/`F`/`B` activas (`E501` ignorado — lo cubre `ruff format`). Hoy el lint corre **informativo** en CI por deuda preexistente; se espera que vuelva a bloquear tras una limpieza dedicada — no la agraves con código nuevo.

- Type hints obligatorios.
- `async` para toda operación de I/O.
- `snake_case` en Python; TypeScript en `strict`, camelCase, componentes en PascalCase.
- Docstrings en español que expliquen el **por qué** (una restricción no obvia, una decisión de diseño), no el qué — el código ya dice el qué.

**No hacer:** ignorar el linter porque "ya está en rojo". Cada archivo que toques debería quedar más limpio, no igual.

## Docs

- Actualizar `CLAUDE.md` si tu cambio altera la arquitectura, las capas, o una regla operativa (ej. cómo se aplican migraciones).
- Runbooks nuevos van en `docs/`, con el mismo tono que [`docs/RUNBOOK_MIGRATIONS.md`](docs/RUNBOOK_MIGRATIONS.md): diagnóstico → causa → arreglo → cómo se previno.

**No hacer:** dejar una feature nueva sin ninguna mención en `CLAUDE.md` si cambia cómo se opera el sistema.

## Pull Requests

- Descripción que explique **qué cambia y por qué** — no un PR vacío con solo el diff.
- Alcance: una cosa por PR. Si tu cambio toca 5 áreas no relacionadas, probablemente son 5 PRs.
- Gates reales de CI que vas a encontrar:
  - `ci-tests.yml`: pytest del backend es **bloqueante**; lint/format del backend es informativo (ver arriba); el job `migration-guard` es bloqueante y barato (~20s, sin BD) — impide que un PR introduzca 2+ heads de Alembic.
  - `ci-security.yml`: escaneo de secretos y dependencias.
  - Los workflows de despliegue/scrapers no corren en PRs; solo en `main`.

## Contacto

Owner: Juan Pablo Botero (jbotero@aztia.co) · Stakeholder: Gestión del Riesgo Medellín
