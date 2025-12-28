# backend/services/llm_provider.py
"""
LLM provider abstraction for the Fessi agent.
Supports multiple LLM providers (OpenAI, Anthropic) with environment-based configuration.
"""

import os
import logging
from typing import Optional
from langchain_core.language_models.chat_models import BaseChatModel

logger = logging.getLogger(__name__)

# Supported providers
PROVIDER_OPENAI = "openai"
PROVIDER_ANTHROPIC = "anthropic"

# Default models per provider
DEFAULT_MODELS = {
    PROVIDER_OPENAI: "gpt-4o-mini",
    PROVIDER_ANTHROPIC: "claude-3-haiku-20240307"
}


def get_llm(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0,
    **kwargs
) -> BaseChatModel:
    """
    Get a configured LLM instance based on environment or explicit settings.

    The provider is determined in the following order:
    1. Explicit `provider` parameter
    2. LLM_PROVIDER environment variable
    3. Auto-detect based on available API keys

    Args:
        provider: LLM provider name ("openai" or "anthropic").
        model: Model name to use. Defaults to provider-specific default.
        temperature: Temperature for generation (0-1). Defaults to 0 for deterministic output.
        **kwargs: Additional arguments passed to the LLM constructor.

    Returns:
        Configured LLM instance.

    Raises:
        ValueError: If provider is unknown or required API key is missing.
    """
    # Determine provider
    provider = provider or os.getenv("LLM_PROVIDER")

    # Auto-detect provider based on available API keys
    if not provider:
        if os.getenv("OPENAI_API_KEY"):
            provider = PROVIDER_OPENAI
            logger.info("Auto-detected OpenAI provider from API key")
        elif os.getenv("ANTHROPIC_API_KEY"):
            provider = PROVIDER_ANTHROPIC
            logger.info("Auto-detected Anthropic provider from API key")
        else:
            raise ValueError(
                "No LLM provider configured. Set LLM_PROVIDER environment variable "
                "or provide OPENAI_API_KEY or ANTHROPIC_API_KEY."
            )

    provider = provider.lower()

    if provider == PROVIDER_OPENAI:
        return _get_openai_llm(model, temperature, **kwargs)
    elif provider == PROVIDER_ANTHROPIC:
        return _get_anthropic_llm(model, temperature, **kwargs)
    else:
        raise ValueError(
            f"Unknown LLM provider: {provider}. "
            f"Supported providers: {PROVIDER_OPENAI}, {PROVIDER_ANTHROPIC}"
        )


def _get_openai_llm(
    model: Optional[str] = None,
    temperature: float = 0,
    **kwargs
) -> BaseChatModel:
    """
    Get an OpenAI LLM instance.

    Args:
        model: Model name. Defaults to OPENAI_MODEL env var or gpt-4o-mini.
        temperature: Temperature for generation.
        **kwargs: Additional arguments.

    Returns:
        Configured ChatOpenAI instance.
    """
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        raise ImportError(
            "langchain-openai is required for OpenAI provider. "
            "Install it with: pip install langchain-openai"
        )

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY environment variable is required for OpenAI provider."
        )

    base_url = os.getenv("OPENAI_BASE_URL")
    model = model or os.getenv("OPENAI_MODEL", DEFAULT_MODELS[PROVIDER_OPENAI])

    # Import timeout from config
    from ..config import LLM_TIMEOUT

    logger.info(f"Initializing OpenAI LLM with model: {model}, timeout={LLM_TIMEOUT}s")
    if base_url:
        logger.info(f"Using custom OpenAI base URL: {base_url}")

    return ChatOpenAI(
        model=model,
        temperature=temperature,
        api_key=api_key,
        base_url=base_url,
        request_timeout=LLM_TIMEOUT,
        **kwargs
    )


def _get_anthropic_llm(
    model: Optional[str] = None,
    temperature: float = 0,
    **kwargs
) -> BaseChatModel:
    """
    Get an Anthropic LLM instance.

    Args:
        model: Model name. Defaults to ANTHROPIC_MODEL env var or claude-3-haiku.
        temperature: Temperature for generation.
        **kwargs: Additional arguments.

    Returns:
        Configured ChatAnthropic instance.
    """
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError:
        raise ImportError(
            "langchain-anthropic is required for Anthropic provider. "
            "Install it with: pip install langchain-anthropic"
        )

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY environment variable is required for Anthropic provider."
        )

    model = model or os.getenv("ANTHROPIC_MODEL", DEFAULT_MODELS[PROVIDER_ANTHROPIC])

    logger.info(f"Initializing Anthropic LLM with model: {model}")

    return ChatAnthropic(
        model=model,
        temperature=temperature,
        api_key=api_key,
        **kwargs
    )


def get_available_providers() -> list[str]:
    """
    Get a list of providers that have API keys configured.

    Returns:
        List of available provider names.
    """
    available = []

    if os.getenv("OPENAI_API_KEY"):
        available.append(PROVIDER_OPENAI)
    if os.getenv("ANTHROPIC_API_KEY"):
        available.append(PROVIDER_ANTHROPIC)

    return available


def is_provider_available(provider: str) -> bool:
    """
    Check if a specific provider is available (has API key configured).

    Args:
        provider: Provider name to check.

    Returns:
        True if provider is available, False otherwise.
    """
    provider = provider.lower()

    if provider == PROVIDER_OPENAI:
        return bool(os.getenv("OPENAI_API_KEY"))
    elif provider == PROVIDER_ANTHROPIC:
        return bool(os.getenv("ANTHROPIC_API_KEY"))
    else:
        return False
