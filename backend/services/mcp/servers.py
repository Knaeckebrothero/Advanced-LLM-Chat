"""
MCP server definitions: validation for the API and the catalog file, the API views, and the
resolved definition a connection is made with (ServerSpec).

Admin servers (user_id NULL) may use ${VAR} in their URL, header values and stdio environment,
filled from the backend's environment when connecting; the variable must look like a secret
(ENV_REF_PATTERN), so a definition can't send other settings anywhere. Users' own servers never
get variables filled, and their header values are stored encrypted and never returned.
"""
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.exc import IntegrityError

from backend.config import MCP_ENABLED, MCP_STDIO_ENABLED, MCP_USER_SERVERS
from backend.models.mcp import McpServerCreate, McpServerOut, McpServerUpdate
from backend.security.secrets import NO_KEY_REASON, SecretUnavailable, decrypt_json, encrypt_json, encryption_available
from backend.services.mcp import store

log = logging.getLogger(__name__)

SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,23}$")
# ${VAR} references in admin servers; the name must end like a secret's or an API address's
ENV_REF = re.compile(r"\$\{([^}]*)\}")
ENV_REF_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(_KEY|_TOKEN|_SECRET|_API)$")
SECRET_ENV_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(_KEY|_TOKEN|_SECRET)$")
HEADER_NAME = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]+$")
MAX_USER_SERVERS = 25
MAX_TEXT = 2000


class McpError(Exception):
    """Invalid input (HTTP 400)."""
    status_code = 400


class McpNotFound(McpError):
    status_code = 404


class McpForbidden(McpError):
    status_code = 403


class McpConflict(McpError):
    status_code = 409


class McpUnavailable(McpError):
    """The configuration switches the feature off (HTTP 503)."""
    status_code = 503


def config_reason() -> Optional[str]:
    """Why MCP is off altogether, or None."""
    return None if MCP_ENABLED else "MCP_ENABLED is off"


def user_servers_reason() -> Optional[str]:
    """Why users can't use their own servers, or None."""
    if not MCP_ENABLED:
        return "MCP_ENABLED is off"
    if not MCP_USER_SERVERS:
        return "MCP_USER_SERVERS is off"
    return None


# =========================================================================
# Validation
# =========================================================================

def make_slug(name: str) -> str:
    """A slug from a name: "My GitHub" -> "my_github"."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if not slug or not slug[0].isalpha():
        slug = f"mcp_{slug}".rstrip("_")
    return slug[:24].rstrip("_")


def _text(value: Optional[str], label: str, *, required: bool = False, limit: int = MAX_TEXT) -> Optional[str]:
    value = value.strip() if isinstance(value, str) else value
    if not value:
        if required:
            raise McpError(f"{label} must not be empty")
        return None
    if len(value) > limit:
        raise McpError(f"{label} is too long (at most {limit} characters)")
    return value


def _check_env_refs(value: str, label: str) -> None:
    for name in ENV_REF.findall(value):
        if not ENV_REF_PATTERN.match(name):
            raise McpError(f"{label}: ${{{name}}} is not allowed; a variable must end in _KEY, _TOKEN, _SECRET "
                           f"or _API")


def _check_url(url: str, admin: bool) -> None:
    if admin and url.startswith("${"):
        _check_env_refs(url, "url")
        return
    if not re.match(r"^https?://[^\s/]+", url, re.IGNORECASE):
        raise McpError("url must start with http:// or https://")
    if admin:
        _check_env_refs(url, "url")


def _check_headers(headers: dict, admin: bool) -> dict:
    result = {}
    for name, value in headers.items():
        name = name.strip()
        if not HEADER_NAME.match(name):
            raise McpError(f"Invalid header name '{name}'")
        if name.lower() in ("host", "content-length", "content-type", "accept", "mcp-session-id",
                            "mcp-protocol-version"):
            raise McpError(f"The header '{name}' is set by the client")
        value = (value or "").strip()
        if "\n" in value or "\r" in value:
            raise McpError(f"The header '{name}' must be one line")
        if admin:
            _check_env_refs(value, f"header '{name}'")
        result[name] = value
    return result


def _check_env(env: dict) -> dict:
    result = {}
    for name, value in env.items():
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
            raise McpError(f"Invalid environment variable name '{name}'")
        _check_env_refs(value or "", f"env {name}")
        result[name] = value or ""
    return result


def _validated(values: dict, existing: Optional[dict], admin_server: bool) -> dict:
    """Check a server's merged columns; returns the values to write (changed columns only)."""
    merged = {**(existing or {}), **values}
    transport = merged.get("transport") or "http"
    auth = merged.get("auth") or "none"

    if transport == "stdio":
        if not admin_server:
            raise McpForbidden("Only admins can add stdio servers")
        # Defining or changing a command needs the switch; renaming or disabling one doesn't
        empty = {"args": [], "env": {}}
        if not MCP_STDIO_ENABLED and (existing is None or any(
                key in values and (values[key] or empty.get(key)) != (existing.get(key) or empty.get(key))
                for key in ("transport", "command", "args", "env"))):
            raise McpUnavailable("stdio servers are turned off on this server (MCP_STDIO_ENABLED)")
        if not merged.get("command"):
            raise McpError("A stdio server needs a command")
        if auth == "oauth":
            raise McpError("OAuth works only with http and sse servers")
    else:
        if not merged.get("url"):
            raise McpError("An http or sse server needs a url")
        _check_url(merged["url"], admin_server)

    if not admin_server:
        for key in ("oauth_client_secret_env",):
            if values.get(key):
                raise McpForbidden("Only admin servers can read a client secret from the environment")
    if values.get("oauth_client_secret_env"):
        if not SECRET_ENV_PATTERN.match(values["oauth_client_secret_env"]):
            raise McpError("oauthClientSecretEnv must name a variable ending in _KEY, _TOKEN or _SECRET")
    return values


