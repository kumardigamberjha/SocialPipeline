"""
LLM factory – build provider-specific LLM instances and resilient multi-tier fallback cascades.

Supported providers: google (Gemini), nvidia (DeepSeek / NIM), ollama (Cloud & Local), groq, openai, anthropic.
"""

import logging
from typing import Any

import litellm
litellm.cooldown_cache = False
litellm.telemetry = False
litellm.suppress_debug_info = True
litellm.request_timeout = 30  # connection-level timeout; prevents "timed out after None seconds"


class _LiteLLMGeminiWarningFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = str(record.getMessage())
        if "DeprecationWarning" in msg and "Gemini 3+" in msg:
            return False
        return True


logging.getLogger("LiteLLM").addFilter(_LiteLLMGeminiWarningFilter())
logging.getLogger("litellm").addFilter(_LiteLLMGeminiWarningFilter())

from crewai import LLM
from app.config import Settings
from app.provider_tiers import ProviderTier
from app.services.openrouter_client import build_openrouter_llm

logger = logging.getLogger(__name__)


# ── Per-tier wall-clock budgets ───────────────────────────────────────────────
# Measured throughput on this deployment (2026-08):
#   gemini-3.6-flash      fast hosted model
#   gemma4:31b-cloud      ~80 tok/s
#   deepseek-v4-flash     ~8 tok/s  — 65s for a 543-token answer on a 91-token
#                                     prompt, so it needs a genuinely large budget
#   qwen2.5:latest        local, depends on the host
#
# These land on the LLM object as ``llm.timeout`` and are the single source of
# truth for the budget: ``call_llm_with_retry`` reads them back off the object
# rather than keeping a parallel tier→seconds table that could drift.
# These are the historical defaults, kept as module constants because the
# builders below take them as default arguments. The *cascade* reads its
# budgets from Settings (see app/provider_tiers.py), so a deployment can
# retune a tier without touching code; these only apply to direct calls.
GEMINI_TIMEOUT = 75
OLLAMA_CLOUD_TIMEOUT = 60
NVIDIA_TIMEOUT = 120
LOCAL_OLLAMA_TIMEOUT = 90
OPENROUTER_TIMEOUT = 150


def build_gemini_llm(
    settings: Settings,
    temperature: float = 0.4,
    model: str | None = None,
    timeout: int = GEMINI_TIMEOUT,
    max_tokens: int | None = None,
    api_key: str | None = None,
) -> LLM:
    """Build Tier 1 Google Gemini LLM."""
    key = api_key or settings.gemini_api_key
    if not key:
        raise ValueError("Missing gemini_api_key")
    model_name = model or settings.analysis_model or "gemini/gemini-3.6-flash"
    if not model_name.startswith("gemini/"):
        model_name = f"gemini/{model_name}"
    # For Gemini 3 / Gemini 2.5 reasoning models, LiteLLM warns and reasoning can degrade
    # when temperature < 1.0. Use temperature = 1.0 for Gemini 3+ models.
    gemini_temp = 1.0 if ("gemini-3" in model_name or "gemini-2.5" in model_name) else temperature
    kwargs: dict[str, Any] = {
        "model": model_name,
        "api_key": key,
        "temperature": gemini_temp,
        "timeout": timeout,
        # crewai's *native* Gemini provider (GeminiCompletion, on google-genai)
        # supports no timeout at all — it has no such field, so the value above
        # is silently dropped and a hung call holds a thread-pool worker
        # indefinitely. Routing through litellm gives a plain crewai.llm.LLM,
        # which forwards `timeout` on every call and lets the retry helper
        # narrow it to whatever is left of the cascade deadline.
        "is_litellm": True,
    }
    if max_tokens:
        kwargs["max_tokens"] = max_tokens
    return LLM(**kwargs)


