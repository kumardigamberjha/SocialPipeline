"""
LLM factory – build provider-specific LLM instances.

Supported providers: ollama, nvidia, groq.

IMPORTANT: To prevent CrewAI / LiteLLM from ever falling back to
OpenAI, this module sets OPENAI_API_KEY to a dummy value at import
time.  This ensures no real OpenAI call can succeed even if some
internal path bypasses our explicit LLM object.
"""

import logging
import os

from crewai import LLM

from app.config import Settings

logger = logging.getLogger(__name__)

# ── Kill the OpenAI fallback at import time ──────────────────────────────────
# CrewAI / LiteLLM will try the default OpenAI client when OPENAI_API_KEY is
# set in the environment.  We overwrite it with a dummy so that if anything
# somehow bypasses our explicit LLM, it fails loudly against a fake key
# rather than silently calling OpenAI.
os.environ["OPENAI_API_KEY"] = "sk-no-openai-intended"
# Removed OPENAI_API_BASE dead-end because it breaks OpenAI-compatible endpoints (Groq, Nvidia)
# os.environ["OPENAI_API_BASE"] = "http://localhost:0"

# ── Provider registry ────────────────────────────────────────────────────────

_PROVIDER_CONFIG = {
    "nvidia": {
        "model": "nvidia_nim/stepfun-ai/step-3.5-flash",
        "api_base": "https://integrate.api.nvidia.com/v1",
    },
    "groq": {
        "model": "groq/llama-3.3-70b-versatile",
        "api_base": "https://api.groq.com/openai/v1",
    },
}

_API_KEY_MAP = {
    "nvidia": "nvidia_api_key",
    "groq": "groq_api_key",
}


def build_llm(provider: str, settings: Settings) -> LLM:
    """
    Build and return an LLM instance for the given provider.

    Args:
        provider: One of "ollama", "nvidia", or "groq".
        settings: Application settings instance.

    Returns:
        A configured crewai.LLM object.

    Raises:
        ValueError: If the provider is not supported.
    """
    provider = provider.lower().strip()

    if provider == "ollama":
        # LiteLLM format: "ollama/<model>" routes to the Ollama REST API.
        model = settings.ollama_model
        api_base = settings.ollama_api_base

        logger.info("Building LLM  ▸ provider=ollama  model=%s  base=%s", model, api_base)

        return LLM(
            model=model,
            base_url=api_base,
            api_key="ollama",          # dummy – Ollama needs no key
            temperature=0.0,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.llm_timeout,
        )

    if provider not in _PROVIDER_CONFIG:
        raise ValueError(
            f"Unsupported LLM provider '{provider}'. "
            f"Choose from: ollama, {', '.join(_PROVIDER_CONFIG.keys())}"
        )

    config = _PROVIDER_CONFIG[provider]
    model = config["model"]
    api_base = config["api_base"]
    api_key = getattr(settings, _API_KEY_MAP[provider])

    logger.info("Building LLM  ▸ provider=%s  model=%s", provider, model)

    return LLM(
        model=model,
        api_key=api_key,
        base_url=api_base,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        timeout=settings.llm_timeout,
    )
