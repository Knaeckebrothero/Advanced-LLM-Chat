"""
The catalog file: JSON import, export and seeding from MODEL_CATALOG_FILE.

Format (snake_case keys matching the database columns, see docs/model_catalog_api.md):

    {
      "version": 1,
      "providers": [{"name", "kind", "base_url", "api_key_env", "privacy_tier", "currency", ...}],
      "models":    [{"provider": "<provider name>", "display_name", "model_id", ...}],
      "personas":  [{"name", "system_prompt", "variables", "default_model": {"provider", "display_name"}, ...}]
    }

Import upserts by natural key (providers by name, models by provider and
display_name, personas by name) and never deletes. A new entry gets defaults
for the keys it leaves out; an existing entry only changes the keys that are
present, and null clears optional columns. An "api_key" is stored encrypted.
Export writes every column, and the decrypted keys only when asked to.

Validation is the same as in the admin API (backend/catalog/service.py).
"""
import json
import logging
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from backend.catalog import crypto, service
from backend.catalog.service import CatalogError
from backend.database import db
from backend.models.catalog import (
    ImportCounts,
    ImportResult,
    ModelCreate,
    ModelUpdate,
    PersonaCreate,
    PersonaUpdate,
    ProviderCreate,
    ProviderUpdate,
)

log = logging.getLogger(__name__)

CATALOG_FILE_VERSION = 1

# Relative MODEL_CATALOG_FILE paths are resolved against the repository root
REPO_ROOT = Path(__file__).resolve().parents[2]

# File key -> API field, per section. Keys not listed are reported and ignored.
PROVIDER_KEYS = {column: field for field, column in service.PROVIDER_FIELDS.items()}
PROVIDER_KEYS["api_key"] = "apiKey"
MODEL_KEYS = {column: field for field, column in service.MODEL_FIELDS.items() if column != "provider_id"}
MODEL_KEYS["provider"] = None  # Natural key, resolved to providerId
PERSONA_KEYS = {column: field for field, column in service.PERSONA_FIELDS.items() if column != "default_model_id"}
PERSONA_KEYS["default_model"] = None  # {"provider", "display_name"}, resolved to defaultModelId

# Column order in exported entries (natural keys first)
PROVIDER_EXPORT_COLUMNS = [
    "name", "kind", "base_url", "api_key_env", "privacy_tier", "currency",
    "default_headers", "notes", "enabled",
]
MODEL_EXPORT_COLUMNS = [
    "display_name", "model_id", "description", "supports_tools", "supports_vision",
    "reasoning", "reasoning_passback", "context_window", "max_output_tokens",
    "temperature", "top_p", "reasoning_effort", "extra_body", "privacy_tier",
    "input_price_per_mtok", "output_price_per_mtok", "is_auxiliary",
    "available_to_guests", "enabled", "sort_order", "notes",
]
PERSONA_EXPORT_COLUMNS = [
    "name", "description", "system_prompt", "variables", "available_to_guests",
    "enabled", "sort_order",
]
NUMERIC_COLUMNS = {"temperature", "top_p", "input_price_per_mtok", "output_price_per_mtok"}


# =========================================================================
# Export
# =========================================================================

def _export_value(column: str, value):
    """Column value as JSON: NUMERIC/REAL as float."""
    if column in NUMERIC_COLUMNS and value is not None:
        return float(value)
    return value


