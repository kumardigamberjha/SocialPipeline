"""
LLM factory – build provider-specific LLM instances.

Supported providers: nvidia, groq.
"""

import logging

from crewai import LLM

from app.config import Settings

logger = logging.getLogger(__name__)

# ── Provider registry ────────────────────────────────────────────────────────

_PROVIDER_CONFIG = {
    "nvidia": {
        "model": "qwen/qwen3.5-122b-a10b",
        "api_base": "https://integrate.api.nvidia.com/v1",
    },
    "groq": {
        "model": "llama-3.3-70b-versatile",
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
        provider: One of "nvidia" or "groq".
        settings: Application settings instance.

    Returns:
        A configured crewai.LLM object.

    Raises:
        ValueError: If the provider is not supported.
    """
    provider = provider.lower().strip()

    if provider not in _PROVIDER_CONFIG:
        raise ValueError(
            f"Unsupported LLM provider '{provider}'. "
            f"Choose from: {list(_PROVIDER_CONFIG.keys())}"
        )

    config = _PROVIDER_CONFIG[provider]
    api_key = getattr(settings, _API_KEY_MAP[provider])

    logger.info("Building LLM  ▸ provider=%s  model=%s", provider, config["model"])

    return LLM(
        model=config["model"],
        api_key=api_key,
        api_base=config["api_base"],
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        timeout=settings.llm_timeout,
    )
