"""
SDK clients for a ModelConfig.

OpenAI-compatible providers get an AsyncOpenAI client, Anthropic gets an
AsyncAnthropic client. Both use the provider's base URL, API key and default
headers from the config, and LLM_TIMEOUT as the request timeout.

The key and the base URL are always passed explicitly: given None, the SDKs
fall back to OPENAI_API_KEY / ANTHROPIC_API_KEY and OPENAI_BASE_URL /
ANTHROPIC_BASE_URL, which could send one provider's key to another provider.

get_client() reuses clients (and their connection pools) per provider account
and event loop; create_client() always builds a new one.
"""
import asyncio
import logging
from collections import OrderedDict
from typing import Union

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from ..config import LLM_TIMEOUT
from .types import KIND_ANTHROPIC, KIND_OPENAI_COMPATIBLE, ModelConfig

log = logging.getLogger(__name__)

# Base URLs for configs without one (ModelConfig.base_url None = the provider's public API)
OPENAI_DEFAULT_BASE_URL = "https://api.openai.com/v1"
ANTHROPIC_DEFAULT_BASE_URL = "https://api.anthropic.com"

# Sent when a config has no key (local servers need none, the SDKs require one)
PLACEHOLDER_API_KEY = "not-needed"

# Clients kept for reuse; the oldest is dropped beyond this number
MAX_CACHED_CLIENTS = 16
_clients: "OrderedDict[tuple, Union[AsyncOpenAI, AsyncAnthropic]]" = OrderedDict()


class ModelConfigError(ValueError):
    """The model config cannot be used to build a client (unknown provider kind)."""


def create_openai_client(config: ModelConfig) -> AsyncOpenAI:
    """
    Build an AsyncOpenAI client for an OpenAI-compatible provider.

    Local servers (llama.cpp, vLLM) often need no key, but the SDK requires one,
    so a placeholder is sent when the config has none.
    """
    base_url = config.base_url or OPENAI_DEFAULT_BASE_URL
    log.debug(f"Creating OpenAI client for {config.provider_name}: base_url={base_url}")
    return AsyncOpenAI(
        api_key=config.api_key or PLACEHOLDER_API_KEY,
        base_url=base_url,
        default_headers=config.default_headers or None,
        timeout=LLM_TIMEOUT,
    )


def create_anthropic_client(config: ModelConfig) -> AsyncAnthropic:
    """
    Build an AsyncAnthropic client.

    An explicit api_key also keeps the SDK from reading ANTHROPIC_AUTH_TOKEN and
    credential profiles. Without a key (a proxy that needs none) a placeholder is sent.
    """
    if not config.api_key:
        log.warning(f"No API key configured for {config.provider_name}; sending a placeholder")
    base_url = config.base_url or ANTHROPIC_DEFAULT_BASE_URL
    log.debug(f"Creating Anthropic client for {config.provider_name}: base_url={base_url}")
    return AsyncAnthropic(
        api_key=config.api_key or PLACEHOLDER_API_KEY,
        base_url=base_url,
        default_headers=config.default_headers or None,
        timeout=LLM_TIMEOUT,
    )


def create_client(config: ModelConfig) -> Union[AsyncOpenAI, AsyncAnthropic]:
    """Build the client that matches the config's provider kind."""
    if config.kind == KIND_OPENAI_COMPATIBLE:
        return create_openai_client(config)
    if config.kind == KIND_ANTHROPIC:
        return create_anthropic_client(config)
    raise ModelConfigError(f"Unknown provider kind: {config.kind}")


def get_client(config: ModelConfig) -> Union[AsyncOpenAI, AsyncAnthropic]:
    """
    A client for the config's provider account, reused across calls.

    Clients are keyed by event loop as well, because a connection pool can't be
    shared between loops (scripts that call asyncio.run() more than once).
    """
    try:
        loop_id = id(asyncio.get_running_loop())
    except RuntimeError:
        loop_id = None
    key = (
        loop_id,
        config.kind,
        config.base_url,
        config.api_key,
        tuple(sorted((config.default_headers or {}).items())),
    )
    client = _clients.get(key)
    if client is None:
        client = create_client(config)
        _clients[key] = client
        while len(_clients) > MAX_CACHED_CLIENTS:
            _clients.popitem(last=False)
    else:
        _clients.move_to_end(key)
    return client
