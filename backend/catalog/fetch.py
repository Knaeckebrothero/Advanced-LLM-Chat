"""
"Fetch models": a provider's GET /models list, offered as a pick list in the admin UI.

Uses the official SDKs directly: AsyncOpenAI for openai_compatible providers
and AsyncAnthropic for Anthropic. The API key is always passed explicitly, so
the SDKs never fall back to OPENAI_API_KEY / ANTHROPIC_API_KEY and send those
to another provider's base URL.
"""
import logging
from typing import Optional

from backend.catalog.crypto import mask
from backend.catalog.resolver import provider_api_key
from backend.catalog.service import CatalogError, CatalogNotFound
from backend.database import db
from backend.llm.types import KIND_ANTHROPIC
from backend.models.catalog import FetchedModel, FetchModelsResponse

log = logging.getLogger(__name__)

# Seconds to wait for a provider's model list
FETCH_TIMEOUT = 30.0

# Placeholder key for providers without one (public model lists); the SDKs refuse None
NO_KEY = "no-key"

# Fields in which providers report the context window, in order of preference
CONTEXT_WINDOW_FIELDS = (
    "context_window", "context_length", "context_size", "max_context_length",
    "max_model_len", "max_input_tokens",
)


class ProviderRequestError(CatalogError):
    """The provider's API call failed (HTTP 502)."""
    status_code = 502


def _context_window(extra: dict) -> Optional[int]:
    """The context window from a model entry's provider-specific fields, if any."""
    candidates = [extra.get(field) for field in CONTEXT_WINDOW_FIELDS]
    # OpenRouter reports it per hosting provider as well
    top_provider = extra.get("top_provider")
    if isinstance(top_provider, dict):
        candidates.append(top_provider.get("context_length"))
    for value in candidates:
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            return int(value)
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _error_message(error: Exception, api_key: Optional[str]) -> str:
    """
    A readable message from an SDK error, with the API key masked in case the
    provider echoes it.
    """
    message = None
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        inner = body.get("error")
        if isinstance(inner, dict):
            message = inner.get("message")
        elif isinstance(inner, str):
            message = inner
        message = message or body.get("message") or body.get("detail")
    message = str(message or getattr(error, "message", None) or error or error.__class__.__name__)

    status_code = getattr(error, "status_code", None)
    if status_code:
        message = f"HTTP {status_code}: {message}"
    if api_key and api_key != NO_KEY:
        message = message.replace(api_key, mask(api_key) or "***")
    return message


async def _list_openai_compatible(provider: dict, api_key: Optional[str]) -> list[FetchedModel]:
    """GET {base_url}/models through the OpenAI SDK."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=api_key or NO_KEY,
        base_url=provider.get("base_url") or None,
        default_headers=provider.get("default_headers") or None,
        timeout=FETCH_TIMEOUT,
        max_retries=1,
    )
    try:
        models = []
        async for entry in client.models.list():
            extra = entry.model_extra or {}
            models.append(FetchedModel(
                id=entry.id,
                ownedBy=getattr(entry, "owned_by", None) or extra.get("owned_by"),
                contextWindow=_context_window(extra),
            ))
        return models
    finally:
        await client.close()


async def _list_anthropic(provider: dict, api_key: Optional[str]) -> list[FetchedModel]:
    """The Anthropic model list through the Anthropic SDK (paginated)."""
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(
        api_key=api_key or NO_KEY,
        base_url=provider.get("base_url") or None,
        default_headers=provider.get("default_headers") or None,
        timeout=FETCH_TIMEOUT,
        max_retries=1,
    )
    try:
        models = []
        async for entry in client.models.list(limit=100):
            extra = entry.model_extra or {}
            models.append(FetchedModel(
                id=entry.id,
                ownedBy="anthropic",
                contextWindow=_context_window(extra),
            ))
        return models
    finally:
        await client.close()


async def fetch_provider_models(provider_id: int) -> FetchModelsResponse:
    """
    List the models a provider offers, marking those already in the catalog.

    Args:
        provider_id: The provider's ID.

    Returns:
        The models, sorted by ID.

    Raises:
        CatalogNotFound: The provider does not exist.
        ProviderRequestError: The provider's API call failed (message from the provider).
    """
    provider = db.get_llm_provider_by_id(provider_id)
    if not provider:
        raise CatalogNotFound(f"Provider {provider_id} not found")

    api_key = provider_api_key(provider)
    log.info(f"Fetching models of provider '{provider['name']}' ({provider['kind']}, "
             f"{provider.get('base_url') or 'SDK default URL'})")
    try:
        if provider["kind"] == KIND_ANTHROPIC:
            models = await _list_anthropic(provider, api_key)
        else:
            models = await _list_openai_compatible(provider, api_key)
    except Exception as e:
        message = _error_message(e, api_key)
        log.warning(f"Fetching models of provider '{provider['name']}' failed: {message}")
        raise ProviderRequestError(f"The provider returned an error: {message}") from e

    added = {row["model_id"] for row in db.get_llm_models(provider_id=provider_id)}
    for model in models:
        model.alreadyAdded = model.id in added
    models.sort(key=lambda m: m.id)
    log.info(f"Provider '{provider['name']}' offers {len(models)} models ({len(added)} in the catalog)")
    return FetchModelsResponse(models=models)
