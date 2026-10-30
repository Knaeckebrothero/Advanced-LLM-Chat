"""
The catalog file: JSON import, export and seeding from MODEL_CATALOG_FILE.

Format (snake_case keys matching the database columns, see docs/model_catalog_api.md):

    {
      "version": 1,
      "providers": [{"name", "kind", "base_url", "api_key_env", "privacy_tier", "currency", ...}],
      "models":    [{"provider": "<provider name>", "display_name", "model_id", ...}],
      "personas":  [{"name", "system_prompt", "variables", "tools", ...}]
    }

Seeding (seed_from_file(), run by app_init on every start) treats the file as
the source of the providers: they are created or replaced by name. Models (by
provider and display_name) and personas (by name) are only created when
missing; existing ones are left untouched, so edits made in the app survive
every deploy.

The import in the app (import_catalog()) upserts models and personas: a new
entry gets defaults for the keys it leaves out, an existing entry only changes
the keys that are present, and null clears optional columns. Provider entries
are ignored, since providers come from the server's catalog file.

Neither deletes anything. Export writes every column; API keys are never part
of it, providers only name their key variable (api_key_env).

Validation is the same as in the admin API (backend/catalog/service.py).
"""
import json
import os
import re
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from backend.catalog import service
from backend.catalog.service import CatalogError
from backend.database import db
from backend.models.catalog import (
    ImportCounts,
    ImportResult,
    ModelCreate,
    ModelUpdate,
    PersonaCreate,
    PersonaUpdate,
    ProviderBase,
)

log = logging.getLogger(__name__)

CATALOG_FILE_VERSION = 1

# Relative MODEL_CATALOG_FILE paths are resolved against the repository root
REPO_ROOT = Path(__file__).resolve().parents[2]

# File key -> API field, per section. Keys not listed are reported and ignored.
PROVIDER_KEYS = {column: field for field, column in service.PROVIDER_FIELDS.items()}
MODEL_KEYS = {column: field for field, column in service.MODEL_FIELDS.items() if column != "provider_id"}
MODEL_KEYS["provider"] = None  # Natural key, resolved to providerId
PERSONA_KEYS = {column: field for field, column in service.PERSONA_FIELDS.items()}

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
    "name", "description", "system_prompt", "variables", "tools", "available_to_guests",
    "enabled", "sort_order",
]
NUMERIC_COLUMNS = {"temperature", "top_p", "input_price_per_mtok", "output_price_per_mtok"}

# Reported once by an import whose file has provider entries
PROVIDERS_IGNORED = "providers ignored: providers come from the server's catalog file"


@dataclass
class SeedCounts:
    """What seeding did with the entries of one section."""
    created: int = 0
    updated: int = 0  # Providers only
    kept: int = 0  # Existing models and personas, left unchanged


@dataclass
class SeedResult:
    """Result of seeding from MODEL_CATALOG_FILE (logged by app_init, not part of the API)."""
    providers: SeedCounts = field(default_factory=SeedCounts)
    models: SeedCounts = field(default_factory=SeedCounts)
    personas: SeedCounts = field(default_factory=SeedCounts)
    errors: list[str] = field(default_factory=list)


# =========================================================================
# Export
# =========================================================================

def _export_value(column: str, value):
    """Column value as JSON: NUMERIC/REAL as float."""
    if column in NUMERIC_COLUMNS and value is not None:
        return float(value)
    return value


def export_catalog() -> dict:
    """
    The whole catalog in the catalog file format, usable as MODEL_CATALOG_FILE.

    Returns:
        The catalog file as a dict.
    """
    providers = db.get_llm_providers()
    provider_names = {row["id"]: row["name"] for row in providers}
    provider_entries = [{column: row.get(column) for column in PROVIDER_EXPORT_COLUMNS} for row in providers]

    models = sorted(db.get_llm_models(), key=lambda m: (m["provider_name"], m["sort_order"] or 0, m["display_name"]))
    model_entries = [
        {"provider": provider_names[row["provider_id"]],
         **{column: _export_value(column, row.get(column)) for column in MODEL_EXPORT_COLUMNS}}
        for row in models
    ]

    persona_entries = []
    for row in db.get_personas():
        entry = {column: row.get(column) for column in PERSONA_EXPORT_COLUMNS}
        entry["variables"] = entry["variables"] or []
        persona_entries.append(entry)

    log.info(f"Exported catalog: {len(provider_entries)} providers, {len(model_entries)} models, "
             f"{len(persona_entries)} personas")
    return {
        "version": CATALOG_FILE_VERSION,
        "providers": provider_entries,
        "models": model_entries,
        "personas": persona_entries,
    }


# =========================================================================
# Entries (shared by import and seeding)
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


