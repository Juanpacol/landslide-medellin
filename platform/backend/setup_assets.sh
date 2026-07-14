#!/bin/sh
# ──────────────────────────────────────────────────────────────────────────────
# setup_assets.sh — Reconstruye los artefactos binarios excluidos del repo git.
#
# Qué hace:
#   1. Construye el índice ChromaDB (RAG) desde los chunks JSON que sí están
#      en el repo.  Necesario para que el agente conversacional pueda buscar
#      contexto en documentos SIATA, DAGRD, geotecnia y comunas.
#   2. Entrena el modelo ML (XGBoost) y guarda best_model.pkl + scaler.pkl.
#      Necesario para que el endpoint /api/risk/predict funcione.
#
# Por qué no están en git:
#   Los PDFs fuente pesan ~1.4 GB en total y superan los límites de GitHub.
#   Los artefactos binarios (ChromaDB, .pkl) son regenerables desde los datos
#   ya procesados que sí están versionados.
#
# Requisitos previos:
#   - PYTHONPATH apuntando a platform/backend (se establece abajo)
#   - Variables de entorno DATABASE_URL / DATABASE_URL_SYNC configuradas
#   - Dependencias Python instaladas (pip install -r requirements.txt)
#   - La base de datos ya debe tener datos (scrapers corridos al menos una vez)
#
# Uso típico al desplegar:
#   cd platform/backend
#   sh setup_assets.sh
#
# Uso en Docker (ver docker-entrypoint.sh — se llama automáticamente):
#   Se invoca antes de `alembic upgrade head` la primera vez que no existe
#   el índice ChromaDB o el modelo.
# ──────────────────────────────────────────────────────────────────────────────
set -e

BACKEND_DIR="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="$BACKEND_DIR:${PYTHONPATH:-}"

CHROMA_DIR="$BACKEND_DIR/rag/data/chroma_db"
MODEL_PATH="$BACKEND_DIR/ml/models/best_model.pkl"

# ── 1. ChromaDB ────────────────────────────────────────────────────────────────
if [ -d "$CHROMA_DIR" ] && [ "$(ls -A "$CHROMA_DIR" 2>/dev/null)" ]; then
    echo "[setup_assets] ✓ ChromaDB ya existe — se omite la ingesta"
else
    echo "[setup_assets] → Construyendo índice ChromaDB (RAG)..."
    echo "    Fuentes: siata_hidromet · siata_geotecnia · dagrd_eventos · medellin_comunas"
    python -m rag.chroma_store --ingest
    echo "[setup_assets] ✓ ChromaDB listo"
fi

# ── 2. Modelo ML ───────────────────────────────────────────────────────────────
if [ -f "$MODEL_PATH" ]; then
    echo "[setup_assets] ✓ Modelo ML ya existe (best_model.pkl) — se omite entrenamiento"
else
    echo "[setup_assets] → Entrenando modelo ML (XGBoost)..."
    echo "    Requiere datos en la base de datos (tabla ml_features con registros)."
    if python -m ml.train; then
        echo "[setup_assets] ✓ Modelo entrenado y guardado"
    else
        echo "[setup_assets] ✗ Entrenamiento falló (puede no haber datos suficientes)."
        echo "    El sistema seguirá funcionando pero /api/risk/predict retornará score=0."
        echo "    Vuelve a correr:  python -m ml.train"
    fi
fi

echo "[setup_assets] ✓ Setup completado"
