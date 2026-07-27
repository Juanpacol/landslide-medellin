"""
SIATA Geotecnia Chunker — Hojas de Vida de Deslizamientos

Descarga fichas técnicas geotécnicas por zona de deslizamiento,
extrae texto, limpia encoding y chunketea por sección.

Output:
    rag/data/siata_geotecnia/
    ├── raw_pdfs/                              # PDFs descargados
    ├── md/
    │   ├── siata_geotecnia_villatina.md      # Markdown por zona
    │   └── siata_geotecnia_all.md            # Markdown combinado
    └── siata_geotecnia_chunks.json           # JSON para ChromaDB

Uso:
    python -m rag.siata_geotecnia_chunker
    python -m rag.siata_geotecnia_chunker --zones Villatina Pajarito   # solo algunas
    python -m rag.siata_geotecnia_chunker --test                       # solo Olaya_Herrera
"""

import json
import logging
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import pdfplumber
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# --- Paths ---
RAG_DIR = Path(__file__).parent
SOURCE_ID = "siata_geotecnia"
SOURCE_DIR = RAG_DIR / "data" / SOURCE_ID
RAW_PDFS_DIR = SOURCE_DIR / "raw_pdfs"
MD_DIR = SOURCE_DIR / "md"

# --- URLs ---
GEOTECNIA_URL = "https://siata.gov.co/geotecnia/HV_Deslizamientos/"

CHUNK_SIZE = 1200  # caracteres máx por chunk

# Secciones conocidas en Hojas de Vida geotécnicas SIATA
SECTION_MAP = {
    "UBICACIÓN": "Ubicación del Sitio",
    "UBICACION": "Ubicación del Sitio",
    "DESCRIPCIÓN DEL SITIO": "Descripción del Sitio",
    "DESCRIPCION DEL SITIO": "Descripción del Sitio",
    "CARACTERÍSTICAS DEL MOVIMIENTO": "Características del Movimiento en Masa",
    "CARACTERISTICAS DEL MOVIMIENTO": "Características del Movimiento en Masa",
    "HISTORIA": "Historia de Eventos",
    "ANTECEDENTES": "Antecedentes Históricos",
    "GEOLOGÍA": "Geología",
    "GEOLOGIA": "Geología",
    "GEOMORFOLOGÍA": "Geomorfología",
    "GEOMORFOLOGIA": "Geomorfología",
    "INSTRUMENTACIÓN": "Instrumentación y Monitoreo",
    "INSTRUMENTACION": "Instrumentación y Monitoreo",
    "MONITOREO": "Instrumentación y Monitoreo",
    "ESQUEMA DE MONITOREO": "Instrumentación y Monitoreo",
    "INFORMES EMITIDOS": "Informes Técnicos Emitidos",
    "INFORMES": "Informes Técnicos Emitidos",
    "MEDIDAS DE MITIGACIÓN": "Medidas de Mitigación",
    "MEDIDAS DE MITIGACION": "Medidas de Mitigación",
    "PARÁMETROS": "Parámetros Geotécnicos",
    "PARAMETROS": "Parámetros Geotécnicos",
    "SENSORES": "Sensores Instalados",
    "DRONES": "Monitoreo con Drones",
    "SOBREVUELOS": "Monitoreo con Drones",
}


@dataclass
class Chunk:
    chunk_id: str
    text: str
    source_id: str  # "siata_geotecnia"
    source_pdf: str  # "HV_Villatina.pdf"
    zone_name: str  # "Villatina"
    zone_slug: str  # "villatina"
    municipio: str  # "Medellín" (extraído del PDF)
    barrio: str  # "Olaya Herrera, occidente de Medellín"
    lat: Optional[float]
    lon: Optional[float]
    page: int
    section: str
    chunk_index: int
    token_estimate: int


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _fix_encoding(text: str) -> str:
    """
    Corrige artefactos de encoding de PDFs en español.
    pdfplumber a veces separa el acento del caracter: 'a´ → 'á', '´ı → 'í'
    """
    fixes = {
        # minúsculas
        "a´": "á",
        "e´": "é",
        "ı´": "í",
        "o´": "ó",
        "u´": "ú",
        "´a": "á",
        "´e": "é",
        "´ı": "í",
        "´o": "ó",
        "´u": "ú",
        "a¨": "ä",
        "u¨": "ü",
        "˜n": "ñ",
        "n˜": "ñ",
        # mayúsculas
        "A´": "Á",
        "E´": "É",
        "I´": "Í",
        "O´": "Ó",
        "U´": "Ú",
        "´A": "Á",
        "´E": "É",
        "´I": "Í",
        "´O": "Ó",
        "´U": "Ú",
        "˜N": "Ñ",
    }
    for bad, good in fixes.items():
        text = text.replace(bad, good)
    return text