def build_nvidia_llm(
    settings: Settings,
    temperature: float = 0.4,
    model: str | None = None,
    timeout: int = NVIDIA_TIMEOUT,
    max_tokens: int | None = None,
) -> LLM:
    """Build NVIDIA NIM / DeepSeek AI LLM."""
    if not settings.nvidia_api_key:
        raise ValueError("Missing nvidia_api_key")
    model_name = model or settings.nvidia_deepseek_model or settings.analysis_fallback_model or "nvidia_nim/deepseek-ai/deepseek-v4-flash-0731"
    if not model_name.startswith("nvidia_nim/"):
        model_name = f"nvidia_nim/{model_name}"
    return LLM(
        model=model_name,
        api_key=settings.nvidia_api_key,
        temperature=temperature,
        # DeepSeek is a reasoning model at ~8 tok/s here; a 16k ceiling invites a
        # chain-of-thought no budget can absorb. Keep the answer short.
        max_tokens=max_tokens or settings.llm_max_tokens,
        timeout=timeout,
    )


def build_ollama_cloud_llm(
    settings: Settings,
    temperature: float = 0.4,
    model: str | None = None,
    timeout: int = OLLAMA_CLOUD_TIMEOUT,
    max_tokens: int | None = None,
) -> LLM:
    """
    Build the Ollama Cloud LLM.

    Note this points at ``settings.ollama_api_base`` — the same host as the local
    tier. In the default setup that is the local Ollama daemon proxying
    ``gemma4:31b-cloud`` through to ollama.com, so the cloud and local tiers share
    a single point of failure: if the daemon is down, both go down together.
    """
    model_name = model or getattr(settings, "ollama_cloud_model", "ollama/gemma4:31b-cloud")
    if not model_name.startswith("ollama/"):
        model_name = f"ollama/{model_name}"
    kwargs: dict[str, Any] = {
        "model": model_name,
        "base_url": settings.ollama_api_base,
        "temperature": temperature,
        "timeout": timeout,
    }
    if max_tokens:
        kwargs["max_tokens"] = max_tokens
    if getattr(settings, "ollama_cloud_api_key", None):
        kwargs["api_key"] = settings.ollama_cloud_api_key
    return LLM(**kwargs)


def build_local_ollama_llm(
    settings: Settings,
    temperature: float = 0.4,
    model: str | None = None,
    timeout: int = LOCAL_OLLAMA_TIMEOUT,
    max_tokens: int | None = None,
) -> LLM:
    """Build the local Ollama LLM (qwen2.5:latest) — the last-resort tier."""
    model_name = model or getattr(settings, "local_ollama_model", "ollama/qwen2.5:latest")
    if not model_name.startswith("ollama/"):
        model_name = f"ollama/{model_name}"
    kwargs: dict[str, Any] = {
        "model": model_name,
        "base_url": settings.ollama_api_base,
        "temperature": temperature,
        "timeout": timeout,
    }
    if max_tokens:
        kwargs["max_tokens"] = max_tokens
    return LLM(**kwargs)


# Cooldown-map keys observed at build time, keyed by tier. Lets /api/health
# report which tiers are currently parked for quota without instantiating the
# whole cascade on every 30s poll — and without this module having to
# reimplement the provider-specific model-string normalisation that crewai
# applies (it strips the "ollama/" prefix, for instance).
_TIER_COOLDOWN_KEYS: dict[str, str] = {}


_TIER_BUILDERS = {
    "gemini": lambda settings, tier, temperature, max_tokens: build_gemini_llm(
        settings,
        temperature=temperature,
        model=tier.model(settings),
        timeout=tier.timeout(settings),
        max_tokens=max_tokens,
        api_key=tier.api_key(settings),
    ),
    "openrouter": lambda settings, tier, temperature, max_tokens: build_openrouter_llm(
        settings,
        temperature=temperature,
        model=tier.model(settings),
        timeout=tier.timeout(settings),
        max_tokens=max_tokens,
    ),
    "ollama_cloud": lambda settings, tier, temperature, max_tokens: build_ollama_cloud_llm(
        settings,
        temperature=temperature,
        model=tier.model(settings),
        timeout=tier.timeout(settings),
        max_tokens=max_tokens,
    ),
    "ollama_local": lambda settings, tier, temperature, max_tokens: build_local_ollama_llm(
        settings,
        temperature=temperature,
        model=tier.model(settings),
        timeout=tier.timeout(settings),
        max_tokens=max_tokens,
    ),
}


