"""
Centralized configuration via Pydantic Settings.

Loads values from environment variables and the `.env` file automatically.
Use `get_settings()` to access the singleton instance.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file="app/.env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── API Keys ──────────────────────────────────────────────
    nvidia_api_key: str = ""
    groq_api_key: str = ""

    # ── Database ──────────────────────────────────────────────
    sqlite_db_path: str = "./data/nexus.db"
    secret_key: str = "change-this-to-a-random-64-char-string-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_days: int = 30
    
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_cluster_endpoint: str = ""
    qdrant_cluster_key: str = ""

    # ── LLM Defaults ─────────────────────────────────────────
    default_provider: str = "ollama"
    llm_temperature: float = 0.6
    llm_max_tokens: int = 4096
    llm_timeout: int = 300
    ollama_model: str = "ollama/mistral:latest"
    ollama_api_base: str = "http://host.docker.internal:11434"
    openai_api_key: str = ""
    openai_api_base: str = ""

    # ── Redis / Celery ───────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Stripe Billing ───────────────────────────────────────
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_pro_price_id: str = ""
    stripe_enterprise_price_id: str = ""

    # ── ComfyUI ──────────────────────────────────────────────
    comfy_host: str = "127.0.0.1"
    comfy_port: int = 8188

    # ── App ───────────────────────────────────────────────────
    app_name: str = "Wings of AI – Content Pipeline"
    app_version: str = "1.0.0"
    log_level: str = "INFO"
    cors_origins: str = "*"  # comma-separated in prod


@lru_cache()
def get_settings() -> Settings:
    """Return a cached Settings singleton."""
    return Settings()
