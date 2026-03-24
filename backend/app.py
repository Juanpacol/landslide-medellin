"""
API FastAPI — Sistema de Análisis de Riesgo de Deslizamientos, Medellín
Ejecutar: uvicorn app:app --reload --port 8000
"""

import json
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

app = FastAPI(title="Medellín Landslide Risk API")

# CORS para desarrollo local
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Archivos estáticos
app.mount("/static", StaticFiles(directory="static"), name="static")

# ---------------------------------------------------------------------------
# Cliente Supabase (None si no está configurado)
# ---------------------------------------------------------------------------

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    from supabase import create_client
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def _supabase_unavailable():
    return JSONResponse(
        status_code=503,
        content={"error": "Supabase no configurado"},
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
def serve_index():
    return FileResponse("static/index.html")


@app.get("/api/export/geojson")
def export_geojson():
    if supabase is None:
        return _supabase_unavailable()

    result = supabase.table("communes").select(
        "commune_id, nombre_comuna, categoria_riesgo, indice_riesgo, n_eventos, is_zona_ladera, geometry"
    ).execute()

    features = []
    for row in result.data or []:
        geom_raw = row.get("geometry")
        try:
            geometry = json.loads(geom_raw) if isinstance(geom_raw, str) else geom_raw
        except (json.JSONDecodeError, TypeError):
            geometry = None

        features.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": {
                "commune_id": row.get("commune_id"),
                "nombre_comuna": row.get("nombre_comuna"),
                "categoria_riesgo": row.get("categoria_riesgo"),
                "indice_riesgo": row.get("indice_riesgo"),
                "n_eventos": row.get("n_eventos"),
                "is_zona_ladera": row.get("is_zona_ladera"),
            },
        })

    return {"type": "FeatureCollection", "features": features}


@app.get("/api/events")
def get_events(
    commune_id: str | None = Query(default=None),
    fecha_inicio: str | None = Query(default=None),
    fecha_fin: str | None = Query(default=None),
):
    if supabase is None:
        return _supabase_unavailable()

    query = supabase.table("events").select("*")

    if commune_id:
        query = query.eq("commune_id", commune_id)
    if fecha_inicio:
        query = query.gte("fecha", fecha_inicio)
    if fecha_fin:
        query = query.lte("fecha", fecha_fin)

    result = query.execute()
    return result.data or []


@app.get("/api/alerts")
def get_alerts():
    if supabase is None:
        return _supabase_unavailable()

    result = supabase.table("alerts").select(
        "id, commune_id, nivel, precipitacion_valor, tipo_umbral, timestamp, communes(nombre_comuna)"
    ).execute()
    alerts = result.data or []

    output = []
    for a in alerts:
        communes_data = a.get("communes") or {}
        output.append({
            "id": a.get("id"),
            "commune_id": a.get("commune_id"),
            "nombre_comuna": communes_data.get("nombre_comuna", a.get("commune_id")),
            "nivel": a.get("nivel"),
            "precipitacion_7d": a.get("precipitacion_valor"),
            "n_eventos_recientes": None,
            "fecha_alerta": a.get("timestamp"),
        })

    order = {"Rojo": 0, "Naranja": 1}
    output.sort(key=lambda a: order.get(a.get("nivel", ""), 99))

    return output


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
