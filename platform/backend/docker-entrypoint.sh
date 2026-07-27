#!/bin/sh
set -e

echo "→ Esperando a que PostgreSQL acepte conexiones..."
python - <<'PY'
import os, time
import psycopg2

url = os.environ["DATABASE_URL_SYNC"]
for i in range(60):
    try:
        psycopg2.connect(url).close()
        print("  ✓ PostgreSQL listo")
        break
    except Exception as exc:
        print(f"  intento {i + 1}/60: {exc}")
        time.sleep(2)
else:
    raise SystemExit("✗ PostgreSQL no respondió a tiempo")
PY

# Guard de drift: si la BD quedó adelante del repo (imagen vieja, o migración
# aplicada sin commitear), `alembic upgrade head` falla con "Can't locate
# revision" y el contenedor entra en crash loop — que no arregla el drift y sí
# tumba el dashboard. En ese caso se arranca igual: la BD ya tiene el esquema.
# El `if` es lo que evita que `set -e` aborte cuando el guard sale != 0.
# Separación de privilegios DDL: contra Supabase el rol de la app no puede
# migrar, así que ni se intenta (si no, cada arranque fallaría). Contra la
# Postgres local del compose sí, y todo sigue igual que antes.
if python -c "import sys; from infrastructure.migrations.ddl_url import can_run_ddl; sys.exit(0 if can_run_ddl() else 1)" 2>/dev/null; then
    echo "→ Verificando estado de migraciones..."
    if python -m monitoring.migration_guard --preflight --json > /tmp/migration_guard.json 2>&1; then
        if grep -q '"safe_to_upgrade": true' /tmp/migration_guard.json; then
            echo "→ Aplicando migraciones (alembic upgrade head)..."
            alembic upgrade head
        else
            echo "⚠ BD adelante del repo — se omite 'alembic upgrade head'"
            cat /tmp/migration_guard.json
        fi
    else
        echo "⚠ El guard no pudo evaluar el estado; se intenta el upgrade como antes"
        cat /tmp/migration_guard.json || true
        alembic upgrade head
    fi
else
    echo "→ Sin credencial DDL y la BD es remota: se omiten las migraciones."
    echo "  Es lo ESPERADO — el rol de la app no tiene DDL y las aplica GitHub"
    echo "  Actions al pushear a main. Ver docs/RUNBOOK_MIGRATIONS.md"
fi

# $PORT: Render/Railway/Heroku lo inyectan dinámicamente. docker-compose no lo
# define, así que cae a 8000 y nada cambia en local.
PORT="${PORT:-8000}"

# --proxy-headers: detrás del proxy de un PaaS, sin esto uvicorn reconstruye
# las URLs como http:// y rompe los redirects.
#
# Sin --workers a propósito: cada worker carga su propia copia de torch + el
# modelo de embeddings (~1.2 GB RSS c/u). Dos workers = OOM en cualquier
# instancia de menos de 3 GB.
echo "→ Iniciando API en :${PORT}"
exec uvicorn api.main:app \
    --host 0.0.0.0 \
    --port "${PORT}" \
    --proxy-headers \
    --forwarded-allow-ips="*"
