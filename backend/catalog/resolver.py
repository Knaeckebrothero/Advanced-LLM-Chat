"""
Model resolution: which model answers, with which persona prompt and tools.

The runtime asks resolve_model() for the ModelConfig of a conversation. The
order is: the explicitly requested model, the conversation's model, the user's
default model, the first enabled catalog model by sort_order, and finally the
environment model (model_from_env()), so setups without a catalog keep working.

Guests only get models and personas marked available_to_guests. Disabled
models, and all models of disabled providers, can't be resolved, except through
get_model_config(), which skips every check (smoke test, admin test button).

A provider's API key always comes from the environment variable named in its
api_key_env; keys are never stored in the database.

The user dicts are those of backend.security.auth.get_current_user():
user_id, email, is_guest. Conversations are rows from db.get_conversation_by_id().
"""
import logging
import os
import re
from datetime import date
from typing import Optional

from backend.database import db
from backend.llm.types import ModelConfig, auxiliary_model_from_env, model_from_env

log = logging.getLogger(__name__)

# {{name}} placeholders in persona prompts; spaces inside the braces are allowed
PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")

# UI language codes to the names used for {{language}}
LANGUAGE_NAMES = {
    "en": "English",
    "de": "German",
}

DEFAULT_LANGUAGE = "en"


class ModelNotAvailable(Exception):
    """No model can answer: nothing in the catalog for this user and no environment model."""


class ModelNotAllowed(Exception):
    """An explicitly requested model is unknown, disabled or not available to the user."""


# =========================================================================
# Users and permissions
# =========================================================================

def is_guest(user: Optional[dict]) -> bool:
    """Whether the user is a guest. A missing user is treated as a guest (most restrictive)."""
    return user is None or bool(user.get("is_guest"))


def _user_id(user: Optional[dict]) -> Optional[int]:
    """The user's ID from a session dict (user_id) or a users row (id)."""
    if not user:
        return None
    return user.get("user_id", user.get("id"))


def model_usable(model: Optional[dict], user: Optional[dict]) -> bool:
    """
    Whether a user may use a model.

    Args:
        model: A row from db.get_llm_model_by_id() / get_llm_models() (with provider_enabled).
        user: The current user.

    Returns:
        True if the model and its provider are enabled and, for guests, the
        model is available to guests.
    """
    if not model:
        return False
    if model.get("enabled") is False or model.get("provider_enabled") is False:
        return False
    if is_guest(user) and not model.get("available_to_guests"):
        return False
    return True


def persona_usable(persona: Optional[dict], user: Optional[dict]) -> bool:
    """
    Whether a user may use a persona.

    Args:
        persona: A row from db.get_persona_by_id().
        user: The current user.

    Returns:
        True if the persona is enabled and, for guests, available to guests.
    """
    if not persona:
        return False
    if persona.get("enabled") is False:
        return False
    if is_guest(user) and not persona.get("available_to_guests"):
        return False
    return True


# =========================================================================
# Building ModelConfig
# =========================================================================

def _env_key(provider: dict) -> Optional[str]:
    """The value of the provider's api_key_env variable, or None if unnamed, unset or blank."""
    env_name = provider.get("api_key_env")
    value = os.getenv(env_name, "").strip() if env_name else ""
    return value or None


def provider_api_key(provider: dict) -> Optional[str]:
    """
    The API key of a provider, from the environment variable named in api_key_env.

    Args:
        provider: A row from llm_providers.

    Returns:
        The key, or None without api_key_env or if the variable is not set.
    """
    value = _env_key(provider)
    if value is None and provider.get("api_key_env"):
        log.warning(f"Provider '{provider.get('name')}': environment variable {provider['api_key_env']} is not set")
    return value


def api_key_set(provider: dict) -> bool:
    """Whether the provider's api_key_env variable is set and not empty (for the admin view)."""
    return _env_key(provider) is not None


def _float(value) -> Optional[float]:
    """NUMERIC / REAL column value as a float, or None."""
    return float(value) if value is not None else None


def _bool(value, default: bool) -> bool:
    """Boolean column value with a default for NULL."""
    return default if value is None else bool(value)


def build_model_config(model: dict, provider: dict) -> ModelConfig:
    """
    Build the runtime configuration from a catalog model and its provider.

    Args:
        model: A row from llm_models (the joined columns are not needed).
        provider: The model's llm_providers row.

    Returns:
        The ModelConfig, with the API key from the environment and the effective privacy tier.
    """
    return ModelConfig(
        id=model["id"],
        display_name=model["display_name"],
        model_id=model["model_id"],
        provider_id=provider["id"],
        provider_name=provider["name"],
        kind=provider["kind"],
        base_url=provider.get("base_url") or None,
        api_key=provider_api_key(provider),
        default_headers=dict(provider.get("default_headers") or {}),
        privacy_tier=model.get("privacy_tier") or provider["privacy_tier"],
        currency=provider.get("currency") or "USD",
        supports_tools=_bool(model.get("supports_tools"), True),
        supports_vision=_bool(model.get("supports_vision"), False),
        reasoning=model.get("reasoning") or "none",
        reasoning_passback=_bool(model.get("reasoning_passback"), False),
        context_window=model.get("context_window"),
        max_output_tokens=model.get("max_output_tokens"),
        temperature=_float(model.get("temperature")),
        top_p=_float(model.get("top_p")),
        reasoning_effort=model.get("reasoning_effort") or None,
        extra_body=dict(model.get("extra_body") or {}),
        input_price_per_mtok=_float(model.get("input_price_per_mtok")),
        output_price_per_mtok=_float(model.get("output_price_per_mtok")),
    )