def _slug(name: str) -> str:
    """'HV_Olaya_Herrera.pdf' → 'olaya_herrera'"""
    name = re.sub(r"^HV_", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\.pdf$", "", name, flags=re.IGNORECASE)
    return name.lower()


def _zone_display_name(slug: str) -> str:
    """'olaya_herrera' → 'Olaya Herrera'"""
    return slug.replace("_", " ").title()


def _extract_metadata_from_text(text: str) -> dict:
    """
    Extrae municipio, barrio, latitud y longitud de la página 1.
    Los PDFs tienen líneas como:
        Municipio: Medellín
        Barrio/Vereda: Olaya Herrera, occidente de Medellín
        Latitud: 6.273625
        Longitud: -75.611854
    """
    meta = {"municipio": "Medellín", "barrio": "", "lat": None, "lon": None}
    for line in text.splitlines():
        line = line.strip()
        if line.lower().startswith("municipio:"):
            meta["municipio"] = line.split(":", 1)[1].strip()
        elif line.lower().startswith("barrio") or line.lower().startswith("vereda"):
            meta["barrio"] = line.split(":", 1)[1].strip() if ":" in line else ""
        elif line.lower().startswith("latitud:"):
            try:
                meta["lat"] = float(line.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif line.lower().startswith("longitud:"):
            try:
                meta["lon"] = float(line.split(":", 1)[1].strip())
            except ValueError:
                pass
    return meta


def _detect_section(text: str) -> str:
    """Detecta sección geotécnica del chunk por encabezados."""
    text_upper = text.upper()
    for key, label in SECTION_MAP.items():
        if key in text_upper:
            return label
    return "Información General"


def _fetch_pdf_urls() -> list[tuple[str, str]]:
    """Scrapea directorio y retorna [(filename, url)]."""
    try:
        resp = requests.get(GEOTECNIA_URL, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Error fetching geotecnia directory: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    return [
        (link.get_text(strip=True), urljoin(GEOTECNIA_URL, link.get("href")))
        for link in soup.find_all("a")
        if link.get_text(strip=True).endswith(".pdf")
    ]


def _download_pdf(url: str, output_path: Path, max_retries: int = 3) -> bool:
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, timeout=120)
            resp.raise_for_status()
            output_path.write_bytes(resp.content)
            logger.info(f"  ↓ {output_path.name} ({len(resp.content) / 1024 / 1024:.1f} MB)")
            return True
        except Exception as e:
            logger.warning(f"  Attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2**attempt)
    return False


def _extract_pages(pdf_path: Path) -> list[tuple[int, str]]:
    pages = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                raw = page.extract_text() or ""
                text = _fix_encoding(raw).strip()
                if text:
                    pages.append((i, text))
                else:
                    logger.warning(f"  Page {i}: no text (likely image-only)")
    except Exception as e:
        logger.error(f"Error reading {pdf_path.name}: {e}")
    return pages


def _split_page_into_chunks(
    page_num: int,
    text: str,
    source_pdf: str,
    zone_slug: str,
    zone_name: str,
    municipio: str,
    barrio: str,
    lat: Optional[float],
    lon: Optional[float],
    chunk_counter: list[int],
) -> list[Chunk]:
    section = _detect_section(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    paragraphs = text.split("\n\n")

    chunks = []
    current_text = ""

    def _flush(text_block: str) -> None:
        text_block = text_block.strip()
        if not text_block:
            return
        chunk_counter[0] += 1
        idx = chunk_counter[0]
        chunks.append(
            Chunk(
                chunk_id=f"{SOURCE_ID}_{zone_slug}_p{page_num}_c{idx}",
                text=text_block,
                source_id=SOURCE_ID,
                source_pdf=source_pdf,
                zone_name=zone_name,
                zone_slug=zone_slug,
                municipio=municipio,
                barrio=barrio,
                lat=lat,
                lon=lon,
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


def _chunks_to_markdown(
    chunks: list[Chunk],
    zone_name: str,
    municipio: str,
    barrio: str,
    lat: Optional[float],
    lon: Optional[float],
) -> str:
    all_text = " ".join(c.text for c in chunks)
    keywords = [
        kw
        for kw in [
            "deslizamiento",
            "movimiento en masa",
            "geotécnica",
            "ladera",
            "monitoreo",
            "sensor",
            "riesgo",
            "evacuación",
            "geología",
            "instrumentación",
            "SIATA",
            "Medellín",
        ]
        if kw.lower() in all_text.lower()
    ]

    coords_str = f"Lat: {lat}, Lon: {lon}" if lat and lon else "Coordenadas no disponibles"
    first_preview = chunks[0].text[:300].replace("\n", " ").strip() + "..." if chunks else ""

    md_lines = [
        f"# HOJA DE VIDA — DESLIZAMIENTO: {zone_name.upper()}",
        "SIATA — Sistema de Alerta Temprana de Medellín",
        f"Zona: {zone_name} | Municipio: {municipio}",
        f"Barrio/Vereda: {barrio}",
        f"Coordenadas: {coords_str}",
        "",
        f"**Quick Summary**: {first_preview}",
        "",
        f"**Keywords**: {', '.join(keywords) if keywords else 'deslizamiento, geotécnica, SIATA, Medellín'}",
        "",
        "---",
        "",
    ]

    for chunk in chunks:
        title = f"CHUNK {chunk.chunk_index}: {chunk.section.upper()} — PÁGINA {chunk.page}"
        md_lines += [
            f"## {title}",
            "",
            "SOURCE: SIATA — Hoja de Vida de Deslizamiento",
            f"ZONE: {chunk.zone_name}",
            f"MUNICIPIO: {chunk.municipio}",
            f"SECTION: {chunk.section}",
            f"PAGE: {chunk.page}",
            f"ID: {chunk.chunk_id}",
            f"TOKENS: ~{chunk.token_estimate} (self-contained)",
            "",
        ]

        content_lines = chunk.text.splitlines()
        for i, line in enumerate(content_lines):
            line = line.strip()
            if not line:
                md_lines.append("")
            elif i == 0 and len(line) < 80 and line.isupper():
                md_lines.append(f"### {line.title()}")
            else:
                md_lines.append(line)

        md_lines += ["", "---", ""]

    return "\n".join(md_lines)


def process_pdf(pdf_path: Path) -> list[Chunk]:
    logger.info(f"Processing {pdf_path.name}...")

    zone_slug = _slug(pdf_path.name)
    zone_name = _zone_display_name(zone_slug)

    pages = _extract_pages(pdf_path)
    if not pages:
        logger.warning("  No text extracted — likely image-only PDF")
        return []

    # Extrae metadatos de la primera página
    meta = _extract_metadata_from_text(pages[0][1])
    municipio = meta["municipio"]
    barrio = meta["barrio"]
    lat = meta["lat"]
    lon = meta["lon"]

    logger.info(f"  Zone: {zone_name} | {municipio} | {barrio} | {lat},{lon}")

    counter = [0]
    all_chunks = []
    for page_num, text in pages:
        chunks = _split_page_into_chunks(
            page_num=page_num,
            text=text,
            source_pdf=pdf_path.name,
            zone_slug=zone_slug,
            zone_name=zone_name,
            municipio=municipio,
            barrio=barrio,
            lat=lat,
            lon=lon,
            chunk_counter=counter,
        )
        all_chunks.extend(chunks)

    logger.info(f"  → {len(all_chunks)} chunks from {len(pages)} pages")
    return all_chunks


def run(zones: Optional[list[str]] = None, test: bool = False) -> None:
    """
    Pipeline principal: descarga → OCR → chunks → Markdown + JSON.

    Args:
        zones: Lista de nombres de zonas a procesar (None = todas).
               Ej: ['Villatina', 'Pajarito']
        test: Si True, solo procesa HV_Olaya_Herrera.pdf (el más pequeño).
    """
    RAW_PDFS_DIR.mkdir(parents=True, exist_ok=True)
    MD_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Obtener lista de PDFs
    all_pdf_urls = _fetch_pdf_urls()
    if not all_pdf_urls:
        logger.error("No PDFs found in geotecnia directory")
        return

    # Filtra si se especificaron zonas o modo test
    if test:
        all_pdf_urls = [(f, u) for f, u in all_pdf_urls if "Olaya_Herrera" in f]
        logger.info("TEST MODE — only Olaya Herrera")
    elif zones:
        filter_slugs = {z.lower().replace(" ", "_") for z in zones}
        all_pdf_urls = [(f, u) for f, u in all_pdf_urls if _slug(f) in filter_slugs]
        logger.info(f"Filtered to {len(all_pdf_urls)} zones: {zones}")

    logger.info(f"Processing {len(all_pdf_urls)} PDFs")

    # 2. Descargar PDFs
    downloaded = []
    for filename, url in all_pdf_urls:
        pdf_path = RAW_PDFS_DIR / filename
        if pdf_path.exists():
            logger.info(f"  Already exists: {filename}")
            downloaded.append(pdf_path)
        elif _download_pdf(url, pdf_path):
            downloaded.append(pdf_path)

    logger.info(f"Downloaded {len(downloaded)}/{len(all_pdf_urls)} PDFs")

    # 3. Procesar PDFs → chunks
    all_chunks: list[Chunk] = []
    chunks_by_zone: dict[str, list[Chunk]] = {}

    for pdf_path in downloaded:
        chunks = process_pdf(pdf_path)
        if chunks:
            all_chunks.extend(chunks)
            chunks_by_zone[chunks[0].zone_slug] = chunks

    if not all_chunks:
        logger.error("No chunks generated — PDFs may be image-only")
        return

    # 4. Markdown por zona
    for zone_slug, chunks in chunks_by_zone.items():
        c0 = chunks[0]
        md_content = _chunks_to_markdown(
            chunks=chunks,
            zone_name=c0.zone_name,
            municipio=c0.municipio,
            barrio=c0.barrio,
            lat=c0.lat,
            lon=c0.lon,
        )
        md_path = MD_DIR / f"{SOURCE_ID}_{zone_slug}.md"
        md_path.write_text(md_content, encoding="utf-8")
        logger.info(f"  Saved MD: {md_path.name}")

    # 5. Markdown combinado
    if len(chunks_by_zone) > 1:
        header = "\n".join(
            [
                f"# SIATA GEOTECNIA — HOJAS DE VIDA DE DESLIZAMIENTOS ({len(all_chunks)} chunks)",
                f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                f"Fuente: {GEOTECNIA_URL}",
                f"Zonas: {', '.join(_zone_display_name(s) for s in chunks_by_zone)}",
                "",
                "---",
                "",
            ]
        )
        sections = []
        for _zone_slug, chunks in chunks_by_zone.items():
            c0 = chunks[0]
            sections.append(
                _chunks_to_markdown(chunks, c0.zone_name, c0.municipio, c0.barrio, c0.lat, c0.lon)
            )
        combined_path = MD_DIR / f"{SOURCE_ID}_all.md"
        combined_path.write_text(header + "\n\n".join(sections), encoding="utf-8")
        logger.info(f"  Saved combined MD: {combined_path.name}")

    # 6. JSON para ChromaDB
    json_path = SOURCE_DIR / f"{SOURCE_ID}_chunks.json"
    output = {
        "metadata": {
            "source_id": SOURCE_ID,
            "source_name": "SIATA — Hojas de Vida de Deslizamientos",
            "source_url": GEOTECNIA_URL,
            "processed_at": datetime.now().isoformat(),
            "total_zones": len(chunks_by_zone),
            "zones": list(chunks_by_zone.keys()),
            "total_chunks": len(all_chunks),
        },
        "chunks": [asdict(c) for c in all_chunks],
    }
    json_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    logger.info("=" * 60)
    logger.info(f"DONE — source: {SOURCE_ID}")
    logger.info(f"  Zones processed : {len(chunks_by_zone)}")
    logger.info(f"  Total chunks    : {len(all_chunks)}")
    logger.info(f"  Markdown files  : {MD_DIR}")
    logger.info(f"  JSON for RAG    : {json_path}")
    logger.info("=" * 60)


if __name__ == "__main__":
    import argparse

    from observability.logging_config import configure_logging

    configure_logging("rag-siata-geotecnia-chunker")
    parser = argparse.ArgumentParser(description="SIATA Geotecnia PDF Chunker")
    parser.add_argument("--zones", nargs="+", help="Zonas específicas (ej: Villatina Pajarito)")
    parser.add_argument(
        "--test", action="store_true", help="Solo procesa Olaya Herrera (más pequeño)"
    )
    args = parser.parse_args()

    run(zones=args.zones, test=args.test)
