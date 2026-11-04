"""
The tools of MCP servers for an answer, and the test of a server (docs/mcp.md).

tools_for_answer() connects to the servers of the conversation's agent (its admin servers, plus
the user's own if the agent selects the tool group user_mcp), lists their tools and wraps each in
a Tool for the agent loop. A server that fails gives no tools but a notice, which the answer shows
as a step.
"""
import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from backend.catalog.resolver import persona_usable
from backend.config import MCP_ENABLED, MCP_MAX_RESULT_CHARS, MCP_TOOL_TIMEOUT
from backend.database import db
from backend.llm.tools import Tool, ToolError
from backend.models.mcp import McpTestResult, McpToolInfo
from backend.services.mcp import store
from backend.services.mcp.oauth import TokenAuth, guarded, has_tokens
from backend.services.mcp.pool import Connection, McpAuthRequired, McpConnectError, describe_error, pool, root_cause
from backend.services.mcp.servers import McpUnavailable, ServerSpec, resolve, unavailable_reason, user_servers_reason

log = logging.getLogger(__name__)

# OpenAI and Anthropic accept tool names of letters, digits, _ and -, up to 64 characters
TOOL_NAME_MAX = 64
DESCRIPTION_MAX = 4000

# Step titles of the notices (the frontend translates them by these strings)
UNAVAILABLE_TITLE = "MCP server unavailable"
SIGN_IN_TITLE = "Sign-in needed"


@dataclass
class Notice:
    """A server of the answer that gives no tools, and why."""
    server_id: int
    name: str
    reason: str
    auth_required: bool = False
    slug: str = ""


@dataclass
class McpToolset:
    tools: list[Tool] = field(default_factory=list)
    servers: list[dict] = field(default_factory=list)  # For the system prompt (with_mcp_servers)
    notices: list[Notice] = field(default_factory=list)

    def unavailable(self) -> list[dict]:
        """The servers without tools this time, for the system prompt."""
        return [{"name": n.name, "prefix": n.slug, "reason": n.reason} for n in self.notices]


# =========================================================================
# Which servers
# =========================================================================

def answer_servers(user: dict, conversation: Optional[dict]) -> list[dict]:
    """
    The servers of an answer: the agent's admin servers (enabled; for guests only those available
    to guests), plus the user's own enabled servers if the agent selects user_mcp (never guests).
    Without an agent, or with one the user may not use, there are none.
    """
    if not MCP_ENABLED:
        return []
    persona_id = (conversation or {}).get("persona_id")
    if persona_id is None:
        return []
    persona = db.get_persona_by_id(persona_id)
    if not persona_usable(persona, user):
        return []
    guest = bool(user.get("is_guest"))
    rows = [row for row in store.admin_servers_by_slug(list(persona.get("mcp_servers") or []))
            if row.get("enabled") is not False and (not guest or row.get("available_to_guests"))]
    groups = persona.get("tools")
    if groups is not None and "user_mcp" in groups and not guest and user_servers_reason() is None:
        rows += store.user_servers(user["user_id"], enabled_only=True)
    return rows


# =========================================================================
# Connections
# =========================================================================

def _auth_factory(spec: ServerSpec, user: dict):
    if spec.auth != "oauth":
        return None
    guarded_client = guarded(spec.row, user)
    return lambda: TokenAuth(spec.id, user["user_id"], spec.name, guarded_client)


async def connect(row: dict, user: dict, *, fresh: bool = False) -> tuple[ServerSpec, Connection]:
    """
    A connection to a server for a user.

    Raises:
        McpUnavailable: The configuration doesn't allow it (the reason).
        McpAuthRequired: OAuth without (valid) sign-in.
        McpConnectError: The server can't be reached.
    """
    reason = unavailable_reason(row)
    if reason:
        raise McpUnavailable(reason)
    spec = resolve(row)
    if spec.auth == "oauth" and not await asyncio.to_thread(has_tokens, spec.id, user["user_id"]):
        raise McpAuthRequired(f"Sign in to {spec.name} on the MCP servers page to use its tools")
    connection = await pool.get(spec, user["user_id"], guarded=guarded(row, user),
                                auth_factory=_auth_factory(spec, user), fresh=fresh)
    return spec, connection