def _save(existing: Optional[dict], create_model, update_model, create, update, fields: dict,
          fields_to_keys: dict, *, create_only: bool) -> str:
    """
    Validate an entry with the API models and create or update it.

    Returns:
        "created", "updated", or "kept" for an existing entry with create_only.
    """
    if existing and create_only:
        return "kept"
    try:
        if existing:
            update(existing["id"], update_model(**fields))
            return "updated"
        create(create_model(**fields))
        return "created"
    except ValidationError as e:
        raise CatalogError(_validation_message(e, fields_to_keys)) from e


def _label(section: str, index: int, entry) -> str:
    """Entry label for messages, e.g. "models[3] (Kimi K3)"."""
    if isinstance(entry, dict):
        name = entry.get("name") or entry.get("display_name")
        if name:
            return f"{section}[{index}] ({name})"
    return f"{section}[{index}]"


def _seed_provider(entry: dict, label: str, errors: list) -> str:
    """Create or replace a provider from a seed file entry."""
    if "api_key" in entry:
        entry = {key: value for key, value in entry.items() if key != "api_key"}
        errors.append(f"{label}: api_key ignored: keys are only read from the environment variable "
                      "named in api_key_env")
    fields = _fields(entry, PROVIDER_KEYS, label, errors)
    name = str(entry.get("name") or "").strip()
    if not name:
        raise CatalogError("name is required")
    fields["name"] = name
    try:
        data = ProviderBase(**fields)
    except ValidationError as e:
        raise CatalogError(_validation_message(e, {v: k for k, v in PROVIDER_KEYS.items()})) from e
    return "created" if service.upsert_provider(data) else "updated"


def _import_model(entry: dict, label: str, errors: list, *, create_only: bool) -> str:
    """Create or update (unless create_only) a model; its provider must exist."""
    fields = _fields(entry, MODEL_KEYS, label, errors)
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
    return _save(existing, ModelCreate, ModelUpdate, service.create_model, service.update_model,
                 fields, {v: k for k, v in MODEL_KEYS.items() if v}, create_only=create_only)


def _import_persona(entry: dict, label: str, errors: list, *, create_only: bool) -> str:
    """Create or update (unless create_only) a persona."""
    fields = _fields(entry, PERSONA_KEYS, label, errors)
    name = str(entry.get("name") or "").strip()
    if not name:
        raise CatalogError("name is required")
    fields["name"] = name
    existing = db.get_persona_by_name(name)
    return _save(existing, PersonaCreate, PersonaUpdate, service.create_persona, service.update_persona,
                 fields, {v: k for k, v in PERSONA_KEYS.items()}, create_only=create_only)


def _check_file(data) -> list[str]:
    """
    Check the structure of a catalog file.

    Returns:
        Messages about unknown top-level keys.

    Raises:
        CatalogError: If the file is not an object, has another version, or a
            section is not a list.
    """
    if not isinstance(data, dict):
        raise CatalogError("The catalog file must be a JSON object")
    version = data.get("version", CATALOG_FILE_VERSION)
    if version != CATALOG_FILE_VERSION:
        raise CatalogError(f"Unsupported catalog file version {version!r} (expected {CATALOG_FILE_VERSION})")
    for section in ("providers", "models", "personas"):
        if data.get(section) is not None and not isinstance(data[section], list):
            raise CatalogError(f"'{section}' must be a list")
    return [f"unknown top-level key '{key}' ignored" for key in data
            if key not in ("version", "providers", "models", "personas")]


def _run_section(data: dict, section: str, importer, counts, errors: list, **options) -> None:
    """
    Save the entries of one section on their own; a bad entry is reported in
    errors and the others are still saved.
    """
    for index, entry in enumerate(data.get(section) or []):
        label = _label(section, index, entry)
        try:
            if not isinstance(entry, dict):
                raise CatalogError("must be an object")
            outcome = importer(entry, label, errors, **options)
            setattr(counts, outcome, getattr(counts, outcome) + 1)
        except CatalogError as e:
            errors.append(f"{label}: {e}")


# =========================================================================
# Import (admin UI)
# =========================================================================

def import_catalog(data: dict) -> ImportResult:
    """
    Import a catalog file uploaded in the app: upsert models, then personas.

    Provider entries are ignored (one message in errors); a model whose
    provider is not in the catalog is reported in errors.

    Args:
        data: The parsed catalog file.

    Returns:
        Created and updated counts per section, and the errors.

    Raises:
        CatalogError: If the file itself is malformed (not an object, wrong
            version, sections that are not lists).
    """
    result = ImportResult(models=ImportCounts(), personas=ImportCounts(), errors=_check_file(data))
    if data.get("providers"):
        result.errors.append(PROVIDERS_IGNORED)
    _run_section(data, "models", _import_model, result.models, result.errors, create_only=False)
    _run_section(data, "personas", _import_persona, result.personas, result.errors, create_only=False)

    log.info(
        f"Imported catalog: models {result.models.created} created / {result.models.updated} updated, "
        f"personas {result.personas.created} / {result.personas.updated}, {len(result.errors)} error(s)"
    )
    return result


