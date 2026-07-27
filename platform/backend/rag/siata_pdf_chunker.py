"""
SIATA PDF Chunker

Descarga reportes semanales HIDROMET de SIATA, extrae texto via OCR,
y chunketea el contenido en formato Markdown estructurado + JSON para ChromaDB.

Output:
    rag/data/siata_hidromet/
    ├── raw_pdfs/                                    # PDFs descargados
    ├── md/
    │   ├── siata_hidromet_YYYYMMDD_YYYYMMDD.md     # Markdown por semana
    │   └── siata_hidromet_all.md                   # Markdown combinado
    └── siata_hidromet_chunks.json                  # JSON para ChromaDB

Uso:
    python -m rag.siata_pdf_chunker --weeks 4
    python -m rag.siata_pdf_chunker --weeks 12
    python -m rag.siata_pdf_chunker --weeks 2 --max-downloads 1  # testing
"""

import json
import logging
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import pdfplumber
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# --- Paths ---
RAG_DIR = Path(__file__).parent
SOURCE_ID = "siata_hidromet"
SOURCE_DIR = RAG_DIR / "data" / SOURCE_ID
RAW_PDFS_DIR = SOURCE_DIR / "raw_pdfs"
MD_DIR = SOURCE_DIR / "md"

# --- Config ---
SIATA_REPORTE_URL = "https://siata.gov.co/reporte_semanal/"
CHUNK_SIZE = 1200  # caracteres máx por chunk

# Secciones conocidas en los PDFs HIDROMET (segunda línea de cada página)
SECTION_MAP = {
    "GESTIÓN DEL RIESGO": "Gestión del Riesgo - Resumen Semanal",
    "PRECIPITACIÓN": "Precipitación",
    "MOVIMIENTOS EN MASA": "Movimientos en Masa",
    "DESCARGAS ELÉCTRICAS": "Descargas Eléctricas",
    "INFORMACIÓN SATELITAL": "Información Satelital",
    "VIENTOS": "Vientos",
    "VARIABLES TÉRMICAS": "Variables Térmicas",
    "CICLONES TROPICALES": "Ciclones Tropicales",
    "PRONÓSTICO PARA LA SIGUIENTE SEMANA": "Pronóstico Siguiente Semana",
}

SECTION_KEYWORDS = {
    "Precipitación": ["precipitación", "lluvia", "acumulado", "pluvio", "mm"],
    "Movimientos en Masa": ["movimientos en masa", "deslizamiento", "ladera"],
    "Descargas Eléctricas": ["descarga", "rayos", "eléctrica", "relámpago"],
    "Pronóstico": ["pronóstico", "siguiente semana", "gfs", "gefs"],
    "Temperatura": ["temperatura", "humedad relativa", "radiación"],
    "Vientos": ["viento", "brisa", "km/h", "rosa de viento"],
    "Ciclones": ["ciclón", "huracán", "onda tropical"],
    "Satelital": ["goes", "nubosidad", "cobertura nubosa", "satélite"],
    "Gestión del Riesgo": ["gestión del riesgo", "alertas", "eventos de lluvia", "interacciones"],
}


@dataclass
class Chunk:
    """Representa un fragmento de texto con metadatos completos."""
    chunk_id: str          # p.ej. "siata_hidromet_20260615_p1_c1"
    text: str
    source_id: str         # "siata_hidromet"
    source_pdf: str        # "HIDROMET_20260615_20260621.pdf"
    week_start: str        # "2026-06-15"
    week_end: str          # "2026-06-21"
    page: int
    section: str           # Sección detectada
    chunk_index: int       # Índice global en el documento
    token_estimate: int    # Estimado de tokens