# =========================================================================
# Tools
# =========================================================================

def tool_name(prefix: str, name: str, taken: set) -> str:
    """The registry name of an MCP tool: <prefix>__<name>, cleaned, at most 64 characters, unique."""
    base = re.sub(r"[^A-Za-z0-9_-]", "_", f"{prefix}__{name}")[:TOOL_NAME_MAX]
    candidate, number = base, 2
    while candidate in taken:
        suffix = f"_{number}"
        candidate = base[:TOOL_NAME_MAX - len(suffix)] + suffix
        number += 1
    taken.add(candidate)
    return candidate


def _parameters(schema: Any) -> dict:
    """A tool's input schema as the APIs accept it: an object schema, without $schema."""
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}
    schema = {key: value for key, value in schema.items() if key != "$schema"}
    schema["type"] = "object"
    if not isinstance(schema.get("properties"), dict):
        schema["properties"] = {}
    return schema


def _size(data: Optional[str]) -> str:
    if not data:
        return "0 KB"
    size = len(data) * 3 // 4
    return f"{size / 1024:.0f} KB" if size < 1024 * 1024 else f"{size / 1024 / 1024:.1f} MB"


def format_result(result) -> str:
    """The text the model gets from an MCP tool result."""
    parts = []
    for block in result.content or []:
        kind = getattr(block, "type", None)
        if kind == "text":
            parts.append(block.text)
        elif kind in ("image", "audio"):
            parts.append(f"[{block.mime_type}, {_size(block.data)}, not shown]")
        elif kind == "resource_link":
            label = block.title or block.name
            parts.append(f"[Resource: {label} <{block.uri}>]" + (f" {block.description}" if block.description else ""))
        elif kind == "resource":
            resource = block.resource
            text = getattr(resource, "text", None)
            if text is not None:
                parts.append(f"[Resource {resource.uri}]\n{text}")
            else:
                parts.append(f"[Resource {resource.uri}: {resource.mime_type or 'binary'}, "
                             f"{_size(getattr(resource, 'blob', None))}, not shown]")
        else:
            parts.append(json.dumps(block.model_dump(mode="json", exclude_none=True), ensure_ascii=False))
    if not parts and result.structured_content is not None:
        parts.append(json.dumps(result.structured_content, ensure_ascii=False, indent=2))
    text = "\n\n".join(part for part in parts if part)
    if len(text) > MCP_MAX_RESULT_CHARS:
        text = text[:MCP_MAX_RESULT_CHARS] + f"\n\n[... cut off: the result had {len(text)} characters]"
    return text


def _make_tool(row: dict, spec: ServerSpec, mcp_tool, name: str, user: dict) -> Tool:
    title = (mcp_tool.title or (mcp_tool.annotations.title if mcp_tool.annotations else None)
             or mcp_tool.name)
    description = (mcp_tool.description or title).strip()
    if len(description) > DESCRIPTION_MAX:
        description = description[:DESCRIPTION_MAX] + " [...]"

    async def call(**arguments):
        connection = None
        try:
            _, connection = await connect(row, user)
            result = await connection.client.call_tool(mcp_tool.name, arguments, read_timeout_seconds=MCP_TOOL_TIMEOUT)
        except McpAuthRequired as e:
            raise ToolError(str(e))
        except (McpConnectError, McpUnavailable) as e:
            raise ToolError(f"{spec.name}: {e}")
        except Exception as e:
            cause = root_cause(e)
            if isinstance(cause, McpAuthRequired):
                raise ToolError(str(cause))
            if connection is not None and getattr(connection.auth, "failed", None):
                raise ToolError(connection.auth.failed)
            log.warning(f"MCP tool {spec.slug}/{mcp_tool.name} failed: {describe_error(e)}")
            raise ToolError(f"{spec.name}: {describe_error(e)}")
        text = format_result(result)
        if result.is_error:
            raise ToolError(text or "The tool reported an error")
        return text

    return Tool(name=name, description=description, parameters=_parameters(mcp_tool.input_schema), func=call,
                title=f"{spec.name}: {title}")


