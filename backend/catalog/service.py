"""
Catalog entries: validation, storage and their API views.

Shared by the HTTP API (backend/api/catalog.py) and the catalog file import
(catalog_file.py), so both apply the same rules. Errors are CatalogError
subclasses with an HTTP status; the API turns them into HTTP errors and the
import into messages in ImportResult.errors.

API keys are write-only: they are encrypted on the way in, and the views only
contain apiKeySource and apiKeyMasked.
"""
import logging
import re
from typing import Optional

from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from backend.catalog import crypto
from backend.catalog.resolver import api_key_source, is_guest, model_usable, persona_usable
from backend.database import db
from backend.models.catalog import (
    ModelCreate,
    ModelOut,
    ModelUpdate,
    PersonaCreate,
    PersonaOut,
    PersonaUpdate,
    PersonaVariable,
    ProviderCreate,
    ProviderOut,
    ProviderUpdate,
    PublicModel,
    PublicPersona,
)

log = logging.getLogger(__name__)


class CatalogError(Exception):
    """Invalid catalog input (HTTP 400)."""
    status_code = 400


class CatalogNotFound(CatalogError):
    """The provider, model or persona does not exist (HTTP 404)."""
    status_code = 404


class CatalogConflict(CatalogError):
    """A name is already taken (HTTP 409)."""
    status_code = 409


class CatalogNotAllowed(CatalogError):
    """The user may not use this model or persona (HTTP 403)."""
    status_code = 403


# API field (camelCase) -> column, per table. Nullable columns can be cleared
# with null in an update; null on any other field leaves it unchanged.
PROVIDER_FIELDS = {
    "name": "name",
    "kind": "kind",
    "baseUrl": "base_url",
    "apiKeyEnv": "api_key_env",
    "privacyTier": "privacy_tier",
    "currency": "currency",
    "defaultHeaders": "default_headers",
    "notes": "notes",
    "enabled": "enabled",
}
PROVIDER_NULLABLE = {"base_url", "api_key_env", "default_headers", "notes"}

MODEL_FIELDS = {
    "providerId": "provider_id",
    "displayName": "display_name",
    "modelId": "model_id",
    "description": "description",
    "supportsTools": "supports_tools",
    "supportsVision": "supports_vision",
    "reasoning": "reasoning",
    "reasoningPassback": "reasoning_passback",
    "contextWindow": "context_window",
    "maxOutputTokens": "max_output_tokens",
    "temperature": "temperature",
    "topP": "top_p",
    "reasoningEffort": "reasoning_effort",
    "extraBody": "extra_body",
    "privacyTier": "privacy_tier",
    "inputPricePerMtok": "input_price_per_mtok",
    "outputPricePerMtok": "output_price_per_mtok",
    "isAuxiliary": "is_auxiliary",
    "availableToGuests": "available_to_guests",
    "enabled": "enabled",
    "sortOrder": "sort_order",
    "notes": "notes",
}
MODEL_NULLABLE = {
    "description", "context_window", "max_output_tokens", "temperature", "top_p",
    "reasoning_effort", "extra_body", "privacy_tier", "input_price_per_mtok",
    "output_price_per_mtok", "notes",
}

PERSONA_FIELDS = {
    "name": "name",
    "description": "description",
    "systemPrompt": "system_prompt",
    "variables": "variables",
    "defaultModelId": "default_model_id",
    "availableToGuests": "available_to_guests",
    "enabled": "enabled",
    "sortOrder": "sort_order",
}
PERSONA_NULLABLE = {"description", "default_model_id", "variables"}

# Columns that must not be empty strings
REQUIRED_TEXT_COLUMNS = {"name", "display_name", "model_id", "system_prompt"}

# api_key_env must name a key-like variable, so a catalog entry can't send
# server secrets such as POSTGRES_PASSWORD to an arbitrary base URL
ENV_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(_KEY|_TOKEN)$")
FORBIDDEN_ENV_NAMES = {"CATALOG_SECRET_KEY"}