def _common_columns(data, *, partial: bool) -> dict:
    """The columns of a create or update request that both kinds of servers share."""
    dumped = data.model_dump(exclude_unset=partial)
    values = {}
    if "name" in dumped:
        values["name"] = _text(dumped["name"], "name", required=True, limit=100)
    if "description" in dumped:
        values["description"] = _text(dumped["description"], "description")
    if "transport" in dumped and dumped["transport"] is not None:
        values["transport"] = dumped["transport"]
    if "url" in dumped:
        values["url"] = _text(dumped["url"], "url")
    if "command" in dumped:
        values["command"] = _text(dumped["command"], "command", limit=500)
    if "args" in dumped and dumped["args"] is not None:
        values["args"] = [str(arg) for arg in dumped["args"]]
    if "env" in dumped and dumped["env"] is not None:
        values["env"] = _check_env(dumped["env"])
    if "auth" in dumped and dumped["auth"] is not None:
        values["auth"] = dumped["auth"]
    if "oauthClientId" in dumped:
        values["oauth_client_id"] = _text(dumped["oauthClientId"], "oauthClientId", limit=500)
    if "oauthClientSecretEnv" in dumped:
        values["oauth_client_secret_env"] = _text(dumped["oauthClientSecretEnv"], "oauthClientSecretEnv", limit=200)
    if "oauthScopes" in dumped:
        values["oauth_scopes"] = _text(dumped["oauthScopes"], "oauthScopes", limit=1000)
    if "tools" in dumped:
        tools = dumped["tools"]
        values["tools"] = None if tools is None else list(dict.fromkeys(str(t) for t in tools))
    if "enabled" in dumped and dumped["enabled"] is not None:
        values["enabled"] = dumped["enabled"]
    return values


def _client_changed(values: dict, existing: Optional[dict]) -> bool:
    """Whether a change makes a dynamically registered client (or the signed-in tokens) invalid."""
    if existing is None:
        return False
    return any(key in values and values[key] != existing.get(key)
               for key in ("url", "oauth_client_id", "transport"))


def _write(operation, slug: str):
    try:
        return operation()
    except IntegrityError as e:
        if getattr(e.orig, "pgcode", None) == "23505":
            raise McpConflict(f"A server with the slug '{slug}' exists already") from e
        raise McpError(f"The server could not be saved: {e.orig}") from e


def _slug_for(data: McpServerCreate) -> str:
    slug = (data.slug or "").strip() or make_slug(data.name or "")
    if not SLUG_PATTERN.match(slug):
        raise McpError("slug must start with a letter and use only a-z, 0-9 and _ (at most 24 characters)")
    return slug


def create_admin_server(data: McpServerCreate) -> dict:
    values = _common_columns(data, partial=False)
    values["slug"] = _slug_for(data)
    if data.headers is not None:
        values["headers"] = _check_headers(data.headers, admin=True)
    values["available_to_guests"] = data.availableToGuests
    values["sort_order"] = data.sortOrder
    values["user_id"] = None
    values = _validated(values, None, admin_server=True)
    return _write(lambda: store.create_server(values), values["slug"])


