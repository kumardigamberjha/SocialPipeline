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
    )

    # ── API Keys ──────────────────────────────────────────────
    nvidia_api_key: str
    groq_api_key: str

    # ── Database ──────────────────────────────────────────────
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_project_link: str = ""
    supabase_publishable_key: str = ""
    supabase_secret_key: str = ""
    supabase_db_connection_string: str = ""
    
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_cluster_endpoint: str = ""
    qdrant_cluster_key: str = ""

    # ── LLM Defaults ─────────────────────────────────────────
    default_provider: str = "nvidia"
    llm_temperature: float = 0.6
    llm_max_tokens: int = 4096
    llm_timeout: int = 300
    ollama_model: str = "ollama/qwen2.5-coder:latest"
    ollama_api_base: str = "http://localhost:11434"

    # ── App ───────────────────────────────────────────────────
    app_name: str = "Wings of AI – Content Pipeline"
    app_version: str = "1.0.0"
    log_level: str = "INFO"
    cors_origins: str = "*"  # comma-separated in prod


@lru_cache()
def get_settings() -> Settings:
    """Return a cached Settings singleton."""
    return Settings()