# =========================================================================
# Input conversion and validation
# =========================================================================

def _to_columns(data: BaseModel, fields: dict, nullable: set, *, partial: bool) -> dict:
    """
    Convert an API model to column values.

    Strings are stripped; empty strings clear nullable columns. In a partial
    update only the fields that were sent are converted, and null on a
    non-nullable field is ignored.

    Args:
        data: The Pydantic request model.
        fields: API field -> column mapping.
        nullable: Columns that may be NULL.
        partial: True for updates (only sent fields), False for creates.

    Returns:
        Column name -> value.

    Raises:
        CatalogError: If a required text field is empty.
    """
    dumped = data.model_dump(exclude_unset=partial)
    values = {}
    for field, column in fields.items():
        if field not in dumped:
            continue
        value = dumped[field]
        if isinstance(value, str):
            value = value.strip()
            if not value:
                if column in REQUIRED_TEXT_COLUMNS:
                    raise CatalogError(f"{field} must not be empty")
                value = None
        if value is None and column not in nullable:
            continue
        values[column] = value
    return values


def _check_env_name(name: Optional[str]) -> None:
    """Reject api_key_env values that don't look like an API key variable."""
    if name is None:
        return
    if name.upper() in FORBIDDEN_ENV_NAMES or not ENV_NAME_PATTERN.match(name):
        raise CatalogError(
            f"apiKeyEnv '{name}' is not allowed: it must name an API key variable "
            "ending in _KEY or _TOKEN (e.g. CORTECS_API_KEY)"
        )


def _check_base_url(url: Optional[str]) -> None:
    """Reject base URLs that are not http(s)."""
    if url is not None and not re.match(r"^https?://", url, re.IGNORECASE):
        raise CatalogError(f"baseUrl '{url}' must start with http:// or https://")


def _check_variables(variables: Optional[list]) -> None:
    """Reject personas that declare a variable twice."""
    names = [v["name"] for v in variables or []]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise CatalogError(f"Duplicate persona variable(s): {', '.join(duplicates)}")


def _write(operation, what: str):
    """
    Run a database write and turn constraint violations into catalog errors.

    Args:
        operation: Zero-argument callable doing the write.
        what: Description for the error message, e.g. "provider 'Cortecs'".

    Returns:
        The operation's result.
    """
    try:
        return operation()
    except IntegrityError as e:
        code = getattr(e.orig, "pgcode", None)
        if code == "23505":  # unique_violation
            raise CatalogConflict(f"A {what} already exists") from e
        if code == "23503":  # foreign_key_violation
            raise CatalogError(f"The {what} refers to a missing entry") from e
        raise CatalogError(f"The {what} could not be saved: {e.orig}") from e


# =========================================================================
# API views
# =========================================================================

def _float(value) -> Optional[float]:
    return float(value) if value is not None else None


def provider_out(row: dict) -> ProviderOut:
    """
    The admin view of a provider row (from get_llm_providers / get_llm_provider_by_id).

    The key itself never leaves this function: only its source and a mask.
    """
    masked = None
    if row.get("api_key_encrypted"):
        try:
            masked = crypto.mask(crypto.decrypt(row["api_key_encrypted"]))
        except crypto.CatalogSecretError as e:
            log.error(f"Provider '{row['name']}': {e}")
    return ProviderOut(
        id=row["id"],
        name=row["name"],
        kind=row["kind"],
        baseUrl=row.get("base_url"),
        apiKeyEnv=row.get("api_key_env"),
        privacyTier=row["privacy_tier"],
        currency=row.get("currency") or "USD",
        defaultHeaders=row.get("default_headers"),
        notes=row.get("notes"),
        enabled=row.get("enabled") is not False,
        apiKeySource=api_key_source(row),
        apiKeyMasked=masked,
        modelCount=row.get("model_count") or 0,
        createdAt=row.get("created_at"),
        updatedAt=row.get("updated_at"),
    )


