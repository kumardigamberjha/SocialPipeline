"""
LLM factory – build provider-specific LLM instances and resilient multi-tier fallback cascades.

Supported providers: google (Gemini), nvidia (DeepSeek / NIM), ollama (Cloud & Local), groq, openai, anthropic.
"""

import logging
from typing import Any

from crewai import LLM
from app.config import Settings

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
GEMINI_TIMEOUT = 45
OLLAMA_CLOUD_TIMEOUT = 60
NVIDIA_TIMEOUT = 120
LOCAL_OLLAMA_TIMEOUT = 90


def build_gemini_llm(
    settings: Settings,
    temperature: float = 0.4,
    model: str | None = None,
    timeout: int = GEMINI_TIMEOUT,
    max_tokens: int | None = None,
) -> LLM:
    """Build Tier 1 Google Gemini LLM."""
    if not settings.gemini_api_key:
        raise ValueError("Missing gemini_api_key")
    model_name = model or settings.analysis_model or "gemini/gemini-3.6-flash"
    if not model_name.startswith("gemini/"):
        model_name = f"gemini/{model_name}"
    kwargs: dict[str, Any] = {
        "model": model_name,
        "api_key": settings.gemini_api_key,
        "temperature": temperature,
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


def build_fallback_cascade(
    settings: Settings,
    temperature: float = 0.4,
    max_tokens: int | None = None,
) -> tuple[LLM, list[tuple[str, LLM]]]:
    """
    Build the 4-tier LLM fallback cascade, ordered by *measured* throughput:
      1. Primary: Google Gemini Flash
      2. Tier 2: Ollama Cloud (gemma4:31b-cloud)  — ~80 tok/s
      3. Tier 3: NVIDIA NIM (DeepSeek AI)         — ~8 tok/s, needs a big budget
      4. Tier 4: Local Ollama (qwen2.5:latest)

    ``max_tokens`` applies to every tier; it used to be accepted and silently
    ignored here, which is how the NVIDIA tiers ended up hardcoded at 16384.

    Returns (primary_llm, [(tier_name, fallback_llm), ...])
    """
    max_tokens = max_tokens or settings.llm_max_tokens

    # Tier 4 (always available locally if Ollama is running)
    local_ollama = build_local_ollama_llm(settings, temperature=temperature, max_tokens=max_tokens)

    # Tier 2: Ollama Cloud
    try:
        ollama_cloud = build_ollama_cloud_llm(settings, temperature=temperature, max_tokens=max_tokens)
    except Exception as e:
        logger.warning("Could not build Ollama Cloud LLM: %s", e)
        ollama_cloud = None

    # Tier 3: NVIDIA NIM (DeepSeek AI)
    nvidia_deepseek = None
    if settings.nvidia_api_key:
        try:
            nvidia_deepseek = build_nvidia_llm(settings, temperature=temperature, max_tokens=max_tokens)
        except Exception as e:
            logger.warning("Could not build NVIDIA DeepSeek LLM: %s", e)

    # Build ordered fallback chain: fastest healthy provider first.
    fallback_chain: list[tuple[str, LLM]] = []
    if ollama_cloud is not None:
        fallback_chain.append(("Tier 2: Ollama Cloud", ollama_cloud))
    if nvidia_deepseek is not None:
        fallback_chain.append(("Tier 3: NVIDIA DeepSeek", nvidia_deepseek))
    fallback_chain.append(("Tier 4: Local Ollama (qwen2.5:latest)", local_ollama))

    # Tier 1: Primary Gemini
    try:
        gemini_llm = build_gemini_llm(settings, temperature=temperature, max_tokens=max_tokens)
        return gemini_llm, fallback_chain
    except Exception as e:
        logger.warning("Could not initialize Tier 1 Gemini LLM (%s); promoting the next tier to primary", e)
        if fallback_chain:
            _first_name, first_llm = fallback_chain[0]
            return first_llm, fallback_chain[1:]
        return local_ollama, []



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

