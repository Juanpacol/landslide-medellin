"""Centralized environment-variable settings (pydantic-settings)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed access to env vars; real environment always wins over .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # db/session.py
    DATABASE_URL: str | None = None
    DATABASE_URL_SYNC: str | None = None
    DB_SSL: bool = False

    # api/auth.py, api/main.py
    API_TOKEN: str | None = None
    API_TOKEN_VIEWER: str | None = None
    ENV: str | None = None
    ENVIRONMENT: str | None = None
    ALLOWED_ORIGINS: str = ""

    # alerts/slack.py, alerts/slack_media.py, alerts/reports.py
    SLACK_WEBHOOK_URL: str | None = None
    SLACK_BOT_TOKEN: str | None = None
    SLACK_CHANNEL_ID: str | None = None
    DASHBOARD_URL: str = "http://localhost:3000"
    CHART_BASE_URL: str = "http://localhost:8000"
    ANTHROPIC_MODEL: str = "claude-haiku-4-5"
    ANTHROPIC_API_KEY: str = ""

    # agent/chat.py, agent/chat_rag.py, agent/risk_explanations.py
    LLM_PROVIDER: str = "anthropic"
    OLLAMA_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2"
    RAG_CHAT_MODEL: str | None = None
    RAG_MAX_TOOL_ROUNDS: int = 3

    # rag/chroma_store.py, integrations/agent_contracts.py
    ENABLE_RAG: bool = True
    RAG_EMBED_MODEL: str = "paraphrase-multilingual-MiniLM-L12-v2"


settings = Settings()