def update_admin_server(server_id: int, data: McpServerUpdate) -> tuple[dict, dict]:
    """Returns (old row, new row)."""
    existing = store.get_server(server_id)
    if existing is None or existing["user_id"] is not None:
        raise McpNotFound(f"MCP server {server_id} not found")
    values = _common_columns(data, partial=True)
    dumped = data.model_dump(exclude_unset=True)
    if "headers" in dumped:
        values["headers"] = None if dumped["headers"] is None else _check_headers(dumped["headers"], admin=True)
    if dumped.get("availableToGuests") is not None:
        values["available_to_guests"] = dumped["availableToGuests"]
    if dumped.get("sortOrder") is not None:
        values["sort_order"] = dumped["sortOrder"]
    values = _validated(values, existing, admin_server=True)
    if _client_changed(values, existing):
        values["oauth_client_encrypted"] = None
    row = _write(lambda: store.update_server(server_id, values), existing["slug"])
    return existing, row


def create_user_server(user_id: int, data: McpServerCreate) -> dict:
    reason = user_servers_reason()
    if reason:
        raise McpUnavailable(f"Own MCP servers are turned off on this server ({reason})")
    if store.count_user_servers(user_id) >= MAX_USER_SERVERS:
        raise McpError(f"At most {MAX_USER_SERVERS} servers per user")
    values = _common_columns(data, partial=False)
    values["slug"] = _slug_for(data)
    values["user_id"] = user_id
    if data.headers:
        values["headers_encrypted"] = _encrypt_headers(_check_headers(data.headers, admin=False))
    values = _validated(values, None, admin_server=False)
    return _write(lambda: store.create_server(values), values["slug"])


def update_user_server(user_id: int, server_id: int, data: McpServerUpdate) -> tuple[dict, dict]:
    existing = own_server(user_id, server_id)
    values = _common_columns(data, partial=True)
    dumped = data.model_dump(exclude_unset=True)
    if "headers" in dumped:
        if not dumped["headers"]:
            values["headers_encrypted"] = None
        else:
            stored = stored_headers(existing)
            headers = _check_headers(dumped["headers"], admin=False)
            # An empty value keeps the stored one
            headers = {name: value or stored.get(name, "") for name, value in headers.items()}
            values["headers_encrypted"] = _encrypt_headers({k: v for k, v in headers.items() if v})
    values = _validated(values, existing, admin_server=False)
    if _client_changed(values, existing):
        values["oauth_client_encrypted"] = None
    row = _write(lambda: store.update_server(server_id, values), existing["slug"])
    return existing, row


def own_server(user_id: int, server_id: int) -> dict:
    row = store.get_server(server_id)
    if row is None or row["user_id"] != user_id:
        raise McpNotFound(f"MCP server {server_id} not found")
    return row


def _encrypt_headers(headers: dict) -> Optional[str]:
    if not headers:
        return None
    if not encryption_available():
        raise McpUnavailable(f"Headers can't be stored: {NO_KEY_REASON}")
    return encrypt_json(headers)


def stored_headers(row: dict) -> dict:
    """A user's server's header values (decrypted); {} if none or unreadable."""
    if not row.get("headers_encrypted"):
        return {}
    try:
        return decrypt_json(row["headers_encrypted"]) or {}
    except SecretUnavailable as e:
        log.warning(f"MCP server {row['id']}: {e}")
        return {}


def check_persona_servers(slugs: Optional[list]) -> Optional[list[str]]:
    """An agent's mcpServers: known admin server slugs without duplicates (raises McpError)."""
    if slugs is None:
        return None
    slugs = list(dict.fromkeys(str(slug) for slug in slugs))
    known = {row["slug"] for row in store.admin_servers_by_slug(slugs)}
    unknown = [slug for slug in slugs if slug not in known]
    if unknown:
        raise McpError(f"Unknown MCP server(s): {', '.join(unknown)}")
    return slugs


# =========================================================================
# Resolving a definition
# =========================================================================

def _fill_env(value: str, missing: list) -> str:
    def replace(match):
        name = match.group(1)
        if not ENV_REF_PATTERN.match(name):
            missing.append(f"${{{name}}} is not allowed")
            return ""
        found = os.getenv(name)
        if not found:
            missing.append(f"{name} is not set")
            return ""
        return found
    return ENV_REF.sub(replace, value)


