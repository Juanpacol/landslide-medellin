"""
DAGRD Eventos Chunker

Extrae reportes de emergencias (deslizamientos, derrumbes, movimientos en masa)
del portal WordPress de la Alcaldía de Medellín / DAGRD y los convierte en chunks.

Output:
    rag/data/dagrd_eventos/
    ├── md/
    │   └── dagrd_eventos_all.md
    └── dagrd_eventos_chunks.json

Uso:
    python -m rag.dagrd_chunker
    python -m rag.dagrd_chunker --max-pages 2   # para testing
"""

import json
import logging
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

RAG_DIR = Path(__file__).parent
SOURCE_ID = "dagrd_eventos"
SOURCE_DIR = RAG_DIR / "data" / SOURCE_ID
MD_DIR = SOURCE_DIR / "md"

WP_API = "https://www.medellin.gov.co/es/wp-json/wp/v2/posts"
SEARCH_TERMS = ["deslizamiento", "derrumbe", "movimiento en masa", "DAGRD emergencia"]
HEADERS = {"User-Agent": "TEYVA-Scraper/1.0"}
CHUNK_SIZE = 1200

COMMUNE_PATTERN = re.compile(
    r"comuna\s+(\d{1,2})|barrio\s+([\w\s]+)|corregimiento\s+([\w\s]+)",
    re.IGNORECASE,
)