def _estimate_tokens(text: str) -> int:
    """Estimación simple: ~1 token por cada 4 caracteres."""
    return max(1, len(text) // 4)


def _extract_dates_from_filename(filename: str) -> tuple[str, str] | None:
    """Extrae fechas de HIDROMET_YYYYMMDD_YYYYMMDD.pdf"""
    match = re.search(r"HIDROMET_(\d{8})_(\d{8})", filename)
    if not match:
        return None
    try:
        start = datetime.strptime(match.group(1), "%Y%m%d").strftime("%Y-%m-%d")
        end = datetime.strptime(match.group(2), "%Y%m%d").strftime("%Y-%m-%d")
        return start, end
    except ValueError:
        return None


def _detect_section(text: str) -> str:
    """
    Detecta sección del chunk.
    Primero intenta leer el encabezado explícito de la página (segunda línea),
    luego hace keyword matching como fallback.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # Los PDFs HIDROMET tienen en la segunda línea el nombre de la sección
    if len(lines) >= 2:
        second_line = lines[1].upper()
        for key, label in SECTION_MAP.items():
            if key in second_line:
                return label

    # Fallback: keyword matching en todo el texto
    text_lower = text.lower()
    for section, keywords in SECTION_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return section

    return "General"


def _extract_keywords(text: str) -> list[str]:
    """Extrae palabras clave relevantes del texto para el header Markdown."""
    keyword_pool = [
        "precipitación", "lluvia", "acumulado", "mm", "movimientos en masa",
        "deslizamiento", "alerta", "riesgo", "temperatura", "vientos",
        "humedad", "descargas eléctricas", "rayos", "pronóstico", "Valle de Aburrá",
        "Medellín", "SIATA", "hidromet", "nubosidad", "satélite", "ciclón",
    ]
    text_lower = text.lower()
    return [kw for kw in keyword_pool if kw.lower() in text_lower][:12]


def _fetch_pdf_urls() -> list[tuple[str, str]]:
    """Scrapea el directorio SIATA y retorna [(filename, url)]."""
    try:
        resp = requests.get(SIATA_REPORTE_URL, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Error fetching SIATA directory: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    pdf_links = [
        (link.get_text(strip=True), urljoin(SIATA_REPORTE_URL, link.get("href")))
        for link in soup.find_all("a")
        if link.get("href", "").endswith(".pdf") or link.get_text(strip=True).endswith(".pdf")
    ]
    logger.info(f"Found {len(pdf_links)} PDFs in SIATA directory")
    return pdf_links


def _download_pdf(url: str, output_path: Path, max_retries: int = 3) -> bool:
    """Descarga PDF con reintentos y backoff exponencial."""
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            output_path.write_bytes(resp.content)
            logger.info(f"  ↓ {output_path.name} ({len(resp.content) / 1024 / 1024:.1f} MB)")
            return True
        except Exception as e:
            logger.warning(f"  Attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
    return False


def _extract_pages(pdf_path: Path) -> list[tuple[int, str]]:
    """Extrae texto de cada página con pdfplumber."""
    pages = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                if text.strip():
                    pages.append((i, text))
    except Exception as e:
        logger.error(f"Error reading {pdf_path.name}: {e}")
    return pages


def _split_page_into_chunks(
    page_num: int,
    text: str,
    source_pdf: str,
    week_start: str,
    week_end: str,
    chunk_counter: list[int],  # mutable counter compartido entre páginas
) -> list[Chunk]:
    """Divide el texto de una página en chunks del tamaño correcto."""
    section = _detect_section(text)
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    paragraphs = text.split("\n\n")

    date_compact = week_start.replace("-", "")
    chunks = []
    current_text = ""

    def _flush(text_block: str) -> None:
        text_block = text_block.strip()
        if not text_block:
            return
        chunk_counter[0] += 1
        idx = chunk_counter[0]
        chunk_id = f"{SOURCE_ID}_{date_compact}_p{page_num}_c{idx}"
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                text=text_block,
                source_id=SOURCE_ID,
                source_pdf=source_pdf,
                week_start=week_start,
                week_end=week_end,
                page=page_num,
                section=section,
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


def _chunks_to_markdown(chunks: list[Chunk], week_start: str, week_end: str) -> str:
    """
    Convierte lista de chunks en Markdown estructurado siguiendo el patrón:

    # TÍTULO DEL DOCUMENTO
    **Quick Summary**: ...
    **Keywords**: ...

    ## CHUNK 1: TÍTULO DE SECCIÓN

    SOURCE: ...
    SECTION: ...
    WEEK: ...
    TOKENS: ... (self-contained)

    ### Contenido
    ...
    """
    # --- Header del documento ---
    all_text = " ".join(c.text for c in chunks)
    keywords = _extract_keywords(all_text)
    keywords_str = ", ".join(keywords) if keywords else "SIATA, hidromet, precipitación, Medellín"

    # Genera un resumen a partir del primer chunk
    first_chunk_preview = chunks[0].text[:300].replace("\n", " ").strip() + "..." if chunks else ""

    md_lines = [
        f"# INFORME HIDROMET SEMANAL — SIATA",
        f"Sistema de Alerta Temprana de Medellín (SIATA)",
        f"Semana: {week_start} → {week_end}",
        f"",
        f"**Quick Summary**: {first_chunk_preview}",
        f"",
        f"**Keywords**: {keywords_str}",
        f"",
        "---",
        "",
    ]

    # --- Chunks ---
    for chunk in chunks:
        section_label = chunk.section or "General"
        title = f"CHUNK {chunk.chunk_index}: {section_label.upper()} — PÁGINA {chunk.page}"

        md_lines += [
            f"## {title}",
            f"",
            f"SOURCE: SIATA INFORME HIDROMET SEMANAL",
            f"SECTION: {section_label}",
            f"WEEK: {chunk.week_start} → {chunk.week_end}",
            f"PAGE: {chunk.page}",
            f"ID: {chunk.chunk_id}",
            f"TOKENS: ~{chunk.token_estimate} (self-contained)",
            f"",
        ]

        # Contenido del chunk con subsecciones
        content_lines = chunk.text.splitlines()
        for i, line in enumerate(content_lines):
            line = line.strip()
            if not line:
                md_lines.append("")
            elif i == 0 and len(line) < 80 and line.isupper():
                # Primera línea en mayúsculas = subsección
                md_lines.append(f"### {line.title()}")
            else:
                md_lines.append(line)

        md_lines += ["", "---", ""]

    return "\n".join(md_lines)


def process_pdf(pdf_path: Path) -> list[Chunk]:
    """Procesa un PDF: extrae texto → chunketea → retorna lista de chunks."""
    logger.info(f"Processing {pdf_path.name}...")

    dates = _extract_dates_from_filename(pdf_path.name)
    if not dates:
        logger.warning(f"  Cannot parse dates from {pdf_path.name}, skipping")
        return []

    week_start, week_end = dates
    pages = _extract_pages(pdf_path)
    if not pages:
        logger.warning(f"  No text extracted from {pdf_path.name}")
        return []

    counter = [0]
    all_chunks = []
    for page_num, text in pages:
        chunks = _split_page_into_chunks(
            page_num=page_num,
            text=text,
            source_pdf=pdf_path.name,
            week_start=week_start,
            week_end=week_end,
            chunk_counter=counter,
        )
        all_chunks.extend(chunks)

    logger.info(f"  → {len(all_chunks)} chunks from {len(pages)} pages")
    return all_chunks


def get_recent_pdf_urls(weeks: int) -> list[tuple[str, str]]:
    """Retorna URLs de PDFs de las últimas N semanas."""
    all_pdfs = _fetch_pdf_urls()
    cutoff = datetime.now() - timedelta(weeks=weeks)
    recent = []
    for filename, url in all_pdfs:
        dates = _extract_dates_from_filename(filename)
        if dates:
            try:
                if datetime.strptime(dates[1], "%Y-%m-%d") >= cutoff:
                    recent.append((filename, url))
            except ValueError:
                pass
    logger.info(f"Selected {len(recent)} PDFs from last {weeks} weeks")
    return recent


def run(weeks: int = 4, max_downloads: Optional[int] = None) -> None:
    """
    Pipeline principal: descarga → OCR → chunks → Markdown + JSON.

    Args:
        weeks: Semanas atrás a buscar.
        max_downloads: Límite de PDFs (útil para tests).
    """
    RAW_PDFS_DIR.mkdir(parents=True, exist_ok=True)
    MD_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Obtener URLs
    pdf_urls = get_recent_pdf_urls(weeks)
    if not pdf_urls:
        logger.error("No PDFs found")
        return
    if max_downloads:
        pdf_urls = pdf_urls[:max_downloads]

    # 2. Descargar PDFs
    downloaded = []
    for filename, url in pdf_urls:
        pdf_path = RAW_PDFS_DIR / filename
        if pdf_path.exists():
            logger.info(f"  Already exists: {filename}")
            downloaded.append(pdf_path)
        elif _download_pdf(url, pdf_path):
            downloaded.append(pdf_path)

    logger.info(f"Downloaded {len(downloaded)}/{len(pdf_urls)} PDFs")

    # 3. Procesar PDFs → chunks
    all_chunks: list[Chunk] = []
    chunks_by_pdf: dict[str, list[Chunk]] = {}

    for pdf_path in downloaded:
        chunks = process_pdf(pdf_path)
        if chunks:
            all_chunks.extend(chunks)
            chunks_by_pdf[pdf_path.name] = chunks

    if not all_chunks:
        logger.error("No chunks generated")
        return

    # 4. Guardar Markdown por PDF
    for pdf_name, chunks in chunks_by_pdf.items():
        dates = _extract_dates_from_filename(pdf_name)
        if not dates:
            continue
        week_start, week_end = dates
        md_content = _chunks_to_markdown(chunks, week_start, week_end)

        # Nombre: siata_hidromet_YYYYMMDD_YYYYMMDD.md
        date_tag = f"{week_start.replace('-', '')}_{week_end.replace('-', '')}"
        md_filename = f"{SOURCE_ID}_{date_tag}.md"
        md_path = MD_DIR / md_filename
        md_path.write_text(md_content, encoding="utf-8")
        logger.info(f"  Saved MD: {md_path.name}")

    # 5. Guardar Markdown combinado (todos los PDFs)
    if len(chunks_by_pdf) > 1:
        all_md_lines = [
            f"# SIATA HIDROMET — ARCHIVO COMPLETO ({len(all_chunks)} chunks)",
            f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"Fuente: {SIATA_REPORTE_URL}",
            "",
            "---",
            "",
        ]
        for pdf_name, chunks in chunks_by_pdf.items():
            dates = _extract_dates_from_filename(pdf_name)
            if dates:
                all_md_lines.append(
                    _chunks_to_markdown(chunks, dates[0], dates[1])
                )
        combined_path = MD_DIR / f"{SOURCE_ID}_all.md"
        combined_path.write_text("\n\n".join(all_md_lines), encoding="utf-8")
        logger.info(f"  Saved combined MD: {combined_path.name}")

    # 6. Guardar JSON para ChromaDB
    json_path = SOURCE_DIR / f"{SOURCE_ID}_chunks.json"
    output = {
        "metadata": {
            "source_id": SOURCE_ID,
            "source_name": "SIATA — Informe Hidromet Semanal",
            "source_url": SIATA_REPORTE_URL,
            "processed_at": datetime.now().isoformat(),
            "weeks_lookback": weeks,
            "total_pdfs": len(chunks_by_pdf),
            "total_chunks": len(all_chunks),
        },
        "chunks": [asdict(c) for c in all_chunks],
    }
    json_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    # --- Resumen final ---
    logger.info("=" * 60)
    logger.info(f"DONE — source: {SOURCE_ID}")
    logger.info(f"  PDFs processed : {len(chunks_by_pdf)}")
    logger.info(f"  Total chunks   : {len(all_chunks)}")
    logger.info(f"  Markdown files : {MD_DIR}")
    logger.info(f"  JSON for RAG   : {json_path}")
    logger.info("=" * 60)


if __name__ == "__main__":
    import argparse

    from observability.logging_config import configure_logging

    configure_logging("rag-siata-pdf-chunker")
    parser = argparse.ArgumentParser(description="SIATA HIDROMET PDF Chunker")
    parser.add_argument("--weeks", type=int, default=4, help="Semanas atrás (default: 4)")
    parser.add_argument("--max-downloads", type=int, help="Límite de PDFs (para testing)")
    args = parser.parse_args()

    run(weeks=args.weeks, max_downloads=args.max_downloads)
