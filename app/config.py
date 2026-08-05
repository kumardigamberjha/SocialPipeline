"""
Centralized configuration via Pydantic Settings.

Loads values from environment variables and the `.env` file automatically.
Use `get_settings()` to access the singleton instance.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Insecure placeholder shipped in source. Refused in production by
# _reject_insecure_production_config below.
_PLACEHOLDER_SECRET_KEY = "change-this-to-a-random-64-char-string-in-production"


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        # Absolute, so the file resolves no matter what the process CWD is. A
        # relative "app/.env" silently loaded *nothing* when uvicorn was started
        # from anywhere but the repo root, falling back to every default below
        # — including the placeholder JWT signing key.
        env_file=Path(__file__).resolve().parent / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Environment ───────────────────────────────────────────
    environment: Literal["development", "production"] = "development"

    # ── API Keys ──────────────────────────────────────────────
    nvidia_api_key: str | None = None
    groq_api_key: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None
    gemma_api_key: str | None = None
    ollama_cloud_api_key: str | None = None
    meta_access_token: str | None = None

    # ── Database ──────────────────────────────────────────────
    sqlite_db_path: str = "./data/nexus.db"
    secret_key: str = _PLACEHOLDER_SECRET_KEY
    jwt_algorithm: str = "HS256"
    jwt_expire_days: int = 30
    
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_cluster_endpoint: str = ""
    qdrant_cluster_key: str = ""

    # ── LLM Defaults ─────────────────────────────────────────
    default_provider: Literal["nvidia", "groq", "ollama", "openai", "anthropic", "google", "gemma"] = "ollama"
    llm_temperature: float = 0.6
    llm_max_tokens: int = 4096
    llm_timeout: int = 300
    ollama_model: str = "ollama/mistral:latest"
    # Model used for the YouTube AI analysis feature (local Ollama qwen).
    ollama_analysis_model: str = "ollama/qwen2.5:latest"
    ollama_api_base: str = "http://host.docker.internal:11434"
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

    # ── Google Calendar (planner) ────────────────────────────
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/google/callback"
    # Fernet key for encrypting stored OAuth tokens. No default on purpose —
    # generate one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    google_token_encryption_key: str = ""
    frontend_url: str = "http://localhost:3000"
    default_timezone: str = "Asia/Kolkata"

    # ── App ───────────────────────────────────────────────────
    app_name: str = "Wings of AI – Content Pipeline"
    app_version: str = "1.0.0"
    log_level: str = "INFO"
    cors_origins: str = "*"  # comma-separated in prod

    @model_validator(mode="after")
    def _reject_insecure_production_config(self) -> "Settings":
        """Fail fast rather than serve production traffic with dev defaults.

        Previously nothing checked that the placeholder signing key had been
        overridden, so a misresolved .env path (or a forgotten variable) meant
        every JWT was signed with a value published in the source tree.
        """
        if self.environment != "production":
            return self

        problems: list[str] = []
        if self.secret_key == _PLACEHOLDER_SECRET_KEY:
            problems.append("SECRET_KEY is still the placeholder from source control")
        elif len(self.secret_key) < 32:
            problems.append("SECRET_KEY is shorter than 32 characters")
        if "*" in self.cors_origins:
            problems.append("CORS_ORIGINS must list explicit origins, not '*'")
        if self.google_client_id and not self.google_token_encryption_key:
            problems.append(
                "GOOGLE_TOKEN_ENCRYPTION_KEY must be set when Google OAuth is configured"
            )

        if problems:
            raise ValueError(
                "Refusing to start with ENVIRONMENT=production:\n  - "
                + "\n  - ".join(problems)
            )
        return self


@lru_cache()
def get_settings() -> Settings:
    """Return a cached Settings singleton."""
    return Settings()
