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

echo "→ Aplicando migraciones (alembic upgrade head)..."
alembic upgrade head

echo "→ Reconstruyendo artefactos binarios (ChromaDB + modelo ML si no existen)..."
sh "$(dirname "$0")/setup_assets.sh"

echo "→ Iniciando API en :8000"
exec uvicorn api.main:app --host 0.0.0.0 --port 8000
