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

from app.provider_tiers import ProviderTier, resolve_chain

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
    # Second key, tried only when the primary fails for a reason another key can
    # actually fix — quota exhausted, or the key itself rejected. Quota on the
    # free tier is per project, so a second key is a second daily allowance.
    # Note `extra="ignore"` above: without this field the env var is dropped
    # silently rather than raising, which is why it appeared to do nothing.
    gemini_backup_api_key: str | None = None
    gemma_api_key: str | None = None
    ollama_cloud_api_key: str | None = None
    # Tier 3 of the analysis cascade. This lived in app/.env with no field to
    # receive it, so `extra="ignore"` above silently discarded it — the exact
    # trap the gemini_backup_api_key comment warns about.
    openrouter_api_key: str | None = None
    meta_access_token: str | None = None
    instagram_app_id: str | None = None
    instagram_app_secret: str | None = None
    instagram_redirect_uri: str = "http://localhost:8000/api/instagram/oauth/callback"
    instagram_token_expires_at: str | None = None

    # ── Database ──────────────────────────────────────────────
    # Postgres. The API uses the async (asyncpg) engine; Celery workers use the
    # sync (psycopg) one derived from the same URL by _sync_database_url().
    database_url: str = "postgresql+asyncpg://nexus:nexus@localhost:5432/nexus"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    # ── Auth / sessions ───────────────────────────────────────
    secret_key: str = _PLACEHOLDER_SECRET_KEY
    jwt_algorithm: str = "HS256"
    # Access tokens are deliberately short-lived: revocation is enforced by a
    # Redis denylist that only has to outlive a single access token.
    access_token_ttl_seconds: int = 900          # 15 minutes
    refresh_token_ttl_seconds: int = 2592000     # 30 days, absolute (not sliding)
    # Minimum signup password length. Below 12 the bcrypt work factor is doing
    # all the work; above it the entropy is.
    password_min_length: int = 12

    # ── Email / SMTP ──────────────────────────────────────────
    # Gmail: use an App Password (16-char) from
    # https://myaccount.google.com/apppasswords — not your account password.
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""           # e.g. you@gmail.com
    smtp_password: str = ""       # Gmail App Password
    smtp_from: str = ""           # defaults to smtp_user when empty

    # How long a verification OTP is valid (seconds). 600 = 10 minutes.
    email_verify_otp_ttl_seconds: int = 600

    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_cluster_endpoint: str = ""
    qdrant_cluster_key: str = ""

    # ── LLM Defaults ─────────────────────────────────────────
    default_provider: Literal["nvidia", "groq", "ollama", "openai", "anthropic", "google", "gemma"] = "ollama"
    llm_temperature: float = 0.6
    llm_max_tokens: int = 4096
    # Wall-clock ceiling for a whole LLM fallback cascade, not one call.
    # Must stay under Cloudflare's ~100s proxy timeout: the analysis endpoints
    # run the cascade synchronously inside the request handler.
    llm_timeout: int = 120
    ollama_model: str = "ollama/gemma4:31b-cloud"
    # Local Ollama model (used as the last priority local fallback)
    local_ollama_model: str = "ollama/qwen2.5:latest"
    # Ollama cloud model (3rd priority fallback)
    ollama_cloud_model: str = "ollama/gemma4:31b-cloud"
    # Tiers 1 and 2 of the analysis cascade: Google Gemini on two keys.
    analysis_model: str = "gemini/gemini-3.6-flash"
    ollama_analysis_model: str = "gemini/gemini-3.6-flash"
    # 2nd priority fallback: NVIDIA DeepSeek AI (NVIDIA NIM)
    nvidia_deepseek_model: str = "nvidia_nim/deepseek-ai/deepseek-v4-flash-0731"
    analysis_fallback_model: str = "nvidia_nim/deepseek-ai/deepseek-v4-flash-0731"
    # Kept as a config knob; no longer wired into the analysis cascade — this
    # model does not hold the JSON schema these prompts require.
    nvidia_fallback_model: str = "nvidia_nim/meta/llama-3.1-8b-instruct"
    # Model behind default_provider="nvidia". Must exist in NVIDIA's catalog:
    # https://integrate.api.nvidia.com/v1/models
    nvidia_model: str = "nvidia_nim/deepseek-ai/deepseek-v4-flash-0731"
    ollama_api_base: str = "http://localhost:11434"
    openai_api_base: str = ""

    # ── OpenRouter (analysis cascade tier 3) ──────────────────────────
    openrouter_api_base: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    # Optional attribution headers OpenRouter surfaces on its dashboard.
    openrouter_referer: str = ""
    openrouter_title: str = "Content Creator"

    # ── Per-tier wall-clock budgets ───────────────────────────────────
    # Each lands on the LLM object as ``llm.timeout``; call_llm_with_retry
    # reads it back off the object rather than keeping a parallel table.
    # Measured on this deployment: gemma4:31b-cloud ~80 tok/s, and the free
    # Nemotron tier is a large reasoning model that streams slowly, so it
    # needs a genuinely wide budget or it fails 100% of the time.
    gemini_tier_timeout: int = 75
    openrouter_timeout: int = 150
    ollama_cloud_tier_timeout: int = 60
    local_ollama_tier_timeout: int = 90

    # Comma-separated provider_tiers keys, to reorder or shorten the analysis
    # cascade without a code change. Empty means DEFAULT_PROVIDER_CHAIN.
    llm_provider_chain: str = ""
    # Ceiling for the whole audit cascade. Wider than llm_timeout because a
    # strict cascade retries each tier before advancing (3 attempts on a
    # transient fault), and the audit runs on a background-friendly path
    # rather than behind the Cloudflare proxy timeout.
    audit_llm_timeout: int = 300

    # ── YouTube competitor tracking ───────────────────────────────────────
    # The weekly Sunday sync refreshes at most this many approved competitors
    # per user (stalest-first — see sync_queries.select_competitors_for_weekly_sync),
    # each up to this many latest videos. Bounds the per-user quota spend to
    # roughly cap * 3 units/week regardless of how many competitors are tracked.
    competitor_weekly_sync_cap: int = 50
    competitor_weekly_video_limit: int = 10

    # ── Redis / Celery ───────────────────────────────────────
    # Two physical instances, deliberately. The cache runs allkeys-lru; the
    # state/broker instance runs noeviction. Auth denylist entries and queued
    # task payloads must never be evictable — an evicted denylist entry
    # silently *un-revokes* a token.
    #
    # These are explicit rather than derived. The previous code built the
    # result backend by string-munging redis_url, which produced an invalid
    # URL for anything not ending in "/0" (redis://h:6379/2 -> .../2/1).
    redis_cache_url: str = "redis://localhost:6379/0"       # analytics/AI caches
    redis_state_url: str = "redis://localhost:6380/2"       # denylist, WS tickets, job pubsub
    celery_broker_url: str = "redis://localhost:6380/0"
    celery_result_backend: str = "redis://localhost:6380/1"

    # Run pipelines in-process via BackgroundTasks when no Celery worker is
    # consuming the queue. A developer convenience; refused in production,
    # where an unqueued multi-minute job would block an API worker.
    allow_inprocess_fallback: bool = True

    # DEPRECATED: single-instance Redis URL. Still read by the call sites that
    # have not yet moved to app.core.redis_client; removed once they have.
    redis_url: str = "redis://localhost:6379/0"

    # ── Stripe Billing ───────────────────────────────────────
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_pro_price_id: str = ""
    stripe_enterprise_price_id: str = ""

    # ── ComfyUI (retired — image generation now runs on Gemini) ──
    # Kept commented rather than deleted so the local-GPU path is one revert
    # away; see app/services/comfy_client.py.
    # comfy_host: str = "127.0.0.1"
    # comfy_port: int = 8188

    # ── Image generation (Gemini) ────────────────────────────
    # Model id for image renders. NOTE: image generation needs an *image*
    # model — the "-image" suffix is not optional, and the text models in
    # `analysis_model` above cannot return image parts.
    #   gemini-3.1-flash-image       versatile default
    #   gemini-3.1-flash-lite-image  fastest / cheapest (1K only)
    #   gemini-3-pro-image           highest fidelity, legible text
    gemini_image_model: str = "gemini-3.1-flash-image"
    # 4:5 is the Instagram portrait ratio the prompt engine is tuned for.
    gemini_image_aspect_ratio: str = "4:5"
    gemini_image_size: str = "2K"      # "512" | "1K" | "2K" | "4K"
    gemini_image_timeout: int = 120

    # Where rendered images are written. The default is the Next.js public dir,
    # which makes them reachable at /generated_posts/<file> in local dev where
    # the API and the dashboard share a checkout. Under docker-compose they are
    # separate containers with no shared mount, so the API serves the files back
    # itself (GET /api/plans/{plan}/items/{item}/image) and this should point at
    # a mounted volume instead.
    image_output_dir: str = str(
        Path(__file__).resolve().parent.parent / "dashboard" / "public" / "generated_posts"
    )
    # DEPRECATED: the ComfyUI-era name for image_output_dir. Deployments (and
    # docker-compose) still set COMFY_OUTPUT_DIR; the validator below mirrors it
    # so an existing volume mount does not silently start writing elsewhere.
    comfy_output_dir: str = ""

    # ── Google Calendar (planner) ────────────────────────────
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/google/callback"
    # Fernet key for encrypting stored OAuth tokens (Google *and* Instagram).
    # No default on purpose — generate one with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # GOOGLE_TOKEN_ENCRYPTION_KEY is the historical name and still works; see
    # the validator below, which mirrors whichever one is set.
    token_encryption_key: str = ""
    google_token_encryption_key: str = ""
    # Previous keys, newest first. Set after rotating so MultiFernet can still
    # decrypt ciphertext written under the old key. Comma-separated.
    token_encryption_previous_keys: str = ""
    frontend_url: str = "http://localhost:3000"
    default_timezone: str = "Asia/Kolkata"

    # ── App ───────────────────────────────────────────────────
    app_name: str = "Wings of AI – Content Pipeline"
    app_version: str = "1.0.0"
    report_brand_name: str = "Growth Intelligence"
    log_level: str = "INFO"
    cors_origins: str = "*"  # comma-separated in prod

    # ── Derived helpers ───────────────────────────────────────

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def sync_database_url(self) -> str:
        """The same database over psycopg, for Celery workers.

        Workers are synchronous; handing them the asyncpg engine would mean an
        ``asyncio.run()`` per task and a fresh event loop per connection.
        """
        return self.database_url.replace("+asyncpg", "+psycopg")

    @property
    def cookie_secure(self) -> bool:
        """Secure cookies everywhere except plain-http local development."""
        return self.is_production

    @property
    def cookie_prefix(self) -> str:
        """``__Host-`` in production, bare names in development.

        The ``__Host-`` prefix is the strongest binding a cookie can have (exact
        host, no Domain, Path=/, Secure) but the browser rejects it over plain
        http, which is what localhost serves.
        """
        return "__Host-" if self.is_production else ""

    @property
    def resolved_token_encryption_key(self) -> str:
        """TOKEN_ENCRYPTION_KEY, falling back to the historical Google name."""
        return self.token_encryption_key or self.google_token_encryption_key

    @property
    def previous_encryption_keys(self) -> list[str]:
        return [
            k.strip()
            for k in self.token_encryption_previous_keys.split(",")
            if k.strip()
        ]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def provider_chain(self) -> tuple["ProviderTier", ...]:
        """The ordered analysis cascade, including tiers that are not configured.

        Unconfigured tiers are kept so that a tier index means the same provider
        in every log line and health payload; the builder skips them.
        """
        return resolve_chain(self.llm_provider_chain)

    @property
    def usable_provider_chain(self) -> tuple["ProviderTier", ...]:
        """Only the tiers that can actually be attempted right now."""
        return tuple(t for t in self.provider_chain if t.is_configured(self))

    @model_validator(mode="after")
    def _mirror_encryption_key_aliases(self) -> "Settings":
        """Keep the old and new encryption-key names in sync.

        Existing deployments set GOOGLE_TOKEN_ENCRYPTION_KEY. The key now
        protects Instagram tokens too, so the setting was renamed — but silently
        dropping the old name would make every stored Google credential
        undecryptable, forcing a reconnect.
        """
        resolved = self.token_encryption_key or self.google_token_encryption_key
        if resolved:
            object.__setattr__(self, "token_encryption_key", resolved)
            object.__setattr__(self, "google_token_encryption_key", resolved)
        return self

    @model_validator(mode="after")
    def _mirror_image_output_dir_alias(self) -> "Settings":
        """Honour the pre-Gemini COMFY_OUTPUT_DIR name.

        The setting outlived ComfyUI itself — it is just "where renders land" —
        so an environment that still sets the old name keeps pointing at the
        same mounted volume instead of falling back to the in-repo default.
        """
        resolved = self.comfy_output_dir or self.image_output_dir
        object.__setattr__(self, "image_output_dir", resolved)
        object.__setattr__(self, "comfy_output_dir", resolved)
        return self

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
        if self.google_client_id and not self.resolved_token_encryption_key:
            problems.append(
                "TOKEN_ENCRYPTION_KEY must be set when Google OAuth is configured"
            )

        # Sessions are cookie-based. Without a real signing key, a forged access
        # token is accepted; without Secure cookies over the tunnel, the session
        # travels in cleartext to anything on the path.
        if self.database_url.startswith("sqlite"):
            problems.append("DATABASE_URL still points at SQLite")
        if "postgresql+asyncpg" not in self.database_url:
            problems.append("DATABASE_URL must use the postgresql+asyncpg driver")

        # An in-process fallback runs a multi-minute pipeline inside an API
        # worker. Behind Cloudflare's ~100s proxy timeout that is a guaranteed
        # 524 *and* a blocked worker.
        if self.allow_inprocess_fallback:
            problems.append(
                "ALLOW_INPROCESS_FALLBACK must be false in production; "
                "run a Celery worker for every queue instead"
            )

        # Without a configured client-grade tier every audit is internal_only,
        # so the export gate refuses all of them and the product silently has
        # no deliverable. That is a config error, not a runtime condition.
        if not any(t.is_client_grade and t.is_configured(self) for t in self.provider_chain):
            problems.append(
                "no client-grade LLM tier is configured (set GEMINI_API_KEY or "
                "GEMINI_BACKUP_API_KEY); every audit would be blocked from export"
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