def export_catalog(include_keys: bool = False) -> dict:
    """
    The whole catalog in the catalog file format.

    Args:
        include_keys: Add the decrypted "api_key" of providers with a stored key.

    Returns:
        The catalog file as a dict.
    """
    providers = db.get_llm_providers()
    provider_names = {row["id"]: row["name"] for row in providers}

    provider_entries = []
    for row in providers:
        entry = {column: row.get(column) for column in PROVIDER_EXPORT_COLUMNS}
        if include_keys and row.get("api_key_encrypted"):
            try:
                entry["api_key"] = crypto.decrypt(row["api_key_encrypted"])
            except crypto.CatalogSecretError as e:
                log.warning(f"Export: provider '{row['name']}' key left out: {e}")
        provider_entries.append(entry)

    models = sorted(db.get_llm_models(), key=lambda m: (m["provider_name"], m["sort_order"] or 0, m["display_name"]))
    model_keys = {row["id"]: (row["provider_name"], row["display_name"]) for row in models}
    model_entries = [
        {"provider": provider_names[row["provider_id"]],
         **{column: _export_value(column, row.get(column)) for column in MODEL_EXPORT_COLUMNS}}
        for row in models
    ]

    persona_entries = []
    for row in db.get_personas():
        entry = {column: row.get(column) for column in PERSONA_EXPORT_COLUMNS}
        entry["variables"] = entry["variables"] or []
        default = model_keys.get(row.get("default_model_id"))
        entry["default_model"] = {"provider": default[0], "display_name": default[1]} if default else None
        persona_entries.append(entry)

    log.info(f"Exported catalog: {len(provider_entries)} providers, {len(model_entries)} models, "
             f"{len(persona_entries)} personas (keys {'included' if include_keys else 'left out'})")
    return {
        "version": CATALOG_FILE_VERSION,
        "providers": provider_entries,
        "models": model_entries,
        "personas": persona_entries,
    }


# =========================================================================
# Import
# =========================================================================

def _validation_message(error: ValidationError, fields_to_keys: dict) -> str:
    """A Pydantic error with the file's snake_case key names."""
    parts = []
    for item in error.errors():
        location = [fields_to_keys.get(str(part), str(part)) for part in item["loc"]]
        parts.append(f"{'.'.join(location) or 'entry'}: {item['msg']}")
    return "; ".join(parts)


def _fields(entry: dict, keys: dict, label: str, errors: list) -> dict:
    """
    Map an entry's file keys to API fields; unknown keys are reported in errors and ignored.
    """
    fields = {}
    for key, value in entry.items():
        if key not in keys:
            errors.append(f"{label}: unknown key '{key}' ignored")
        elif keys[key] is not None:
            fields[keys[key]] = value
    return fields


def _upsert(existing: Optional[dict], create_model, update_model, create, update, fields: dict,
            counts: ImportCounts, fields_to_keys: dict) -> None:
    """Validate an entry with the API models and create or update it."""
    try:
        if existing:
            update(existing["id"], update_model(**fields))
            counts.updated += 1
        else:
            create(create_model(**fields))
            counts.created += 1
    except ValidationError as e:
        raise CatalogError(_validation_message(e, fields_to_keys)) from e


def _label(section: str, index: int, entry) -> str:
    """Entry label for messages, e.g. "models[3] (Kimi K3)"."""
    if isinstance(entry, dict):
        name = entry.get("name") or entry.get("display_name")
        if name:
            return f"{section}[{index}] ({name})"
    return f"{section}[{index}]"


def _import_provider(entry: dict, label: str, result: ImportResult) -> None:
    fields = _fields(entry, PROVIDER_KEYS, label, result.errors)
    name = str(entry.get("name") or "").strip()
    if not name:
        raise CatalogError("name is required")
    fields["name"] = name
    existing = db.get_llm_provider_by_name(name)
    _upsert(existing, ProviderCreate, ProviderUpdate, service.create_provider, service.update_provider,
            fields, result.providers, {v: k for k, v in PROVIDER_KEYS.items() if v})


def _import_model(entry: dict, label: str, result: ImportResult) -> None:
    fields = _fields(entry, MODEL_KEYS, label, result.errors)
    provider_name = str(entry.get("provider") or "").strip()
    display_name = str(entry.get("display_name") or "").strip()
    if not provider_name or not display_name:
        raise CatalogError("provider and display_name are required")
    provider = db.get_llm_provider_by_name(provider_name)
    if not provider:
        raise CatalogError(f"provider '{provider_name}' not found")
    fields["providerId"] = provider["id"]
    fields["displayName"] = display_name
    existing = db.get_llm_model_by_name(provider["id"], display_name)
    _upsert(existing, ModelCreate, ModelUpdate, service.create_model, service.update_model,
            fields, result.models, {v: k for k, v in MODEL_KEYS.items() if v})