def build_tier_cascade(
    settings: Settings,
    temperature: float = 0.4,
    max_tokens: int | None = None,
    chain: tuple[ProviderTier, ...] | None = None,
) -> list[tuple[ProviderTier, Any]]:
    """Instantiate the ordered provider chain from ``chain`` or ``settings.provider_chain``."""
    max_tokens = max_tokens or settings.llm_max_tokens
    built: list[tuple[ProviderTier, Any]] = []
    tiers = chain if chain is not None else settings.provider_chain

    for tier in tiers:
        if not tier.is_configured(settings):
            logger.warning(
                "LLM cascade: skipping %s — not configured (model=%r, key=%s)",
                tier.name,
                tier.model(settings),
                "set" if tier.api_key(settings) else "missing",
            )
            continue
        builder = _TIER_BUILDERS.get(tier.builder)
        if builder is None:
            logger.warning("LLM cascade: %s has unknown builder %r", tier.name, tier.builder)
            continue
        try:
            llm = builder(settings, tier, temperature, max_tokens)
        except Exception as exc:
            logger.warning("LLM cascade: could not build %s: %s", tier.name, exc)
            continue
        # The tier travels with the object. Everything downstream — retry
        # classification, the `used` stamp, the export gate — reads it from here.
        try:
            llm.provider_tier = tier
        except Exception:  # pragma: no cover - defensive, for slotted LLM classes
            logger.debug("Could not stamp provider_tier onto %s", tier.name)
        try:
            from app.services.blog_pipeline.utils import _llm_key

            _TIER_COOLDOWN_KEYS[tier.key] = _llm_key(llm)
        except Exception:  # pragma: no cover - health reporting is optional
            logger.debug("Could not record cooldown key for %s", tier.name)
        built.append((tier, llm))

    if not built:
        raise RuntimeError(
            "No LLM tier could be built. Check GEMINI_PAID_API_KEY / GEMINI_API_KEY "
            "and OLLAMA_API_BASE."
        )
    return built


def build_fallback_cascade(
    settings: Settings,
    temperature: float = 0.4,
    max_tokens: int | None = None,
    is_audit: bool = False,
) -> tuple[Any, list[tuple[str, Any]]]:
    """The analysis cascade, as ``(primary_llm, [(tier_name, llm), ...])``."""
    chain = settings.audit_provider_chain if is_audit else settings.provider_chain
    built = build_tier_cascade(settings, temperature=temperature, max_tokens=max_tokens, chain=chain)
    primary_tier, primary_llm = built[0]
    if not primary_tier.is_client_grade:
        logger.warning(
            "LLM cascade: no client-grade tier is available; starting at %s. "
            "Audits produced now will be marked internal_only and blocked from export.",
            primary_tier.name,
        )
    return primary_llm, [(tier.name, llm) for tier, llm in built[1:]]