async def _server_tools(row: dict, user: dict):
    """(spec, connection, offered tools) or a Notice."""
    try:
        spec, connection = await connect(row, user)
    except McpAuthRequired as e:
        return Notice(row["id"], row["name"], str(e), auth_required=True, slug=row["slug"])
    except (McpUnavailable, McpConnectError) as e:
        return Notice(row["id"], row["name"], str(e), slug=row["slug"])
    except Exception as e:
        log.error(f"MCP server {row['slug']} failed: {e}", exc_info=True)
        return Notice(row["id"], row["name"], describe_error(e), slug=row["slug"])
    offered = [tool for tool in connection.tools if spec.tools is None or tool.name in spec.tools]
    return spec, connection, offered


async def tools_for_answer(user: dict, conversation: Optional[dict], taken: set) -> McpToolset:
    """
    The MCP tools of an answer.

    Args:
        user: The current user.
        conversation: The conversation row (persona_id).
        taken: Tool names the answer has already; the new ones are added to it.
    """
    toolset = McpToolset()
    rows = await asyncio.to_thread(answer_servers, user, conversation)
    if not rows:
        return toolset
    results = await asyncio.gather(*(_server_tools(row, user) for row in rows))
    prefixes: set = set()
    for row, result in zip(rows, results):
        if isinstance(result, Notice):
            log.info(f"MCP server {row['slug']} gives no tools: {result.reason}")
            toolset.notices.append(result)
            continue
        spec, connection, offered = result
        if not offered:
            continue
        # An admin server and a user's own server may share a slug
        prefix, number = spec.slug, 2
        while prefix in prefixes:
            prefix, number = f"{spec.slug}{number}", number + 1
        prefixes.add(prefix)
        for mcp_tool in offered:
            toolset.tools.append(_make_tool(row, spec, mcp_tool, tool_name(prefix, mcp_tool.name, taken), user))
        toolset.servers.append({"name": spec.name, "prefix": prefix, "description": spec.description,
                                "instructions": connection.instructions})
    return toolset


def notice_step(notice: Notice) -> dict:
    """The step of a server that gives no tools (an AgentStep dict)."""
    return {
        "type": "observation",
        "title": SIGN_IN_TITLE if notice.auth_required else UNAVAILABLE_TITLE,
        "content": notice.reason if notice.auth_required else f"{notice.name}: {notice.reason}",
        "metadata": {"mcpServer": notice.server_id, "authRequired": notice.auth_required},
    }


# =========================================================================
# Test
# =========================================================================

async def test_server(row: dict, user: dict) -> McpTestResult:
    """Connect anew as the user and list the server's tools."""
    try:
        spec, connection = await connect(row, user, fresh=True)
    except McpAuthRequired as e:
        return McpTestResult(ok=False, authRequired=True, error=str(e))
    except (McpUnavailable, McpConnectError) as e:
        return McpTestResult(ok=False, error=str(e))
    except Exception as e:
        log.error(f"Test of MCP server {row['slug']} failed: {e}", exc_info=True)
        return McpTestResult(ok=False, error=describe_error(e))
    tools = []
    for tool in connection.tools:
        annotations = tool.annotations
        tools.append(McpToolInfo(
            name=tool.name,
            title=tool.title or (annotations.title if annotations else None),
            description=tool.description,
            readOnly=annotations.read_only_hint if annotations else None,
            destructive=annotations.destructive_hint if annotations else None,
            enabled=spec.tools is None or tool.name in spec.tools,
        ))
    return McpTestResult(ok=True, serverName=connection.server_name, serverVersion=connection.server_version,
                         protocolVersion=connection.protocol_version, instructions=connection.instructions,
                         tools=tools)