def model_out(row: dict) -> ModelOut:
    """The admin view of a model row (from get_llm_models / get_llm_model_by_id)."""
    return ModelOut(
        id=row["id"],
        providerId=row["provider_id"],
        providerName=row["provider_name"],
        displayName=row["display_name"],
        modelId=row["model_id"],
        description=row.get("description"),
        supportsTools=row.get("supports_tools") is not False,
        supportsVision=bool(row.get("supports_vision")),
        reasoning=row.get("reasoning") or "none",
        reasoningPassback=bool(row.get("reasoning_passback")),
        contextWindow=row.get("context_window"),
        maxOutputTokens=row.get("max_output_tokens"),
        temperature=_float(row.get("temperature")),
        topP=_float(row.get("top_p")),
        reasoningEffort=row.get("reasoning_effort"),
        extraBody=row.get("extra_body"),
        privacyTier=row.get("privacy_tier"),
        effectivePrivacyTier=row["effective_privacy_tier"],
        currency=row.get("currency") or "USD",
        inputPricePerMtok=_float(row.get("input_price_per_mtok")),
        outputPricePerMtok=_float(row.get("output_price_per_mtok")),
        isAuxiliary=bool(row.get("is_auxiliary")),
        availableToGuests=bool(row.get("available_to_guests")),
        enabled=row.get("enabled") is not False,
        sortOrder=row.get("sort_order") or 0,
        notes=row.get("notes"),
    )


def model_public(row: dict) -> PublicModel:
    """The picker view of a model row."""
    return PublicModel(
        id=row["id"],
        displayName=row["display_name"],
        description=row.get("description"),
        providerName=row["provider_name"],
        privacyTier=row["effective_privacy_tier"],
        supportsTools=row.get("supports_tools") is not False,
        supportsVision=bool(row.get("supports_vision")),
        reasoning=row.get("reasoning") or "none",
        contextWindow=row.get("context_window"),
        inputPricePerMtok=_float(row.get("input_price_per_mtok")),
        outputPricePerMtok=_float(row.get("output_price_per_mtok")),
        currency=row.get("currency") or "USD",
    )


def _variables(row: dict) -> list[PersonaVariable]:
    """A persona's stored variables; malformed entries are skipped with a warning."""
    result = []
    for variable in row.get("variables") or []:
        try:
            result.append(PersonaVariable(**variable))
        except (TypeError, ValueError) as e:
            log.warning(f"Persona {row['id']}: skipping malformed variable {variable!r}: {e}")
    return result


def persona_out(row: dict) -> PersonaOut:
    """The admin view of a persona row."""
    return PersonaOut(
        id=row["id"],
        name=row["name"],
        description=row.get("description"),
        systemPrompt=row["system_prompt"],
        variables=_variables(row),
        defaultModelId=row.get("default_model_id"),
        availableToGuests=bool(row.get("available_to_guests")),
        enabled=row.get("enabled") is not False,
        sortOrder=row.get("sort_order") or 0,
    )


def persona_public(row: dict, visible_model_ids: set) -> PublicPersona:
    """The picker view of a persona row; a default model the user can't see is left out."""
    default_model_id = row.get("default_model_id")
    return PublicPersona(
        id=row["id"],
        name=row["name"],
        description=row.get("description"),
        systemPrompt=row["system_prompt"],
        variables=_variables(row),
        defaultModelId=default_model_id if default_model_id in visible_model_ids else None,
    )


# =========================================================================
# Picker lists (every user, guests filtered)
# =========================================================================

def public_models(user: Optional[dict]) -> list[PublicModel]:
    """Enabled models of enabled providers the user may use, by sort order and name."""
    rows = db.get_llm_models(enabled_only=True, guests_only=is_guest(user))
    return [model_public(row) for row in rows]