def build_llm(provider: str, settings: Settings) -> Any:
    """
    Build and return a CrewAI LLM instance for the given provider.

    Args:
        provider: One of "ollama", "nvidia", "groq", "openai", "anthropic", "google", "ollama_cloud", "ollama_local".
        settings: Application settings instance.

    Returns:
        A configured CrewAI LLM object with an Ollama fallback.
    """
    provider = provider.lower().strip()
    
    # Always create the local Ollama LLM for fallback
    local_ollama_llm = build_local_ollama_llm(settings, temperature=settings.llm_temperature)

    if provider in ("ollama", "ollama_local", "local"):
        logger.info("Building LLM  ▸ provider=local_ollama  model=%s  base=%s", settings.local_ollama_model, settings.ollama_api_base)
        return local_ollama_llm
    elif provider == "ollama_cloud":
        logger.info("Building LLM  ▸ provider=ollama_cloud  model=%s  base=%s", settings.ollama_cloud_model, settings.ollama_api_base)
        return build_ollama_cloud_llm(settings, temperature=settings.llm_temperature)

    primary_llm = None
    try:
        if provider == "openai":
            if not settings.openai_api_key:
                raise ValueError("Missing openai_api_key")
            primary_llm = LLM(model="gpt-4o", api_key=settings.openai_api_key, temperature=settings.llm_temperature)
            logger.info("Building LLM  ▸ provider=openai  model=gpt-4o")
        elif provider == "anthropic":
            if not settings.anthropic_api_key:
                raise ValueError("Missing anthropic_api_key")
            primary_llm = LLM(model="anthropic/claude-3-5-sonnet-latest", api_key=settings.anthropic_api_key, temperature=settings.llm_temperature)
            logger.info("Building LLM  ▸ provider=anthropic  model=claude-3-5-sonnet-latest")
        elif provider in ("google", "gemini"):
            primary_llm = build_gemini_llm(settings, temperature=settings.llm_temperature)
            logger.info("Building LLM  ▸ provider=google  model=%s", settings.analysis_model)
        elif provider == "groq":
            if not settings.groq_api_key:
                raise ValueError("Missing groq_api_key")
            primary_llm = LLM(model="groq/llama-3.3-70b-versatile", api_key=settings.groq_api_key, temperature=settings.llm_temperature)
            logger.info("Building LLM  ▸ provider=groq  model=llama-3.3-70b-versatile")
        elif provider == "nemotron":
            primary_llm = LLM(
                model="ollama/nemotron-3-ultra:cloud",
                base_url=settings.ollama_api_base,
                temperature=settings.llm_temperature,
                max_tokens=16384
            )
            logger.info("Building LLM  ▸ provider=nemotron  model=ollama/nemotron-3-ultra:cloud  base=%s  context=256k", settings.ollama_api_base)
        elif provider in ("nvidia", "deepseek"):
            primary_llm = build_nvidia_llm(settings, temperature=settings.llm_temperature)
            logger.info("Building LLM  ▸ provider=nvidia  model=%s", settings.nvidia_deepseek_model)
        else:
            logger.warning(f"Unknown LLM provider '{provider}', falling back to local ollama.")
            return local_ollama_llm

        # Return primary model
        return primary_llm

    except Exception as e:
        logger.warning(f"Failed to initialize primary provider '{provider}' ({e}). Falling back to local ollama.")
        return local_ollama_llm


def describe_chain(settings: Settings) -> list[dict]:
    """The cascade as data, for /api/health and the dashboard tier indicator.

    Deliberately does no network I/O and builds no LLM objects: this is polled
    every 30 seconds. Cooldown state comes from keys recorded the last time the
    cascade was actually built, so a tier that has never been built reports
    ``cooling_for = None`` rather than a confident zero.
    """
    from app.services.blog_pipeline.utils import cooldown_remaining_for_key

    rows: list[dict] = []
    for tier in settings.provider_chain:
        configured = tier.is_configured(settings)
        cooldown_key = _TIER_COOLDOWN_KEYS.get(tier.key)
        cooling = cooldown_remaining_for_key(cooldown_key) if cooldown_key else None
        rows.append(
            {
                "index": tier.index,
                "key": tier.key,
                "name": tier.name,
                "grade": tier.grade,
                "model": tier.model(settings),
                "configured": configured,
                "cooling_for": round(cooling) if cooling else (0 if cooling == 0 else None),
                "available": configured and not cooling,
            }
        )
    return rows


def active_tier(settings: Settings) -> dict | None:
    """The tier the next analysis call would land on, or None if none can serve.

    This is what makes a silent degradation visible *before* somebody finds it in
    a PDF: if this reports an internal_only tier, every audit generated right now
    is going to be blocked from export.
    """
    for row in describe_chain(settings):
        if row["available"]:
            return row
    return None
