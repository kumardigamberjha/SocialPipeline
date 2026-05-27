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
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── API Keys ──────────────────────────────────────────────
    nvidia_api_key: str = ""
    groq_api_key: str = ""

    # ── LLM Defaults ─────────────────────────────────────────
    default_provider: str = "nvidia"
    llm_temperature: float = 0.6
    llm_max_tokens: int = 2048
    llm_timeout: int = 60

    # ── App ───────────────────────────────────────────────────
    app_name: str = "Agent SaaS Platform"
    app_version: str = "1.0.0"
    log_level: str = "INFO"
    cors_origins: str = "*"  # comma-separated in prod

    # ── Database & Memory ─────────────────────────────────────
    supabase_url: str = ""
    supabase_key: str = ""
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    
    # ── Additional API Keys ───────────────────────────────────
    openai_api_key: str = ""
    openai_api_base: str = ""



@lru_cache()
def get_settings() -> Settings:
    """Return a cached Settings singleton."""
    return Settings()
