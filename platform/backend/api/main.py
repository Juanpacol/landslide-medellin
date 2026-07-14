import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.auth import assert_production_auth
from api.routes import alerts, chat, rain, risk, scraper

# Falla el ARRANQUE (no solo warnings) si ENV=production sin API_TOKEN:
# un despliegue mal configurado no puede quedar con endpoints mutantes abiertos.
assert_production_auth()

app = FastAPI(title="TEYVA API", version="0.1.0")

# CORS restringido por entorno. Definir ALLOWED_ORIGINS como lista separada por
# comas (ej. "https://teyva.co,https://www.teyva.co"). Sin la variable, default
# a frontend local de desarrollo. Nunca usar "*" con allow_credentials=True.
_origins_env = os.getenv("ALLOWED_ORIGINS", "").strip()
_allowed_origins = (
    [o.strip() for o in _origins_env.split(",") if o.strip()]
    if _origins_env
    else ["http://localhost:3000", "http://127.0.0.1:3000"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(risk.router, prefix="/api/risk", tags=["risk"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(scraper.router, prefix="/api/scraper", tags=["scraper"])
app.include_router(rain.router, prefix="/api/rain", tags=["rain"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])


@app.get("/api/geo/communes")
def communes_catalog() -> dict[str, list[dict[str, object]]]:
    """Catálogo del territorio desde la fuente única (domain/communes.py).
    El frontend consume esto en vez de duplicar la lista hardcodeada."""
    from domain.communes import COMMUNES

    return {
        "communes": [
            {
                "id": c.id,
                "official_code": c.official_code,
                "nombre": c.nombre,
                "tipo": c.tipo,
                "is_ladera": c.is_ladera,
            }
            for c in COMMUNES
        ]
    }


@app.get("/")
def root() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
