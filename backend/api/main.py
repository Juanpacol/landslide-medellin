from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import chat, risk, scraper

app = FastAPI(title="TEYVA API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(risk.router, prefix="/api/risk", tags=["risk"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(scraper.router, prefix="/api/scraper", tags=["scraper"])


@app.get("/")
def root() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
