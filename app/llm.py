"""
LLM factory – build provider-specific LLM instances.

Supported providers: ollama, nvidia, groq, openai, anthropic, google.
"""

import logging
from typing import Any

from crewai import LLM
from app.config import Settings

logger = logging.getLogger(__name__)


def build_llm(provider: str, settings: Settings) -> Any:
    """
    Build and return a CrewAI LLM instance for the given provider.

    Args:
        provider: One of "ollama", "nvidia", "groq", "openai", "anthropic", "google".
        settings: Application settings instance.

    Returns:
        A configured CrewAI LLM object with an Ollama fallback.
    """
    provider = provider.lower().strip()
    
    # Always create the local Ollama LLM for fallback
    ollama_llm = LLM(
        model="ollama/qwen2.5-coder:latest",
        base_url=settings.ollama_api_base,
        temperature=settings.llm_temperature,
    )

    if provider == "ollama":
        logger.info("Building LLM  ▸ provider=ollama  model=qwen2.5-coder:latest  base=%s", settings.ollama_api_base)
        return ollama_llm

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
        elif provider == "google":
            if not settings.gemini_api_key:
                raise ValueError("Missing gemini_api_key")
            primary_llm = LLM(model="gemini/gemini-3.5-flash", api_key=settings.gemini_api_key, temperature=settings.llm_temperature)
            logger.info("Building LLM  ▸ provider=google  model=gemini-3.5-flash")
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
        elif provider == "nvidia":
            if not settings.nvidia_api_key:
                raise ValueError("Missing nvidia_api_key")
            primary_llm = LLM(model="nvidia/stepfun-ai/step-3.5-flash", api_key=settings.nvidia_api_key, temperature=settings.llm_temperature)
            logger.info("Building LLM  ▸ provider=nvidia  model=stepfun-ai/step-3.5-flash")
        else:
            logger.warning(f"Unknown LLM provider '{provider}', falling back to ollama.")
            return ollama_llm

        # Return primary model
        return primary_llm

    except Exception as e:
        logger.warning(f"Failed to initialize primary provider '{provider}' ({e}). Falling back to ollama.")
        return ollama_llm