def _config_for_row(model: dict) -> ModelConfig:
    """Load the model's provider and build its ModelConfig."""
    provider = db.get_llm_provider_by_id(model["provider_id"])
    return build_model_config(model, provider)


# =========================================================================
# Resolution
# =========================================================================

def _conversation_model_id(conversation: Optional[dict]) -> Optional[int]:
    """The model stored with a conversation (row or API dict)."""
    if not conversation:
        return None
    return conversation.get("model_id", conversation.get("modelId"))


def _default_model_id(user: Optional[dict]) -> Optional[int]:
    """The user's default model from user_settings; guests have none."""
    if is_guest(user):
        return None
    settings = db.get_user_settings(_user_id(user))
    return settings.get("default_model_id") if settings else None


def resolve_model(
    user: Optional[dict],
    model_id: Optional[int] = None,
    conversation: Optional[dict] = None
) -> ModelConfig:
    """
    Decide which model answers.

    Order: model_id, the conversation's model_id, the user's default_model_id,
    the first enabled model by sort_order, then model_from_env(). Stored
    choices (conversation, default) that are no longer usable are skipped.

    Args:
        user: The current user (get_current_user()); None is treated as a guest.
        model_id: An explicitly requested model (e.g. stream-generate's modelId).
        conversation: The conversation row (uses its model_id).

    Returns:
        The ModelConfig to call.

    Raises:
        ModelNotAllowed: If model_id is unknown, disabled or not available to the user.
        ModelNotAvailable: If no model is left, not even from the environment.
    """
    # 1. An explicit request must be honored or rejected, never silently replaced
    if model_id is not None:
        model = db.get_llm_model_by_id(model_id)
        if not model_usable(model, user):
            log.warning(f"Model {model_id} requested by user {_user_id(user)} is not available")
            raise ModelNotAllowed(f"Model {model_id} is not available")
        log.debug(f"Resolved requested model {model_id} ({model['display_name']})")
        return _config_for_row(model)

    # 2. The conversation's model, 3. the user's default model
    for source, candidate in (
        ("conversation", _conversation_model_id(conversation)),
        ("default", _default_model_id(user)),
    ):
        if candidate is None:
            continue
        model = db.get_llm_model_by_id(candidate)
        if model_usable(model, user):
            log.debug(f"Resolved {source} model {candidate} ({model['display_name']})")
            return _config_for_row(model)
        log.info(f"The {source} model {candidate} is not available for user {_user_id(user)}, falling back")

    # 4. The first enabled catalog model
    models = db.get_llm_models(enabled_only=True, guests_only=is_guest(user))
    if models:
        log.debug(f"Resolved first catalog model {models[0]['id']} ({models[0]['display_name']})")
        return _config_for_row(models[0])

    # 5. The environment model, as before the catalog
    env_model = model_from_env()
    if env_model:
        log.debug(f"Resolved environment model {env_model.model_id}")
        return env_model

    raise ModelNotAvailable(
        "No model is available: the catalog has no usable model and neither "
        "OPENAI_API_KEY nor ANTHROPIC_API_KEY is set"
    )


def resolve_auxiliary_model() -> Optional[ModelConfig]:
    """
    The model for background tasks (titles, speech preprocessing).

    Returns:
        The first enabled model with is_auxiliary (by sort_order), else
        auxiliary_model_from_env(), which may be None.
    """
    models = db.get_llm_models(enabled_only=True, auxiliary_only=True)
    if models:
        return _config_for_row(models[0])
    return auxiliary_model_from_env()


def get_model_config(model_id: int) -> ModelConfig:
    """
    The configuration of any catalog model, without permission or enabled checks.

    For the smoke test and the admin test button only.

    Args:
        model_id: The model's ID (llm_models.id).

    Returns:
        The ModelConfig.

    Raises:
        ModelNotAvailable: If the model does not exist.
    """
    model = db.get_llm_model_by_id(model_id)
    if not model:
        raise ModelNotAvailable(f"Model {model_id} does not exist")
    return _config_for_row(model)


# =========================================================================
# Personas
# =========================================================================

def format_date(day: date) -> str:
    """The date as {{date}} shows it, e.g. "Friday, 30 October 2026"."""
    return f"{day:%A}, {day.day} {day:%B %Y}"


