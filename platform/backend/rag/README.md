# RAG Module - SIATA PDF Chunker

Módulo de **Retrieval-Augmented Generation** para procesar reportes HIDROMET de SIATA y preparar datos para el chatbot.

## Fase 1: Chunking (Actual)

Este módulo descarga reportes semanales PDF de SIATA, extrae texto via OCR, y los divide en chunks manteniendo contexto temporal y de sección.

### Instalación de dependencias

```bash
cd platform/backend
pip install pdfplumber
# O reinstala todo:
pip install -r requirements.txt
```

### Uso

```bash
cd platform/backend
export PYTHONPATH=.

# Descarga y procesa últimos 4 semanas (default)
python -m rag.siata_pdf_chunker

# Últimas 12 semanas
python -m rag.siata_pdf_chunker --weeks 12

# Output personalizado
python -m rag.siata_pdf_chunker --weeks 4 --output /ruta/custom_chunks.json

# Testing con 2 PDFs solamente (para validar)
python -m rag.siata_pdf_chunker --weeks 4 --max-downloads 2
```

### Output

Genera `rag/data/chunks.json` con estructura:

```json
{
  "metadata": {
    "source": "SIATA HIDROMET",
    "processed_at": "2026-06-29T12:34:56.789...",
    "total_chunks": 1243,
    "weeks_lookback": 4
  },
  "chunks": [
    {
      "text": "Semana del 15 al 21 de junio...",
      "source_pdf": "HIDROMET_20260615_20260621.pdf",
      "week_start": "2026-06-15",
      "week_end": "2026-06-21",
      "page": 3,
      "section": "Precipitación"
    },
    ...
  ]
}
```

### Características

✅ Descarga inteligente (no re-descarga si ya existe)
✅ OCR robusto con pdfplumber
✅ Chunking por secciones + tamaño limitado
✅ Detección automática de secciones (Precipitación, Análisis, etc.)
✅ Metadatos temporales (semana exacta de cada chunk)
✅ Manejo de errores y reintentos

### Estructura

```
rag/
├── __init__.py
├── siata_pdf_chunker.py       # Script principal
├── README.md                   # Este archivo
└── data/
    ├── raw_pdfs/              # PDFs descargados (ignorado en git)
    └── chunks.json            # Output: chunks procesados
```

## Fase 2: ChromaDB + Embeddings (Próxima)

Una vez validado que los chunks están bien:

1. Instalar ChromaDB
2. Generar embeddings (Ollama local o modelo pequeño)
3. Ingestar chunks en ChromaDB
4. Conectar con `agent/chat.py`

## Próximos Pasos

- [ ] Probar con `--max-downloads 2` para validar
- [ ] Revisar calidad de chunks en `chunks.json`
- [ ] Escalar a 12+ semanas si se ve bien
- [ ] Implementar ChromaDB consumer en `agent/chat.py`