def public_personas(user: Optional[dict]) -> list[PublicPersona]:
    """Enabled personas the user may use."""
    rows = db.get_personas(enabled_only=True, guests_only=is_guest(user))
    visible_model_ids = {
        row["id"] for row in db.get_llm_models(enabled_only=True, guests_only=is_guest(user))
    }
    return [persona_public(row, visible_model_ids) for row in rows]


# =========================================================================
# Providers
# =========================================================================

def list_providers() -> list[ProviderOut]:
    """All providers with their model counts, by name."""
    return [provider_out(row) for row in db.get_llm_providers()]


def _require_provider(provider_id: int) -> dict:
    provider = db.get_llm_provider_by_id(provider_id)
    if not provider:
        raise CatalogNotFound(f"Provider {provider_id} not found")
    return provider


def create_provider(data: ProviderCreate) -> ProviderOut:
    """
    Create a provider. A given apiKey is stored encrypted.

    Raises:
        CatalogError: Invalid base URL or api_key_env.
        CatalogConflict: The name is taken.
    """
    values = _to_columns(data, PROVIDER_FIELDS, PROVIDER_NULLABLE, partial=False)
    _check_base_url(values.get("base_url"))
    _check_env_name(values.get("api_key_env"))
    if data.apiKey and data.apiKey.strip():
        values["api_key_encrypted"] = crypto.encrypt(data.apiKey.strip())

    row = _write(lambda: db.create_llm_provider(values), f"provider named '{values['name']}'")
    return provider_out(db.get_llm_provider_by_id(row["id"]))


def update_provider(provider_id: int, data: ProviderUpdate) -> ProviderOut:
    """
    Update the fields of a provider that were sent.

    apiKey: left out or null keeps the stored key, "" removes it, anything
    else replaces it.

    Raises:
        CatalogNotFound: The provider does not exist.
        CatalogError: Invalid base URL or api_key_env.
        CatalogConflict: The new name is taken.
    """
    _require_provider(provider_id)
    values = _to_columns(data, PROVIDER_FIELDS, PROVIDER_NULLABLE, partial=True)
    _check_base_url(values.get("base_url"))
    _check_env_name(values.get("api_key_env"))
    if "apiKey" in data.model_fields_set and data.apiKey is not None:
        key = data.apiKey.strip()
        values["api_key_encrypted"] = crypto.encrypt(key) if key else None

    _write(lambda: db.update_llm_provider(provider_id, values), f"provider named '{values.get('name')}'")
    return provider_out(db.get_llm_provider_by_id(provider_id))


def delete_provider(provider_id: int) -> None:
    """Delete a provider and its models."""
    if not db.delete_llm_provider(provider_id):
        raise CatalogNotFound(f"Provider {provider_id} not found")


# =========================================================================
# Models
# =========================================================================

def list_models() -> list[ModelOut]:
    """All models (including disabled ones), by sort order and name."""
    return [model_out(row) for row in db.get_llm_models()]


def create_model(data: ModelCreate) -> ModelOut:
    """
    Create a model.

    Raises:
        CatalogError: The provider does not exist or a field is invalid.
        CatalogConflict: The provider already has a model with this display name.
    """
    values = _to_columns(data, MODEL_FIELDS, MODEL_NULLABLE, partial=False)
    if not db.get_llm_provider_by_id(values["provider_id"]):
        raise CatalogError(f"Provider {values['provider_id']} not found")

    row = _write(
        lambda: db.create_llm_model(values),
        f"model named '{values['display_name']}' for this provider",
    )
    return model_out(db.get_llm_model_by_id(row["id"]))