@dataclass
class ServerSpec:
    """A server as a connection needs it: variables filled, secrets decrypted."""
    id: int
    slug: str
    name: str
    description: Optional[str]
    transport: str
    auth: str
    url: Optional[str] = None
    headers: dict = field(default_factory=dict)
    command: Optional[str] = None
    args: list = field(default_factory=list)
    env: dict = field(default_factory=dict)
    owner_id: Optional[int] = None  # None: an admin server
    tools: Optional[list] = None
    row: dict = field(default_factory=dict, repr=False)

    @property
    def shared(self) -> bool:
        return self.owner_id is None

    def fingerprint(self) -> str:
        """Changes whenever the connection must be made again."""
        data = [self.transport, self.auth, self.url, self.headers, self.command, self.args, self.env]
        return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def unavailable_reason(row: dict) -> Optional[str]:
    """Why a server can't be used now (configuration), or None."""
    reason = config_reason()
    if reason:
        return reason
    if row["user_id"] is not None:
        reason = user_servers_reason()
        if reason:
            return reason
    if row["transport"] == "stdio" and not MCP_STDIO_ENABLED:
        return "MCP_STDIO_ENABLED is off"
    needs_key = row["auth"] == "oauth" or (row["user_id"] is not None and row.get("headers_encrypted"))
    if needs_key and not encryption_available():
        return NO_KEY_REASON
    try:
        resolve(row)
    except McpUnavailable as e:
        return str(e)
    return None


def resolve(row: dict) -> ServerSpec:
    """The definition to connect with. Raises McpUnavailable for unset variables."""
    admin_server = row["user_id"] is None
    missing: list[str] = []
    url = row.get("url")
    headers = dict(row.get("headers") or {}) if admin_server else stored_headers(row)
    env = dict(row.get("env") or {})
    if admin_server:
        url = _fill_env(url, missing) if url else url
        headers = {name: _fill_env(value, missing) for name, value in headers.items()}
        env = {name: _fill_env(value, missing) for name, value in env.items()}
    if row.get("auth") != "headers":
        headers = {}
    if missing:
        raise McpUnavailable(", ".join(dict.fromkeys(missing)))
    return ServerSpec(
        id=row["id"], slug=row["slug"], name=row["name"], description=row.get("description"),
        transport=row["transport"], auth=row["auth"], url=url, headers=headers,
        command=row.get("command"), args=list(row.get("args") or []), env=env,
        owner_id=row["user_id"], tools=row.get("tools"), row=row,
    )


# =========================================================================
# API view
# =========================================================================

def server_out(row: dict, connected: Optional[set] = None, *, full: bool = True) -> McpServerOut:
    """
    The API view of a server.

    Args:
        connected: The server ids the current user has signed in to (for OAuth servers).
        full: False for an admin server shown to a user who isn't an admin (to sign in to it):
            without headers, environment, command and OAuth client.
    """
    admin_server = row["user_id"] is None
    header_names = list((row.get("headers") or {}).keys()) if admin_server else list(stored_headers(row).keys())
    if not full:
        return McpServerOut(
            id=row["id"], shared=admin_server, name=row["name"], slug=row["slug"],
            description=row.get("description"), transport=row["transport"], url=row.get("url"), auth=row["auth"],
            enabled=row.get("enabled") is not False,
            connected=(row["id"] in connected) if row["auth"] == "oauth" and connected is not None else None,
            unavailableReason=unavailable_reason(row), createdAt=row.get("created_at"), updatedAt=row.get("updated_at"),
        )
    return McpServerOut(
        id=row["id"],
        shared=admin_server,
        name=row["name"],
        slug=row["slug"],
        description=row.get("description"),
        transport=row["transport"],
        url=row.get("url"),
        command=row.get("command"),
        args=list(row.get("args") or []),
        env=dict(row.get("env") or {}) if admin_server else {},
        auth=row["auth"],
        headers=dict(row.get("headers") or {}) if admin_server else None,
        headerNames=header_names,
        oauthClientId=row.get("oauth_client_id"),
        oauthClientSecretEnv=row.get("oauth_client_secret_env") if admin_server else None,
        oauthScopes=row.get("oauth_scopes"),
        tools=row.get("tools"),
        availableToGuests=bool(row.get("available_to_guests")) if admin_server else False,
        enabled=row.get("enabled") is not False,
        sortOrder=row.get("sort_order") or 0,
        connected=(row["id"] in connected) if row["auth"] == "oauth" and connected is not None else None,
        unavailableReason=unavailable_reason(row),
        createdAt=row.get("created_at"),
        updatedAt=row.get("updated_at"),
    )