# =========================================================================
# Seeding (MODEL_CATALOG_FILE)
# =========================================================================

def resolve_catalog_path(path: str | Path) -> Path:
    """A catalog file path; relative paths are resolved against the repository root."""
    path = Path(path)
    return path if path.is_absolute() else REPO_ROOT / path


# ${VAR} in a provider's base_url, filled from the environment when seeding
ENV_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _apply_environment(data: dict) -> list[str]:
    """
    Prepare the providers of a seed file for this server's environment.

    - ${VAR} placeholders in a provider's base_url are replaced with environment
      values. This keeps private addresses (e.g. a homelab model router) out of a
      committed catalog file. A provider whose variable is unset is skipped,
      together with its models.
    - A provider whose api_key_env variable is unset is saved disabled, so the
      picker doesn't offer models that can't answer. It is enabled again on the
      next seed once the key is set, unless the file sets `enabled` itself.

    This only runs when seeding from MODEL_CATALOG_FILE, never for files uploaded
    in the UI, so an upload can't read the server's environment.

    Args:
        data: The parsed catalog file; changed in place.

    Returns:
        Messages about skipped and disabled providers.
    """
    if not isinstance(data, dict) or not isinstance(data.get("providers"), list):
        return []

    messages = []
    skipped = set()
    providers = []
    for entry in data["providers"]:
        base_url = entry.get("base_url") if isinstance(entry, dict) else None
        if isinstance(base_url, str):
            missing = [name for name in ENV_PLACEHOLDER.findall(base_url) if not os.getenv(name)]
            if missing:
                skipped.add(entry.get("name"))
                messages.append(f"provider '{entry.get('name')}' skipped: {', '.join(missing)} not set")
                continue
            entry["base_url"] = ENV_PLACEHOLDER.sub(lambda match: os.environ[match.group(1)], base_url)
        key_env = entry.get("api_key_env") if isinstance(entry, dict) else None
        if key_env and "enabled" not in entry:
            entry["enabled"] = bool(os.getenv(key_env, "").strip())
            if not entry["enabled"]:
                messages.append(f"provider '{entry.get('name')}' disabled: {key_env} not set")
        providers.append(entry)
    data["providers"] = providers

    if skipped and isinstance(data.get("models"), list):
        data["models"] = [
            entry for entry in data["models"]
            if not (isinstance(entry, dict) and entry.get("provider") in skipped)
        ]
    return messages


def seed_catalog(data: dict) -> SeedResult:
    """
    Seed the catalog from a parsed catalog file: create or replace the
    providers, then create the models and personas that don't exist yet.

    Existing models and personas are kept as they are (counted as kept), so
    changes made in the app are never overwritten. Each entry is saved on its
    own; a bad entry is reported in errors and the others are still saved.

    Args:
        data: The parsed catalog file (after _apply_environment()).

    Returns:
        The counts per section and the errors.

    Raises:
        CatalogError: If the file itself is malformed.
    """
    result = SeedResult(errors=_check_file(data))
    _run_section(data, "providers", _seed_provider, result.providers, result.errors)
    _run_section(data, "models", _import_model, result.models, result.errors, create_only=True)
    _run_section(data, "personas", _import_persona, result.personas, result.errors, create_only=True)

    log.info(
        f"Seeded catalog: providers {result.providers.created} created / {result.providers.updated} updated, "
        f"models {result.models.created} created / {result.models.kept} kept, "
        f"personas {result.personas.created} / {result.personas.kept}, {len(result.errors)} error(s)"
    )
    return result


def seed_from_file(path: str | Path) -> SeedResult:
    """
    Seed the catalog from a file on disk (MODEL_CATALOG_FILE), see seed_catalog().

    Args:
        path: The JSON file; relative paths are resolved against the repository root.

    Returns:
        The seed result.

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
    file_providers = {
        str(entry.get("name") or "").strip()
        for entry in (data.get("providers") or [] if isinstance(data, dict) else [])
        if isinstance(entry, dict)
    }
    for message in _apply_environment(data):
        log.warning(f"Catalog file {resolved.name}: {message}")
    result = seed_catalog(data)
    for error in result.errors:
        log.warning(f"Catalog file {resolved.name}: {error}")

    # Seeding never deletes, so a provider removed from the file stays (with its models)
    for row in db.get_llm_providers():
        if row["name"] not in file_providers:
            log.warning(f"Provider '{row['name']}' is in the database but not in {resolved.name}; "
                        "it is left as it is (delete it in the database to remove it)")
    return result