def language_name(language: Optional[str]) -> str:
    """A UI language code ('de') as its name ('German'); unknown values pass through."""
    if not language:
        return LANGUAGE_NAMES[DEFAULT_LANGUAGE]
    return LANGUAGE_NAMES.get(language.strip().lower(), language)


def user_display_name(user: Optional[dict]) -> str:
    """
    The name for {{user_name}}: the user's name, else the part of the email
    before the @, "Guest" for guests.
    """
    if is_guest(user):
        return "Guest"
    row = db.get_user_by_id(_user_id(user)) or {}
    name = (row.get("name") or "").strip()
    if name:
        return name
    email = row.get("email") or user.get("email") or ""
    return email.split("@")[0]


def user_language(user: Optional[dict]) -> str:
    """The user's UI language code from user_settings ('en' for guests and without settings)."""
    if is_guest(user):
        return DEFAULT_LANGUAGE
    settings = db.get_user_settings(_user_id(user))
    return (settings or {}).get("language") or DEFAULT_LANGUAGE


def render_prompt(
    template: str,
    variables: Optional[list],
    values: Optional[dict],
    *,
    user_name: str,
    language: Optional[str],
    today: Optional[date] = None
) -> str:
    """
    Fill the {{placeholders}} of a persona prompt.

    A declared variable gets its value from values, else its default, else ""
    (a blank value counts as missing). The built-ins {{date}}, {{user_name}}
    and {{language}} need no declaration; a declared variable of the same name
    overrides them. Unknown placeholders are left unchanged.

    Args:
        template: The persona's system prompt.
        variables: The persona's variables: [{"name", "label", "default"}].
        values: The conversation's persona_values.
        user_name: Value for {{user_name}}.
        language: UI language code or name for {{language}}.
        today: Date for {{date}} (default: today).

    Returns:
        The rendered prompt.
    """
    replacements = {
        "date": format_date(today or date.today()),
        "user_name": user_name or "",
        "language": language_name(language),
    }
    values = values or {}
    for variable in variables or []:
        name = variable.get("name") if isinstance(variable, dict) else None
        if not name:
            continue
        value = values.get(name)
        if value is None or not str(value).strip():
            value = variable.get("default")
        replacements[name] = "" if value is None else str(value)

    return PLACEHOLDER_PATTERN.sub(lambda match: replacements.get(match.group(1), match.group(0)), template)


def render_persona_prompt(
    persona_id: Optional[int],
    values: Optional[dict],
    *,
    user_name: str,
    language: Optional[str]
) -> Optional[str]:
    """
    The rendered system prompt of a persona.

    Args:
        persona_id: The persona (conversations.persona_id); None for no persona.
        values: The conversation's persona_values.
        user_name: Value for {{user_name}} (see user_display_name()).
        language: UI language code or name for {{language}} (see user_language()).

    Returns:
        The prompt, or None without a persona or if it is missing or disabled.
    """
    if persona_id is None:
        return None
    persona = db.get_persona_by_id(persona_id)
    if not persona or persona.get("enabled") is False:
        log.info(f"Persona {persona_id} is missing or disabled, answering without it")
        return None
    return render_prompt(
        persona["system_prompt"],
        persona.get("variables"),
        values,
        user_name=user_name,
        language=language,
    )


def persona_prompt_for_conversation(
    user: Optional[dict],
    conversation: Optional[dict],
    *,
    language: Optional[str] = None
) -> Optional[str]:
    """
    The rendered persona prompt of a conversation, for the runtime.

    Looks up the user's name and (unless given) UI language, and skips
    personas the user may not use (e.g. a guest with a persona that was
    later restricted).

    Args:
        user: The current user.
        conversation: The conversation row (persona_id, persona_values).
        language: UI language code; default from the user's settings.

    Returns:
        The prompt, or None without a usable persona.
    """
    persona_id = (conversation or {}).get("persona_id")
    if persona_id is None:
        return None
    persona = db.get_persona_by_id(persona_id)
    if not persona_usable(persona, user):
        log.info(f"Persona {persona_id} is not available for user {_user_id(user)}, answering without it")
        return None
    return render_prompt(
        persona["system_prompt"],
        persona.get("variables"),
        conversation.get("persona_values"),
        user_name=user_display_name(user),
        language=language or user_language(user),
    )


def persona_tool_groups(user: Optional[dict], conversation: Optional[dict]) -> Optional[list[str]]:
    """
    The tool groups the conversation's persona selected, for the runtime.

    Personas the user may not use are skipped, as in persona_prompt_for_conversation().

    Args:
        user: The current user.
        conversation: The conversation row (persona_id).

    Returns:
        The persona's tool groups (keys of backend.llm.tools.TOOL_GROUPS; [] for
        no tools), or None for every enabled tool: without a usable persona, or
        if the persona has no selection.
    """
    persona_id = (conversation or {}).get("persona_id")
    if persona_id is None:
        return None
    persona = db.get_persona_by_id(persona_id)
    if not persona_usable(persona, user):
        return None
    tools = persona.get("tools")
    return None if tools is None else list(tools)