def update_model(model_id: int, data: ModelUpdate) -> ModelOut:
    """
    Update the fields of a model that were sent; null clears optional fields.

    Raises:
        CatalogNotFound: The model does not exist.
        CatalogError: The new provider does not exist or a field is invalid.
        CatalogConflict: The display name is taken for the provider.
    """
    existing = db.get_llm_model_by_id(model_id)
    if not existing:
        raise CatalogNotFound(f"Model {model_id} not found")
    values = _to_columns(data, MODEL_FIELDS, MODEL_NULLABLE, partial=True)
    if "provider_id" in values and not db.get_llm_provider_by_id(values["provider_id"]):
        raise CatalogError(f"Provider {values['provider_id']} not found")

    _write(
        lambda: db.update_llm_model(model_id, values),
        f"model named '{values.get('display_name', existing['display_name'])}' for this provider",
    )
    return model_out(db.get_llm_model_by_id(model_id))


def delete_model(model_id: int) -> None:
    """Delete a model."""
    if not db.delete_llm_model(model_id):
        raise CatalogNotFound(f"Model {model_id} not found")


# =========================================================================
# Personas
# =========================================================================

def list_personas() -> list[PersonaOut]:
    """All personas (including disabled ones), by sort order and name."""
    return [persona_out(row) for row in db.get_personas()]


def _check_default_model(model_id: Optional[int]) -> None:
    if model_id is not None and not db.get_llm_model_by_id(model_id):
        raise CatalogError(f"Default model {model_id} not found")


def create_persona(data: PersonaCreate) -> PersonaOut:
    """
    Create a persona.

    Raises:
        CatalogError: The default model does not exist or a variable is declared twice.
        CatalogConflict: The name is taken.
    """
    values = _to_columns(data, PERSONA_FIELDS, PERSONA_NULLABLE, partial=False)
    _check_variables(values.get("variables"))
    _check_default_model(values.get("default_model_id"))

    row = _write(lambda: db.create_persona(values), f"persona named '{values['name']}'")
    return persona_out(row)


def update_persona(persona_id: int, data: PersonaUpdate) -> PersonaOut:
    """
    Update the fields of a persona that were sent.

    Raises:
        CatalogNotFound: The persona does not exist.
        CatalogError: The default model does not exist or a variable is declared twice.
        CatalogConflict: The new name is taken.
    """
    if not db.get_persona_by_id(persona_id):
        raise CatalogNotFound(f"Persona {persona_id} not found")
    values = _to_columns(data, PERSONA_FIELDS, PERSONA_NULLABLE, partial=True)
    if "variables" in values:
        values["variables"] = values["variables"] or []
        _check_variables(values["variables"])
    _check_default_model(values.get("default_model_id"))

    row = _write(lambda: db.update_persona(persona_id, values), f"persona named '{values.get('name')}'")
    return persona_out(row)


def delete_persona(persona_id: int) -> None:
    """Delete a persona."""
    if not db.delete_persona(persona_id):
        raise CatalogNotFound(f"Persona {persona_id} not found")


# =========================================================================
# Checks for conversations and settings
# =========================================================================

def check_model_choice(user: Optional[dict], model_id: Optional[int]) -> None:
    """
    Check that a user may pick a model for a conversation or as default.

    Raises:
        CatalogError: The model does not exist (400).
        CatalogNotAllowed: The model is disabled or not available to the user (403).
    """
    if model_id is None:
        return
    model = db.get_llm_model_by_id(model_id)
    if not model:
        raise CatalogError(f"Model {model_id} not found")
    if not model_usable(model, user):
        raise CatalogNotAllowed(f"Model {model_id} is not available")


def check_persona_choice(user: Optional[dict], persona_id: Optional[int]) -> None:
    """
    Check that a user may pick a persona for a conversation.

    Raises:
        CatalogError: The persona does not exist (400).
        CatalogNotAllowed: The persona is disabled or not available to the user (403).
    """
    if persona_id is None:
        return
    persona = db.get_persona_by_id(persona_id)
    if not persona:
        raise CatalogError(f"Persona {persona_id} not found")
    if not persona_usable(persona, user):
        raise CatalogNotAllowed(f"Persona {persona_id} is not available")
