"""
Catalog entries: validation, storage and their API views.

Shared by the HTTP API (backend/api/catalog.py) and the catalog file
(catalog_file.py), so both apply the same rules. Errors are CatalogError
subclasses with an HTTP status; the API turns them into HTTP errors and the
import into messages in ImportResult.errors.

Providers are only written by seeding from MODEL_CATALOG_FILE (upsert_provider);
the API lists them. Their keys come from environment variables, so the views
only say whether the variable is set (apiKeySet).
"""
import logging
import re
from typing import Optional

from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from backend.catalog.resolver import api_key_set, is_guest, model_usable, persona_usable
from backend.database import db
from backend.llm.tools import TOOL_GROUPS, tool_group_status
from backend.models.catalog import (
    ModelCreate,
    ModelOut,
    ModelUpdate,
    PersonaCreate,
    PersonaOut,
    PersonaUpdate,
    PersonaVariable,
    ProviderBase,
    ProviderOut,
    PublicModel,
    PublicPersona,
    ToolGroupStatus,
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
    "tools": "tools",
    "availableToGuests": "available_to_guests",
    "enabled": "enabled",
    "sortOrder": "sort_order",
}
# tools: NULL = every enabled tool, so null in an update selects all tools again
PERSONA_NULLABLE = {"description", "variables", "tools"}

# Columns that must not be empty strings
REQUIRED_TEXT_COLUMNS = {"name", "display_name", "model_id", "system_prompt"}

# api_key_env must name a key-like variable, so a catalog entry can't send
# server secrets such as POSTGRES_PASSWORD to an arbitrary base URL
ENV_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(_KEY|_TOKEN)$")


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
    if not ENV_NAME_PATTERN.match(name):
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


def _normalize_tools(values: dict) -> None:
    """A persona's tool groups without duplicates, in TOOL_GROUPS order (None stays None)."""
    if values.get("tools") is not None:
        values["tools"] = [group for group in TOOL_GROUPS if group in values["tools"]]


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

    The key itself is never part of it, only whether its variable is set.
    """
    return ProviderOut(
        id=row["id"],
        name=row["name"],
        kind=row["kind"],
        baseUrl=row.get("base_url"),
        apiKeyEnv=row.get("api_key_env"),
        apiKeySet=api_key_set(row),
        privacyTier=row["privacy_tier"],
        currency=row.get("currency") or "USD",
        defaultHeaders=row.get("default_headers"),
        notes=row.get("notes"),
        enabled=row.get("enabled") is not False,
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


def _tools(row: dict) -> Optional[list[str]]:
    """A persona's stored tool groups (None = all); unknown groups are skipped with a warning."""
    tools = row.get("tools")
    if tools is None:
        return None
    unknown = [group for group in tools if group not in TOOL_GROUPS]
    if unknown:
        log.warning(f"Persona {row['id']}: skipping unknown tool group(s) {unknown!r}")
    return [group for group in tools if group in TOOL_GROUPS]


def persona_out(row: dict) -> PersonaOut:
    """The admin view of a persona row."""
    return PersonaOut(
        id=row["id"],
        name=row["name"],
        description=row.get("description"),
        systemPrompt=row["system_prompt"],
        variables=_variables(row),
        tools=_tools(row),
        availableToGuests=bool(row.get("available_to_guests")),
        enabled=row.get("enabled") is not False,
        sortOrder=row.get("sort_order") or 0,
    )


def persona_public(row: dict) -> PublicPersona:
    """The picker view of a persona row."""
    return PublicPersona(
        id=row["id"],
        name=row["name"],
        description=row.get("description"),
        systemPrompt=row["system_prompt"],
        variables=_variables(row),
        tools=_tools(row),
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
    return [persona_public(row) for row in rows]


# =========================================================================
# Providers
# =========================================================================

def list_providers() -> list[ProviderOut]:
    """All providers with their model counts, by name."""
    return [provider_out(row) for row in db.get_llm_providers()]


def upsert_provider(data: ProviderBase) -> bool:
    """
    Create a provider, or replace the one with the same name (seeding only).

    The catalog file is the only source of providers, so an existing provider
    takes every value of the entry; fields the entry leaves out get their
    defaults. Its models are kept.

    Args:
        data: The provider from the catalog file.

    Returns:
        True if the provider was created, False if it was updated.

    Raises:
        CatalogError: Invalid base URL or api_key_env.
    """
    # Not partial: every field is written, so a value removed from the file is cleared
    values = _to_columns(data, PROVIDER_FIELDS, PROVIDER_NULLABLE, partial=False)
    _check_base_url(values.get("base_url"))
    _check_env_name(values.get("api_key_env"))

    existing = db.get_llm_provider_by_name(values["name"])
    what = f"provider named '{values['name']}'"
    if existing:
        _write(lambda: db.update_llm_provider(existing["id"], values), what)
        return False
    _write(lambda: db.create_llm_provider(values), what)
    return True


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


def create_persona(data: PersonaCreate) -> PersonaOut:
    """
    Create a persona.

    Raises:
        CatalogError: A variable is declared twice.
        CatalogConflict: The name is taken.
    """
    values = _to_columns(data, PERSONA_FIELDS, PERSONA_NULLABLE, partial=False)
    _check_variables(values.get("variables"))
    _normalize_tools(values)

    row = _write(lambda: db.create_persona(values), f"persona named '{values['name']}'")
    return persona_out(row)


def update_persona(persona_id: int, data: PersonaUpdate) -> PersonaOut:
    """
    Update the fields of a persona that were sent.

    tools: left out keeps the selection, null selects every enabled tool, [] none.

    Raises:
        CatalogNotFound: The persona does not exist.
        CatalogError: A variable is declared twice.
        CatalogConflict: The new name is taken.
    """
    if not db.get_persona_by_id(persona_id):
        raise CatalogNotFound(f"Persona {persona_id} not found")
    values = _to_columns(data, PERSONA_FIELDS, PERSONA_NULLABLE, partial=True)
    if "variables" in values:
        values["variables"] = values["variables"] or []
        _check_variables(values["variables"])
    _normalize_tools(values)

    row = _write(lambda: db.update_persona(persona_id, values), f"persona named '{values.get('name')}'")
    return persona_out(row)


def delete_persona(persona_id: int) -> None:
    """Delete a persona."""
    if not db.delete_persona(persona_id):
        raise CatalogNotFound(f"Persona {persona_id} not found")


# =========================================================================
# Tools
# =========================================================================

def list_tool_groups() -> list[ToolGroupStatus]:
    """Every tool group a persona can select, with whether the server enables it."""
    return [ToolGroupStatus(**status) for status in tool_group_status()]


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
