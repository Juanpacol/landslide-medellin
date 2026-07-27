FROM python:3.11-slim

# libgomp1: runtime de XGBoost. Sin compiladores: todas las deps traen wheels manylinux.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

# Instalar deps primero para aprovechar la caché de capas de Docker.
# requirements.txt trae el --extra-index-url de PyTorch CPU: sin él se bajarían
# ~5.5 GB de paquetes CUDA inservibles en un servidor sin GPU.
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Pre-bakear el modelo de embeddings (~500 MB). Sin esto se descarga en la
# PRIMERA consulta RAG y, como no hay caché persistente, se vuelve a descargar
# en cada reinicio del contenedor — el primer usuario tras cada deploy se come
# la espera, y en un host con rootfs de solo lectura el RAG fallaría siempre.
#
# Va ANTES del `COPY . .` para que la capa se cachee y no se invalide con cada
# cambio de código. Se instancia SentenceTransformer (baja safetensors +
# tokenizer); un snapshot_download sin filtros bajaría 4.6 GB de variantes
# onnx/openvino/tf que no se usan.
#
# RAG_EMBED_MODEL queda fijo a propósito: cambiarlo en runtime haría que el
# contenedor baje otro modelo Y dejaría el índice de chroma_db/ inconsistente
# (vectores de otro espacio de embeddings).
ENV HF_HOME=/opt/hf-cache \
    SENTENCE_TRANSFORMERS_HOME=/opt/hf-cache/sentence-transformers \
    RAG_EMBED_MODEL=paraphrase-multilingual-MiniLM-L12-v2
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"

COPY . .

RUN chmod +x ./docker-entrypoint.sh

# Documentativo: el entrypoint respeta $PORT si el host lo inyecta.
EXPOSE 8000

# python en vez de curl: la imagen slim no lo trae y no vale instalarlo solo
# para esto. start-period largo porque el entrypoint espera a Postgres (hasta
# 120 s) y corre las migraciones antes de levantar uvicorn.
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/health',timeout=4)" || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