def _import_persona(entry: dict, label: str, result: ImportResult) -> None:
    fields = _fields(entry, PERSONA_KEYS, label, result.errors)
    name = str(entry.get("name") or "").strip()
    if not name:
        raise CatalogError("name is required")
    fields["name"] = name

    # The default model is referenced by provider and display name
    if "default_model" in entry:
        reference = entry["default_model"]
        if reference is None:
            fields["defaultModelId"] = None
        elif isinstance(reference, dict) and reference.get("provider") and reference.get("display_name"):
            provider = db.get_llm_provider_by_name(str(reference["provider"]).strip())
            model = db.get_llm_model_by_name(provider["id"], str(reference["display_name"]).strip()) if provider else None
            if model:
                fields["defaultModelId"] = model["id"]
            else:
                result.errors.append(
                    f"{label}: default_model '{reference['display_name']}' of '{reference['provider']}' "
                    "not found, left unchanged"
                )
        else:
            result.errors.append(f"{label}: default_model must be {{\"provider\", \"display_name\"}} or null, ignored")

    existing = db.get_persona_by_name(name)
    _upsert(existing, PersonaCreate, PersonaUpdate, service.create_persona, service.update_persona,
            fields, result.personas, {v: k for k, v in PERSONA_KEYS.items() if v})


def import_catalog(data: dict) -> ImportResult:
    """
    Import a catalog file: upsert providers, then models, then personas.

    Each entry is validated and saved on its own; a bad entry is reported in
    errors and the others are still imported.

    Args:
        data: The parsed catalog file.

    Returns:
        Created and updated counts per section, and the errors.

    Raises:
        CatalogError: If the file itself is malformed (not an object, wrong
            version, sections that are not lists).
    """
    if not isinstance(data, dict):
        raise CatalogError("The catalog file must be a JSON object")
    version = data.get("version", CATALOG_FILE_VERSION)
    if version != CATALOG_FILE_VERSION:
        raise CatalogError(f"Unsupported catalog file version {version!r} (expected {CATALOG_FILE_VERSION})")
    for section in ("providers", "models", "personas"):
        if data.get(section) is not None and not isinstance(data[section], list):
            raise CatalogError(f"'{section}' must be a list")

    result = ImportResult(providers=ImportCounts(), models=ImportCounts(), personas=ImportCounts())
    for key in data:
        if key not in ("version", "providers", "models", "personas"):
            result.errors.append(f"unknown top-level key '{key}' ignored")

    for section, importer in (
        ("providers", _import_provider),
        ("models", _import_model),
        ("personas", _import_persona),
    ):
        for index, entry in enumerate(data.get(section) or []):
            label = _label(section, index, entry)
            try:
                if not isinstance(entry, dict):
                    raise CatalogError("must be an object")
                importer(entry, label, result)
            except (CatalogError, crypto.CatalogSecretError) as e:
                result.errors.append(f"{label}: {e}")

    log.info(
        f"Imported catalog: providers {result.providers.created} created / {result.providers.updated} updated, "
        f"models {result.models.created} / {result.models.updated}, "
        f"personas {result.personas.created} / {result.personas.updated}, {len(result.errors)} error(s)"
    )
    return result


# =========================================================================
# Seeding
# =========================================================================

def resolve_catalog_path(path: str | Path) -> Path:
    """A catalog file path; relative paths are resolved against the repository root."""
    path = Path(path)
    return path if path.is_absolute() else REPO_ROOT / path


def seed_from_file(path: str | Path) -> ImportResult:
    """
    Import a catalog file from disk (MODEL_CATALOG_FILE).

    Args:
        path: The JSON file; relative paths are resolved against the repository root.

    Returns:
        The import result.

    Raises:
        CatalogError: If the file is missing, not valid JSON or malformed.
    """
    resolved = resolve_catalog_path(path)
    if not resolved.is_file():
        raise CatalogError(f"Catalog file not found: {resolved}")
    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise CatalogError(f"Catalog file {resolved} is not valid JSON: {e}") from e

    log.info(f"Seeding the model catalog from {resolved}")
    result = import_catalog(data)
    for error in result.errors:
        log.warning(f"Catalog file {resolved.name}: {error}")
    return result
