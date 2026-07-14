"""
ChromaDB Store — Vector store local para el RAG de TEYVA.

Ingiere los chunks JSON de las 4 fuentes (siata_hidromet, siata_geotecnia,
dagrd_eventos, medellin_comunas), genera embeddings multilingües con
sentence-transformers y los persiste en disco para búsqueda semántica.

Las 4 fuentes tienen esquemas de chunk distintos; aquí se normalizan a un
conjunto común de metadatos compatibles con ChromaDB (solo str/int/float/bool).

Uso:
    python -m rag.chroma_store --ingest          # carga/actualiza todos los chunks
    python -m rag.chroma_store --reset --ingest  # borra y reconstruye
    python -m rag.chroma_store --stats           # conteo por fuente
    python -m rag.chroma_store --test            # corre queries de prueba
    python -m rag.chroma_store --query "lluvia en junio"
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

RAG_DIR = Path(__file__).parent
DATA_DIR = RAG_DIR / "data"
CHROMA_DIR = DATA_DIR / "chroma_db"
COLLECTION_NAME = "teyva_knowledge"

EMBED_MODEL = os.getenv("RAG_EMBED_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")

# Las 4 fuentes y la ruta de su JSON de chunks.
SOURCES = {
    "siata_hidromet": DATA_DIR / "siata_hidromet" / "siata_hidromet_chunks.json",
    "siata_geotecnia": DATA_DIR / "siata_geotecnia" / "siata_geotecnia_chunks.json",
    "dagrd_eventos": DATA_DIR / "dagrd_eventos" / "dagrd_eventos_chunks.json",
    "medellin_comunas": DATA_DIR / "medellin_comunas" / "medellin_comunas_chunks.json",
}

# --- Singletons perezosos (evita recargar el modelo en cada llamada) ---
_client = None
_collection = None
_embed_fn = None


def _get_embedding_function():
    global _embed_fn
    if _embed_fn is None:
        from chromadb.utils import embedding_functions

        logger.info(f"Loading embedding model: {EMBED_MODEL} (primera vez descarga ~470MB)")
        _embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBED_MODEL
        )
    return _embed_fn


def get_collection(create: bool = True):
    """Devuelve la colección ChromaDB persistente (singleton)."""
    global _client, _collection
    if _collection is not None:
        return _collection

    import chromadb

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    _client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    ef = _get_embedding_function()
    if create:
        _collection = _client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
    else:
        _collection = _client.get_collection(name=COLLECTION_NAME, embedding_function=ef)
    return _collection


def _clean_metadata(chunk: dict[str, Any]) -> dict[str, Any]:
    """
    Normaliza el metadata de un chunk a un set común compatible con ChromaDB.
    ChromaDB solo acepta valores str/int/float/bool (no None, no listas).
    """
    def s(key: str, default: str = "") -> str:
        v = chunk.get(key)
        return str(v) if v is not None else default

    meta: dict[str, Any] = {
        "source_id": s("source_id"),
        # Campo de fecha unificado: week_start (hidromet) | event_date (dagrd)
        "date": s("week_start") or s("event_date"),
        # Zona / comuna unificada
        "zone": s("zone_name") or s("nombre"),
        "municipio": s("municipio"),
        "section": s("section"),
        "commune": s("commune_mentioned") or s("nombre"),
        "title": s("event_title"),
        "url": s("url"),
        # Archivo de origen real (PDF para hidromet/geotecnia).
        "source_pdf": s("source_pdf"),
        "grado_amenaza": s("grado_amenaza"),
        "ml_id": s("ml_id"),
        "page": chunk.get("page") if isinstance(chunk.get("page"), int) else 0,
    }
    # Elimina claves vacías para no inflar el índice.
    return {k: v for k, v in meta.items() if v not in ("", None)}


def _build_document(source_id: str, chunk: dict[str, Any]) -> str:
    """
    Construye el texto a embeber prependiendo un encabezado de contexto.

    Las fichas geotécnicas comparten mucho boilerplate ("Hoja de vida de
    movimiento en masa F-GAA-SIATA-94…"), lo que diluye el peso del nombre de
    zona en el embedding. Prepender "[Zona X, Municipio Y]" hace que las
    consultas por entidad (una comuna, una zona) recuperen el chunk correcto.
    """
    text = chunk.get("text", "").strip()
    if source_id == "siata_geotecnia":
        zona = chunk.get("zone_name", "")
        muni = chunk.get("municipio", "")
        header = f"[Zona: {zona} | Municipio: {muni}]"
    elif source_id == "medellin_comunas":
        nombre = chunk.get("nombre", "")
        codigo = chunk.get("codigo", "")
        header = f"[Comuna: {nombre} (código {codigo})]"
    elif source_id == "siata_hidromet":
        header = f"[Reporte SIATA semana {chunk.get('week_start', '')} a {chunk.get('week_end', '')}]"
    elif source_id == "dagrd_eventos":
        header = f"[Evento DAGRD {chunk.get('event_date', '')}: {chunk.get('event_title', '')}]"
    else:
        header = ""
    return f"{header}\n{text}".strip() if header else text


def _load_chunks() -> tuple[list[str], list[str], list[dict]]:
    """Lee los 4 JSON y devuelve (ids, documents, metadatas)."""
    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict] = []

    for source_id, path in SOURCES.items():
        if not path.exists():
            logger.warning(f"  [{source_id}] JSON no encontrado: {path} — se omite")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        chunks = data.get("chunks", [])
        for c in chunks:
            cid = c.get("chunk_id")
            text = c.get("text", "").strip()
            if not cid or not text:
                continue
            ids.append(cid)
            docs.append(_build_document(source_id, c))
            metas.append(_clean_metadata(c))
        logger.info(f"  [{source_id}] {len(chunks)} chunks cargados")

    return ids, docs, metas


def ingest(reset: bool = False, batch_size: int = 128) -> None:
    """Ingiere todos los chunks en ChromaDB (idempotente vía upsert)."""
    import chromadb

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
            logger.info(f"Colección '{COLLECTION_NAME}' borrada (reset)")
        except Exception:
            pass

    global _client, _collection
    _client = client
    _collection = None  # fuerza recreación
    collection = get_collection(create=True)

    ids, docs, metas = _load_chunks()
    if not ids:
        logger.error("No hay chunks para ingerir")
        return

    logger.info(f"Ingiriendo {len(ids)} chunks en batches de {batch_size}...")
    for i in range(0, len(ids), batch_size):
        batch_ids = ids[i : i + batch_size]
        batch_docs = docs[i : i + batch_size]
        batch_metas = metas[i : i + batch_size]
        collection.upsert(ids=batch_ids, documents=batch_docs, metadatas=batch_metas)
        logger.info(f"  {min(i + batch_size, len(ids))}/{len(ids)} embebidos")

    total = collection.count()
    logger.info("=" * 60)
    logger.info(f"INGESTA COMPLETA — {total} chunks en '{COLLECTION_NAME}'")
    logger.info(f"  Persistido en: {CHROMA_DIR}")
    logger.info("=" * 60)


def search(
    query: str,
    source: Optional[str] = None,
    n: int = 5,
    zone: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    Búsqueda semántica en el RAG.

    Args:
        query: texto de consulta.
        source: filtra por source_id (siata_hidromet, siata_geotecnia,
                dagrd_eventos, medellin_comunas). None = todas.
        n: número de resultados.
        zone: filtra por zona/comuna exacta (ej. "Villatina"). Garantiza que
              las consultas por entidad recuperen el chunk correcto y no se
              mezclen zonas vecinas con boilerplate similar.

    Returns:
        Lista de {text, metadata, distance} ordenada por relevancia.
    """
    collection = get_collection(create=False)

    conds = []
    if source:
        conds.append({"source_id": source})
    if zone:
        conds.append({"zone": zone})
    if len(conds) == 1:
        where = conds[0]
    elif len(conds) > 1:
        where = {"$and": conds}
    else:
        where = None

    res = collection.query(
        query_texts=[query],
        n_results=n,
        where=where,
    )

    out: list[dict[str, Any]] = []
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    for doc, meta, dist in zip(docs, metas, dists):
        out.append({"text": doc, "metadata": meta or {}, "distance": dist})
    return out


_KNOWN_ZONES: dict[str, str] | None = None


def _strip_accents(s: str) -> str:
    import unicodedata

    return "".join(
        c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn"
    )


def known_zones() -> dict[str, str]:
    """
    Mapea nombre de zona normalizado → nombre original, leyendo las zonas
    geotécnicas del JSON. Se usa para detectar entidades en la query y filtrar.
    """
    global _KNOWN_ZONES
    if _KNOWN_ZONES is not None:
        return _KNOWN_ZONES
    zones: dict[str, str] = {}
    path = SOURCES["siata_geotecnia"]
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        for c in data.get("chunks", []):
            zn = c.get("zone_name")
            if zn:
                zones[_strip_accents(zn)] = zn
    _KNOWN_ZONES = zones
    return zones


def detect_zone(query: str) -> Optional[str]:
    """Devuelve el nombre de zona si la query menciona una zona conocida."""
    q = _strip_accents(query)
    # Empareja primero los nombres más largos (ej. "la bermejala" antes que "la").
    for norm in sorted(known_zones(), key=len, reverse=True):
        if len(norm) >= 4 and norm in q:
            return known_zones()[norm]
    return None


def stats() -> dict[str, int]:
    """Conteo de chunks por fuente en la colección."""
    collection = get_collection(create=False)
    total = collection.count()
    counts: dict[str, int] = {"_total": total}
    for source_id in SOURCES:
        try:
            res = collection.get(where={"source_id": source_id}, limit=100000)
            counts[source_id] = len(res.get("ids", []))
        except Exception:
            counts[source_id] = -1
    return counts


def _run_tests() -> None:
    """Corre queries de prueba sobre las 4 fuentes."""
    test_queries = [
        ("lluvia acumulada en junio 2026", None),
        ("deslizamiento en Villatina características", "siata_geotecnia"),
        ("amenaza por movimientos en masa Comuna 13", "medellin_comunas"),
        ("emergencia derrumbe reportada por DAGRD", "dagrd_eventos"),
        ("pronóstico de lluvia para la siguiente semana", "siata_hidromet"),
    ]
    for query, source in test_queries:
        print("\n" + "=" * 70)
        print(f"QUERY: {query!r}  (source={source})")
        print("=" * 70)
        results = search(query, source=source, n=3)
        for i, r in enumerate(results, 1):
            meta = r["metadata"]
            preview = r["text"][:160].replace("\n", " ")
            print(f"\n[{i}] dist={r['distance']:.4f} | {meta.get('source_id')} | "
                  f"{meta.get('date', '')} {meta.get('zone', '')}")
            print(f"    {preview}...")


def main() -> None:
    parser = argparse.ArgumentParser(description="ChromaDB store para el RAG de TEYVA")
    parser.add_argument("--ingest", action="store_true", help="Ingiere los chunks")
    parser.add_argument("--reset", action="store_true", help="Borra la colección antes de ingerir")
    parser.add_argument("--stats", action="store_true", help="Muestra conteo por fuente")
    parser.add_argument("--test", action="store_true", help="Corre queries de prueba")
    parser.add_argument("--query", type=str, help="Ejecuta una query puntual")
    args = parser.parse_args()

    if args.ingest:
        ingest(reset=args.reset)
    if args.stats:
        for k, v in stats().items():
            print(f"  {k:20s} {v}")
    if args.test:
        _run_tests()
    if args.query:
        for i, r in enumerate(search(args.query, n=5), 1):
            meta = r["metadata"]
            print(f"\n[{i}] dist={r['distance']:.4f} | {meta.get('source_id')} | {meta.get('zone', '')}")
            print(f"    {r['text'][:200]}...")

    if not any([args.ingest, args.stats, args.test, args.query]):
        parser.print_help()


if __name__ == "__main__":
    main()