@dataclass
class Chunk:
    chunk_id: str
    text: str
    source_id: str
    event_id: str           # WordPress post ID
    event_date: str         # YYYY-MM-DD
    event_title: str
    commune_mentioned: Optional[str]
    url: str
    chunk_index: int
    token_estimate: int


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _clean_html(html: str) -> str:
    """Extrae texto limpio de HTML con BeautifulSoup."""
    soup = BeautifulSoup(html, "html.parser")
    # Elimina scripts, estilos e imágenes
    for tag in soup(["script", "style", "img", "figure"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    # Limpia líneas vacías múltiples
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    return text


def _extract_commune(text: str) -> Optional[str]:
    """Extrae mención de comuna del texto del post."""
    m = COMMUNE_PATTERN.search(text)
    if m:
        return m.group(0).strip()
    return None


def _fetch_posts(max_pages: Optional[int] = None) -> list[dict]:
    """
    Pagina a través de todos los términos de búsqueda y devuelve
    posts únicos deduplicados por ID.
    """
    seen_ids: set[int] = set()
    all_posts: list[dict] = []

    for term in SEARCH_TERMS:
        page = 1
        while True:
            if max_pages and page > max_pages:
                break
            try:
                r = requests.get(
                    WP_API,
                    params={"search": term, "per_page": 20, "page": page},
                    headers=HEADERS,
                    timeout=15,
                )
                if r.status_code != 200:
                    break
                posts = r.json()
                if not posts:
                    break

                new = [p for p in posts if p["id"] not in seen_ids]
                for p in new:
                    seen_ids.add(p["id"])
                    all_posts.append(p)

                logger.info(f"  term='{term}' page={page} → {len(posts)} posts ({len(new)} nuevos)")

                if len(posts) < 20:
                    break
                page += 1
                time.sleep(0.3)  # rate limiting suave

            except Exception as e:
                logger.warning(f"  Error fetching term='{term}' page={page}: {e}")
                break

    logger.info(f"Total unique posts fetched: {len(all_posts)}")
    return all_posts


def _post_to_chunks(post: dict, chunk_counter: list[int]) -> list[Chunk]:
    """Convierte un post WordPress en uno o más chunks."""
    post_id = str(post["id"])
    raw_date = post.get("date", "")
    try:
        event_date = datetime.fromisoformat(raw_date).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        event_date = raw_date[:10] if raw_date else "sin-fecha"

    title = BeautifulSoup(
        post.get("title", {}).get("rendered", ""), "html.parser"
    ).get_text(strip=True)

    content_html = post.get("content", {}).get("rendered", "")
    excerpt_html = post.get("excerpt", {}).get("rendered", "")
    content_text = _clean_html(content_html) or _clean_html(excerpt_html)
    url = post.get("link", "")

    if not content_text:
        return []

    commune = _extract_commune(f"{title} {content_text}")

    # Divide en chunks si el contenido es largo
    paragraphs = content_text.split("\n\n")
    chunks = []
    current_text = ""

    def _flush(text_block: str) -> None:
        text_block = text_block.strip()
        if len(text_block) < 50:  # descarta fragmentos muy cortos
            return
        chunk_counter[0] += 1
        idx = chunk_counter[0]
        chunks.append(
            Chunk(
                chunk_id=f"{SOURCE_ID}_{post_id}_c{idx}",
                text=text_block,
                source_id=SOURCE_ID,
                event_id=post_id,
                event_date=event_date,
                event_title=title,
                commune_mentioned=commune,
                url=url,
                chunk_index=idx,
                token_estimate=_estimate_tokens(text_block),
            )
        )

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if current_text and len(current_text) + len(para) > CHUNK_SIZE:
            _flush(current_text)
            current_text = ""
        current_text += para + "\n\n"
    _flush(current_text)

    return chunks


def _chunks_to_markdown(chunks: list[Chunk]) -> str:
    """Genera Markdown estructurado con todos los chunks DAGRD."""
    # Agrupa por fecha para el índice
    by_date: dict[str, list[Chunk]] = {}
    for c in chunks:
        by_date.setdefault(c.event_date, []).append(c)

    keywords = [
        "deslizamiento", "derrumbe", "movimiento en masa", "DAGRD",
        "emergencia", "evacuación", "Medellín", "riesgo", "lluvia",
    ]

    md_lines = [
        "# EVENTOS DAGRD — EMERGENCIAS DE DESLIZAMIENTOS Y DERRUMBES",
        "Alcaldía de Medellín — Portal Oficial / DAGRD",
        f"Eventos procesados: {len(chunks)} chunks de {len(by_date)} fechas únicas",
        "",
        f"**Quick Summary**: Reportes oficiales de emergencias asociadas a deslizamientos, "
        f"derrumbes y movimientos en masa en Medellín y el Valle de Aburrá. "
        f"Fuente: portal oficial Alcaldía de Medellín.",
        "",
        f"**Keywords**: {', '.join(keywords)}",
        "",
        "---",
        "",
    ]

    for chunk in chunks:
        title = f"CHUNK {chunk.chunk_index}: EVENTO DAGRD — {chunk.event_date}"
        commune_str = f" | COMUNA: {chunk.commune_mentioned}" if chunk.commune_mentioned else ""

        md_lines += [
            f"## {title}",
            "",
            f"SOURCE: DAGRD — Alcaldía de Medellín",
            f"EVENT_ID: {chunk.event_id}",
            f"DATE: {chunk.event_date}",
            f"TITLE: {chunk.event_title}",
            f"URL: {chunk.url}{commune_str}",
            f"ID: {chunk.chunk_id}",
            f"TOKENS: ~{chunk.token_estimate} (self-contained)",
            "",
            f"### {chunk.event_title}",
            "",
        ]

        for line in chunk.text.splitlines():
            line = line.strip()
            md_lines.append(line if line else "")

        md_lines += ["", "---", ""]

    return "\n".join(md_lines)


def run(max_pages: Optional[int] = None) -> None:
    """Pipeline: fetch WordPress → chunks → Markdown + JSON."""
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    MD_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Fetch posts
    posts = _fetch_posts(max_pages=max_pages)
    if not posts:
        logger.error("No posts fetched from DAGRD")
        return

    # Ordena por fecha descendente
    posts.sort(key=lambda p: p.get("date", ""), reverse=True)

    # 2. Convierte a chunks
    counter = [0]
    all_chunks: list[Chunk] = []
    for post in posts:
        chunks = _post_to_chunks(post, counter)
        all_chunks.extend(chunks)

    if not all_chunks:
        logger.error("No chunks generated")
        return

    # 3. Guarda Markdown
    md_path = MD_DIR / f"{SOURCE_ID}_all.md"
    md_path.write_text(_chunks_to_markdown(all_chunks), encoding="utf-8")
    logger.info(f"  Saved MD: {md_path.name}")

    # 4. Guarda JSON para ChromaDB
    json_path = SOURCE_DIR / f"{SOURCE_ID}_chunks.json"
    output = {
        "metadata": {
            "source_id": SOURCE_ID,
            "source_name": "DAGRD — Alcaldía de Medellín",
            "source_url": WP_API,
            "processed_at": datetime.now().isoformat(),
            "total_posts": len(posts),
            "total_chunks": len(all_chunks),
        },
        "chunks": [asdict(c) for c in all_chunks],
    }
    json_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    logger.info("=" * 60)
    logger.info(f"DONE — source: {SOURCE_ID}")
    logger.info(f"  Posts fetched  : {len(posts)}")
    logger.info(f"  Total chunks   : {len(all_chunks)}")
    logger.info(f"  Markdown       : {md_path}")
    logger.info(f"  JSON for RAG   : {json_path}")
    logger.info("=" * 60)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="DAGRD Eventos Chunker")
    parser.add_argument("--max-pages", type=int, help="Límite de páginas por término (para testing)")
    args = parser.parse_args()
    run(max_pages=args.max_pages)
