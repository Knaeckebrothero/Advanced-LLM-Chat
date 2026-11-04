#!/usr/bin/env python3
"""
Test of the MCP servers (docs/mcp.md) against real MCP servers and a real Postgres.

It starts MCP servers of the SDK on free local ports: a plain one, one that wants a header, one
behind a small OAuth authorization server of its own (protected resource and authorization server
metadata, dynamic client registration, PKCE, short-lived access tokens, refresh tokens), and one
over stdio. Covers: the argument check of list types; definitions (slugs, ${VAR} rules, stdio
only for admins and only with MCP_STDIO_ENABLED, users' headers encrypted, an empty header value
that keeps the stored one); agents' servers and users' own servers through user_mcp, for guests
and others; the tools of an answer (names, the tool selection, results: text, errors, images,
cut-off text; a server that is down becomes a notice); the connection pool (reuse, a changed
definition); the address guard of users' own servers; the OAuth sign-in from the start to the
refresh and a refresh that fails; persona validation and deleting a server; the catalog file;
the answer's tools in backend/api/messages.py; the API through FastAPI's test client.

It creates the database <POSTGRES_DB>_mcp_test if needed (or --database, whose name must contain
"test") and deletes its own test users, so it never touches the real database:

    python backend/services/tests/mcp_test.py

Exit code 0 if every check passed.
"""
import argparse
import asyncio
import base64
import dataclasses
import hashlib
import logging
import os
import secrets
import socket
import sys
import tempfile
import textwrap
import threading
import time
import traceback
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Secrets need a key; set before the backend reads its configuration
os.environ.setdefault("ENCRYPTION_KEY", "mcp-test-key-" + "x" * 32)
os.environ["MCP_TEST_KEY"] = "secret-123"

import httpx2  # noqa: E402
import uvicorn  # noqa: E402
from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.server.mcpserver.utilities.types import Image  # noqa: E402
from sqlalchemy import delete, insert, select  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import JSONResponse, RedirectResponse, Response  # noqa: E402

from backend import config  # noqa: E402
from backend.catalog import catalog_file, resolver, service  # noqa: E402
from backend.catalog.service import CatalogError  # noqa: E402
from backend.database.db import Database  # noqa: E402
from backend.database.tables import mcp_servers, mcp_tokens, personas, users  # noqa: E402
from backend.llm.tools import Tool, ToolError, ToolInputError, ToolRegistry  # noqa: E402
from backend.models.catalog import PersonaCreate, PersonaUpdate  # noqa: E402
from backend.models.mcp import McpServerCreate, McpServerUpdate  # noqa: E402
from backend.services.mcp import oauth, servers, store  # noqa: E402
from backend.services.mcp import tools as mcp_tools  # noqa: E402
from backend.services.mcp.pool import pool  # noqa: E402

TEST_EMAILS = ("mcp-test-1@example.com", "mcp-test-2@example.com", "mcp-test-admin@example.com")
TEST_PERSONA_PREFIX = "MCP test agent"
TEST_SLUG_PREFIX = "t_"

db: Database = None
user_ids: list[int] = []
ports: dict[str, int] = {}
auth_server = None  # FakeAuthServer


def user(index: int = 0, guest: bool = False, admin: bool = False) -> dict:
    return {"user_id": user_ids[index], "is_guest": guest, "is_admin": admin, "email": TEST_EMAILS[index]}


def url(name: str) -> str:
    return f"http://127.0.0.1:{ports[name]}/mcp"


# =========================================================================
# Test servers
# =========================================================================

def make_mcp(name: str) -> MCPServer:
    server = MCPServer(name, instructions=f"Instructions of {name}.")

    @server.tool()
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    @server.tool(title="Echo it")
    def echo(text: str, suffix: str | None = None) -> str:
        """Echo the text."""
        return text + (suffix or "")

    @server.tool()
    def fail() -> str:
        """Always fails."""
        raise ValueError("boom")

    @server.tool()
    def picture() -> Image:
        """A tiny image."""
        return Image(data=b"\x89PNG" + b"0" * 2000, format="png")

    @server.tool()
    def big() -> str:
        """A long text."""
        return "y" * 5000

    return server


class Gate:
    """An ASGI wrapper that answers some requests itself and lets the rest through to the MCP app."""

    def __init__(self, app, handler):
        self.app = app
        self.handler = handler

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            response = await self.handler(Request(scope, receive))
            if response is not None:
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


async def key_check(request: Request):
    if request.headers.get("x-api-key") != "secret-123":
        return JSONResponse({"error": "missing key"}, status_code=401)
    return None


class FakeAuthServer:
    """An OAuth authorization server and the protected resource check for the oauth MCP server."""

    def __init__(self):
        self.clients: dict[str, dict] = {}
        self.codes: dict[str, dict] = {}
        self.access: dict[str, float] = {}  # token -> expiry
        self.refresh: set[str] = set()
        self.expires_in = 3600
        self.refreshes = 0

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{ports['oauth']}"

    async def __call__(self, request: Request):
        path = request.url.path
        if path == "/.well-known/oauth-protected-resource/mcp":
            return JSONResponse({"resource": f"{self.base}/mcp", "authorization_servers": [self.base]})
        if path == "/.well-known/oauth-authorization-server":
            return JSONResponse({
                "issuer": self.base, "authorization_endpoint": f"{self.base}/authorize",
                "token_endpoint": f"{self.base}/token", "registration_endpoint": f"{self.base}/register",
                "code_challenge_methods_supported": ["S256"], "token_endpoint_auth_methods_supported": ["none"],
                "response_types_supported": ["code"], "scopes_supported": ["tools"],
            })
        if path == "/register":
            body = await request.json()
            client_id = "client-" + secrets.token_hex(4)
            self.clients[client_id] = body
            return JSONResponse({**body, "client_id": client_id}, status_code=201)
        if path == "/authorize":
            params = request.query_params
            assert params["client_id"] in self.clients and params["code_challenge_method"] == "S256"
            assert params["resource"] == f"{self.base}/mcp", params.get("resource")
            code = secrets.token_hex(8)
            self.codes[code] = dict(params)
            return RedirectResponse(f"{params['redirect_uri']}?{urlencode({'code': code, 'state': params['state']})}")
        if path == "/token":
            form = dict(await request.form())
            if form["grant_type"] == "authorization_code":
                pending = self.codes.pop(form["code"], None)
                if pending is None or pending["redirect_uri"] != form["redirect_uri"]:
                    return JSONResponse({"error": "invalid_grant"}, status_code=400)
                challenge = base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"].encode()).digest()).decode().rstrip("=")
                if challenge != pending["code_challenge"]:
                    return JSONResponse({"error": "invalid_grant", "error_description": "PKCE"}, status_code=400)
            elif form["grant_type"] == "refresh_token":
                if form["refresh_token"] not in self.refresh:
                    return JSONResponse({"error": "invalid_grant"}, status_code=400)
                self.refresh.discard(form["refresh_token"])
                self.refreshes += 1
            else:
                return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)
            access, refresh = "at-" + secrets.token_hex(6), "rt-" + secrets.token_hex(6)
            self.access[access] = time.time() + self.expires_in
            self.refresh.add(refresh)
            return JSONResponse({"access_token": access, "token_type": "bearer", "expires_in": self.expires_in,
                                 "refresh_token": refresh, "scope": "tools"})
        # The MCP endpoint: a valid bearer token or 401
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        if self.access.get(token, 0) < time.time():
            return Response(status_code=401, headers={
                "WWW-Authenticate": f'Bearer resource_metadata="{self.base}/.well-known/oauth-protected-resource/mcp", '
                                    'scope="tools"'})
        return None


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def serve(name: str, app) -> None:
    ports[name] = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=ports[name], log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)


def start_servers() -> None:
    global auth_server
    serve("plain", make_mcp("plain").streamable_http_app())
    serve("keyed", Gate(make_mcp("keyed").streamable_http_app(), key_check))
    serve("sse", make_mcp("sse").sse_app())
    auth_server = FakeAuthServer()
    serve("oauth", Gate(make_mcp("oauth").streamable_http_app(), auth_server))
    ports["closed"] = free_port()  # Nothing listens here


STDIO_SERVER = textwrap.dedent("""
    import os
    from mcp.server.mcpserver import MCPServer
    server = MCPServer("stdio-test")

    @server.tool()
    def whoami() -> str:
        \"\"\"The value of TEST_GREETING.\"\"\"
        return os.environ.get("TEST_GREETING", "?") + " / " + str(os.environ.get("POSTGRES_PASSWORD"))

    server.run()
""")


# =========================================================================
# Helpers
# =========================================================================

def cleanup(conn) -> None:
    conn.execute(delete(mcp_servers).where(mcp_servers.c.slug.startswith(TEST_SLUG_PREFIX)))
    conn.execute(delete(users).where(users.c.email.in_(TEST_EMAILS)))
    conn.execute(delete(personas).where(personas.c.name.startswith(TEST_PERSONA_PREFIX)))


def reset() -> None:
    with db.connection() as conn:
        cleanup(conn)
        user_ids[:] = [conn.execute(insert(users).values(email=email, name="MCP test").returning(users.c.id)).scalar_one()
                       for email in TEST_EMAILS]


def admin_server(slug: str, **fields) -> dict:
    fields.setdefault("url", url("plain"))
    return servers.create_admin_server(McpServerCreate(name=fields.pop("name", slug.title()), slug=slug, **fields))


def own_server(index: int, slug: str, **fields) -> dict:
    fields.setdefault("url", url("plain"))
    return servers.create_user_server(user_ids[index], McpServerCreate(name=fields.pop("name", slug), slug=slug, **fields))


def agent(name: str, mcp: list | None = None, tools: list | None = None, guests: bool = False) -> dict:
    created = service.create_persona(PersonaCreate(name=f"{TEST_PERSONA_PREFIX} {name}", systemPrompt="Test.",
                                                   tools=tools, mcpServers=mcp, availableToGuests=guests))
    return {"id": "mcp-test", "persona_id": created.id}


async def answer_tools(conversation: dict, index: int = 0, **user_flags):
    toolset = await mcp_tools.tools_for_answer(user(index, **user_flags), conversation, set())
    return toolset, ToolRegistry(toolset.tools)


async def expect(error_type, coroutine) -> str:
    try:
        result = await coroutine
    except error_type as e:
        return str(e)
    raise AssertionError(f"expected {error_type.__name__}, got {result!r}")


def expect_sync(error_type, function, *args, **kwargs) -> str:
    try:
        result = function(*args, **kwargs)
    except error_type as e:
        return str(e)
    raise AssertionError(f"expected {error_type.__name__}, got {result!r}")


# =========================================================================
# Tests
# =========================================================================

async def test_argument_check_with_type_lists():
    async def echo(**kwargs):
        return kwargs
    registry = ToolRegistry([Tool(name="t", description="", func=echo, parameters={
        "type": "object", "properties": {"a": {"type": ["string", "null"]}, "b": {"anyOf": [{"type": "integer"}]},
                                         "c": {"type": "integer"}}})])
    assert await registry.call("t", {"a": "x", "b": "anything", "c": "7"}) == {"a": "x", "b": "anything", "c": 7}
    assert "string or null" in await expect(ToolInputError, registry.call("t", {"a": 5}))
    assert "integer" in await expect(ToolInputError, registry.call("t", {"c": True}))


async def test_definitions():
    row = admin_server("t_gh", name="My GitHub!", url="${MCP_TEST_API}/mcp", auth="headers",
                       headers={"Authorization": "Bearer ${MCP_TEST_KEY}"})
    assert row["slug"] == "t_gh" and row["headers"] == {"Authorization": "Bearer ${MCP_TEST_KEY}"}
    assert servers.make_slug("My GitHub!") == "my_github" and servers.make_slug("42 Things") == "mcp_42_things"
    out = servers.server_out(row, set())
    assert out.unavailableReason == "MCP_TEST_API is not set" and out.headerNames == ["Authorization"]
    os.environ["MCP_TEST_API"] = f"http://127.0.0.1:{ports['keyed']}"
    assert servers.server_out(row, set()).unavailableReason is None
    assert servers.resolve(row).headers == {"Authorization": "Bearer secret-123"}

    message = expect_sync(servers.McpError, admin_server, "t_bad", auth="headers", headers={"X": "${POSTGRES_PASSWORD}"})
    assert "POSTGRES_PASSWORD" in message
    assert "slug" in expect_sync(servers.McpError, admin_server, "Bad Slug")
    assert expect_sync(servers.McpConflict, admin_server, "t_gh")
    assert "url" in expect_sync(servers.McpError, admin_server, "t_nourl", url="ftp://x")

    servers.MCP_STDIO_ENABLED = False
    assert expect_sync(servers.McpUnavailable, admin_server, "t_cmd", transport="stdio", command="x", url=None)
    servers.MCP_STDIO_ENABLED = True
    command = admin_server("t_cmd", transport="stdio", command="x", url=None)
    assert command["transport"] == "stdio"
    # With the switch off, a stdio server can still be renamed or disabled, but not get another command
    servers.MCP_STDIO_ENABLED = False
    try:
        servers.update_admin_server(command["id"], McpServerUpdate(name="Renamed", enabled=False, transport="stdio",
                                                                   command="x", args=[], env={}))
        assert expect_sync(servers.McpUnavailable, servers.update_admin_server, command["id"],
                           McpServerUpdate(command="rm"))
    finally:
        servers.MCP_STDIO_ENABLED = True
    assert expect_sync(servers.McpForbidden, own_server, 0, "t_cmd", transport="stdio", command="x", url=None)
    assert expect_sync(servers.McpForbidden, own_server, 0, "t_sec", auth="oauth", oauthClientSecretEnv="X_SECRET")

    # Users' headers are encrypted, never returned, and kept by an empty value
    mine = own_server(0, "t_mine", auth="headers", headers={"X-Api-Key": "secret-123", "X-Other": "o"})
    with db.connection() as conn:
        stored = conn.execute(select(mcp_servers.c.headers, mcp_servers.c.headers_encrypted)
                              .where(mcp_servers.c.id == mine["id"])).first()
    assert stored.headers is None and "secret-123" not in stored.headers_encrypted
    out = servers.server_out(mine, set())
    assert out.headers is None and out.headerNames == ["X-Api-Key", "X-Other"] and out.shared is False
    _, mine = servers.update_user_server(user_ids[0], mine["id"], McpServerUpdate(headers={"X-Api-Key": "", "X-New": "n"}))
    assert servers.stored_headers(mine) == {"X-Api-Key": "secret-123", "X-New": "n"}
    # ${VAR} is never filled for users' servers
    theirs = own_server(1, "t_var", auth="headers", headers={"X": "${MCP_TEST_KEY}"})
    assert servers.resolve(theirs).headers == {"X": "${MCP_TEST_KEY}"}
    # Same slug for another owner is fine; not another user's server
    assert own_server(1, "t_mine")["user_id"] == user_ids[1]
    assert expect_sync(servers.McpNotFound, servers.own_server, user_ids[1], mine["id"])


async def test_agents_and_users_servers():
    admin_server("t_plain", url=url("plain"))
    admin_server("t_guests", url=url("plain"), availableToGuests=True)
    admin_server("t_off", url=url("plain"), enabled=False)
    own_server(0, "t_own", url=url("plain"))

    conversation = agent("A", mcp=["t_plain", "t_guests", "t_off"], tools=["user_mcp"], guests=True)
    rows = mcp_tools.answer_servers(user(0, admin=True), conversation)
    assert [r["slug"] for r in rows] == ["t_plain", "t_guests", "t_own"], [r["slug"] for r in rows]
    assert [r["slug"] for r in mcp_tools.answer_servers(user(0, guest=True), conversation)] == ["t_guests"]
    assert [r["slug"] for r in mcp_tools.answer_servers(user(1), conversation)] == ["t_plain", "t_guests"]
    # Every tool (tools null) or no agent: no MCP servers
    assert mcp_tools.answer_servers(user(0), agent("B")) == []
    assert mcp_tools.answer_servers(user(0), {"id": "x", "persona_id": None}) == []
    # An agent without user_mcp gets no own servers
    assert [r["slug"] for r in mcp_tools.answer_servers(user(0), agent("C", mcp=["t_plain"], tools=["files"]))] == ["t_plain"]

    # Unknown slugs are refused; deleting a server takes it off the agents
    message = expect_sync(CatalogError, service.create_persona,
                          PersonaCreate(name=f"{TEST_PERSONA_PREFIX} D", systemPrompt="x", mcpServers=["t_nope"]))
    assert "t_nope" in message
    persona_id = conversation["persona_id"]
    store.delete_server(store.admin_server_by_slug("t_guests")["id"])
    assert db.get_persona_by_id(persona_id)["mcp_servers"] == ["t_plain", "t_off"]
    updated = service.update_persona(persona_id, PersonaUpdate(mcpServers=[]))
    assert updated.mcpServers is None


async def test_answer_tools():
    admin_server("t_plain", url=url("plain"), description="A test server", tools=["add", "echo", "fail", "picture", "big"])
    admin_server("t_down", url=f"http://127.0.0.1:{ports['closed']}/mcp")
    conversation = agent("A", mcp=["t_plain", "t_down"])
    toolset, registry = await answer_tools(conversation)
    assert registry.names() == ["t_plain__add", "t_plain__echo", "t_plain__fail", "t_plain__picture", "t_plain__big"]
    assert registry.title("t_plain__echo") == "T_Plain: Echo it", registry.title("t_plain__echo")
    assert toolset.servers == [{"name": "T_Plain", "prefix": "t_plain", "description": "A test server",
                                "instructions": "Instructions of plain."}]
    assert len(toolset.notices) == 1 and toolset.notices[0].name == "T_Down" and not toolset.notices[0].auth_required
    step = mcp_tools.notice_step(toolset.notices[0])
    assert step["title"] == "MCP server unavailable" and step["metadata"]["mcpServer"] == toolset.notices[0].server_id

    assert await registry.call("t_plain__add", {"a": 2, "b": "3"}) == "5"
    assert await registry.call("t_plain__echo", {"text": "hi", "suffix": None}) == "hi"
    assert "fail" in await expect(ToolError, registry.call("t_plain__fail", {}))
    assert await registry.call("t_plain__picture", {}) == "[image/png, 2 KB, not shown]"
    mcp_tools.MCP_MAX_RESULT_CHARS = 100
    assert (await registry.call("t_plain__big", {})).startswith("y" * 100 + "\n\n[... cut off")
    mcp_tools.MCP_MAX_RESULT_CHARS = config.MCP_MAX_RESULT_CHARS

    # The tool selection, and names already taken
    row = store.admin_server_by_slug("t_plain")
    servers.update_admin_server(row["id"], McpServerUpdate(tools=["add"]))
    toolset = await mcp_tools.tools_for_answer(user(0), conversation, {"t_plain__add"})
    assert [tool.name for tool in toolset.tools] == ["t_plain__add_2"]


async def test_pool():
    row = admin_server("t_plain", url=url("plain"))
    _, first = await mcp_tools.connect(row, user(0))
    _, again = await mcp_tools.connect(row, user(0))
    _, other = await mcp_tools.connect(row, user(1))
    assert first is again and first is not other
    _, row = servers.update_admin_server(row["id"], McpServerUpdate(auth="headers", headers={"X-Test": "1"}))
    _, changed = await mcp_tools.connect(row, user(0))
    assert changed is not first and not first.alive
    await pool.close(row["id"])
    assert not changed.alive


async def test_headers():
    row = admin_server("t_keyed", url=url("keyed"))
    result = await mcp_tools.test_server(row, user(0, admin=True))
    assert not result.ok and "401" in result.error, result
    _, row = servers.update_admin_server(row["id"], McpServerUpdate(auth="headers", headers={"X-Api-Key": "${MCP_TEST_KEY}"}))
    result = await mcp_tools.test_server(row, user(0, admin=True))
    assert result.ok and result.serverName == "keyed" and [t.name for t in result.tools][:2] == ["add", "echo"], result


async def test_sse_transport():
    row = admin_server("t_sse", transport="sse", url=f"http://127.0.0.1:{ports['sse']}/sse")
    toolset, registry = await answer_tools(agent("A", mcp=["t_sse"]))
    assert toolset.notices == [] and await registry.call("t_sse__add", {"a": 20, "b": 22}) == "42", toolset.notices
    assert toolset.servers[0]["instructions"] == "Instructions of sse."
    # A selection without tools: no tools and no prompt section
    servers.update_admin_server(row["id"], McpServerUpdate(tools=[]))
    toolset, _ = await answer_tools(agent("B", mcp=["t_sse"]))
    assert toolset.tools == [] and toolset.servers == [] and toolset.notices == []


async def test_private_addresses():
    row = own_server(0, "t_local", url=url("plain"))
    result = await mcp_tools.test_server(row, user(0))
    assert not result.ok and "private address" in result.error, result
    # Admins' own servers may, and so may everyone's with MCP_ALLOW_PRIVATE_URLS
    assert (await mcp_tools.test_server(row, user(0, admin=True))).ok
    oauth.MCP_ALLOW_PRIVATE_URLS = True
    try:
        assert (await mcp_tools.test_server(row, user(0))).ok
    finally:
        oauth.MCP_ALLOW_PRIVATE_URLS = False


def browser(authorization_url: str) -> dict:
    """Follow the authorization URL like a browser that approves at once: the callback's parameters."""
    response = httpx2.get(authorization_url, follow_redirects=False)
    assert response.status_code in (302, 307), response.text
    return {key: value[0] for key, value in parse_qs(urlparse(response.headers["location"]).query).items()}


async def test_oauth():
    oauth.MCP_ALLOW_PRIVATE_URLS = True
    try:
        row = own_server(0, "t_oauth", url=url("oauth"), auth="oauth")
        conversation = agent("A", tools=["user_mcp"])
        toolset, _ = await answer_tools(conversation)
        assert toolset.tools == [] and toolset.notices[0].auth_required, toolset.notices
        assert mcp_tools.notice_step(toolset.notices[0])["title"] == "Sign-in needed"

        redirect = "https://chat.example/api/mcp/oauth/callback"
        authorization_url = await oauth.start_sign_in(row, user(0), redirect)
        assert authorization_url.startswith(f"http://127.0.0.1:{ports['oauth']}/authorize?")
        callback = browser(authorization_url)
        # Another user can't finish it, and a state works only once
        failed = await expect(oauth.SignInFailed, oauth.finish_sign_in(callback["state"], callback["code"], None, None, user(1)))
        assert "another user" in failed
        assert "expired" in await expect(oauth.SignInFailed, oauth.finish_sign_in(callback["state"], callback["code"], None, None, user(0)))

        callback = browser(await oauth.start_sign_in(store.get_server(row["id"]), user(0), redirect))
        assert len(auth_server.clients) == 1  # The registered client is used again
        assert await oauth.finish_sign_in(callback["state"], callback["code"], None, None, user(0)) == row["id"]
        tokens = store.get_tokens(row["id"], user_ids[0])
        assert tokens["access_token"].startswith("at-") and tokens["refresh_token"] and tokens["scope"] == "tools"
        with db.connection() as conn:
            assert "at-" not in conn.execute(select(mcp_tokens.c.tokens_encrypted)).first()[0]
        assert servers.server_out(store.get_server(row["id"]), store.connected_server_ids(user_ids[0])).connected

        toolset, registry = await answer_tools(conversation)
        assert toolset.notices == [] and await registry.call("t_oauth__add", {"a": 1, "b": 1}) == "2"

        # An expired access token is refreshed, also mid-connection after a 401
        for token in list(auth_server.access):
            auth_server.access[token] = 0
        assert await registry.call("t_oauth__add", {"a": 2, "b": 2}) == "4"
        assert auth_server.refreshes == 1
        await pool.close(row["id"])
        tokens = store.get_tokens(row["id"], user_ids[0])
        tokens["expires_at"] = time.time() - 10
        store.save_tokens(row["id"], user_ids[0], tokens)
        toolset, registry = await answer_tools(conversation)
        assert await registry.call("t_oauth__add", {"a": 3, "b": 3}) == "6" and auth_server.refreshes == 2

        # A refresh that fails ends the sign-in
        await pool.close(row["id"])
        auth_server.refresh.clear()
        for token in list(auth_server.access):
            auth_server.access[token] = 0
        toolset, _ = await answer_tools(conversation)
        assert toolset.notices and toolset.notices[0].auth_required, toolset.notices
        assert store.get_tokens(row["id"], user_ids[0]) is None

        # An admin server with OAuth: each user signs in on their own
        shared = admin_server("t_shared", url=url("oauth"), auth="oauth")
        callback = browser(await oauth.start_sign_in(shared, user(1), redirect))
        await oauth.finish_sign_in(callback["state"], callback["code"], None, None, user(1))
        assert store.connected_server_ids(user_ids[1]) == {shared["id"]}
        assert await oauth.sign_out(shared["id"], user_ids[1]) and store.connected_server_ids(user_ids[1]) == set()
    finally:
        oauth.MCP_ALLOW_PRIVATE_URLS = False


async def test_stdio():
    with tempfile.TemporaryDirectory() as folder:
        script = Path(folder) / "server.py"
        script.write_text(STDIO_SERVER)
        os.environ["MCP_TEST_GREETING_KEY"] = "hello"
        row = admin_server("t_stdio", transport="stdio", command=sys.executable, args=[str(script)], url=None,
                           env={"TEST_GREETING": "${MCP_TEST_GREETING_KEY}"})
        toolset, registry = await answer_tools(agent("A", mcp=["t_stdio"]))
        # The process gets its own variables, not the backend's
        assert toolset.notices == [], toolset.notices
        assert await registry.call("t_stdio__whoami", {}) == "hello / None"
        await pool.close(row["id"])


async def test_answer_context():
    from backend.api import messages
    from backend.llm.types import ModelConfig
    admin_server("t_plain", url=url("plain"), tools=["add"])
    admin_server("t_down", url=f"http://127.0.0.1:{ports['closed']}/mcp")
    conversation = agent("A", mcp=["t_plain", "t_down"], tools=[])
    config_ = ModelConfig(id=None, display_name="Test", model_id="test", provider_id=None, provider_name="Test",
                          kind="openai_compatible", base_url=None)
    tools, toolset = await messages._mcp_tools(user(0), conversation, config_, None)
    assert tools.names() == ["t_plain__add"] and len(toolset.notices) == 1
    # The prompt names the server that gives no tools this time, so earlier results aren't taken for made up
    from backend.llm import with_mcp_servers
    prompt = with_mcp_servers("Base", toolset.servers, toolset.unavailable())
    assert "- **T_Plain** (tools `t_plain__*`)" in prompt and "Not available in this answer" in prompt
    assert "- **T_Down** (tools `t_down__*`): " in prompt, prompt
    assert with_mcp_servers("Base", [], []) == "Base"
    no_tools = dataclasses.replace(config_, supports_tools=False)
    assert await messages._mcp_tools(user(0), conversation, no_tools, None) == (None, mcp_tools.McpToolset())


async def test_catalog_file():
    admin_server("t_plain", url=url("plain"), description="Plain", tools=["add"])
    agent("A", mcp=["t_plain"])
    exported = catalog_file.export_catalog()
    entry = next(e for e in exported["mcp_servers"] if e["slug"] == "t_plain")
    assert entry["url"] == url("plain") and entry["tools"] == ["add"] and "headers_encrypted" not in entry
    persona = next(p for p in exported["personas"] if p["name"] == f"{TEST_PERSONA_PREFIX} A")
    assert persona["mcp_servers"] == ["t_plain"]
    result = catalog_file.import_catalog({"version": 1, "mcp_servers": [
        {"slug": "t_plain", "name": "Plain", "description": "Changed"},
        {"name": "T new", "slug": "t_new", "url": url("plain")},
        {"name": "T bad", "slug": "t_bad", "url": url("plain"), "headers": {"X": "${POSTGRES_PASSWORD}"}, "auth": "headers"},
    ], "personas": [{"name": f"{TEST_PERSONA_PREFIX} B", "system_prompt": "x", "mcp_servers": ["t_new"]}]})
    assert (result.mcpServers.created, result.mcpServers.updated, result.personas.created) == (1, 1, 1), result
    assert any("t_bad" in error or "T bad" in error for error in result.errors), result.errors
    assert store.admin_server_by_slug("t_plain")["description"] == "Changed"


async def test_api():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api import mcp as mcp_api
    from backend.security.auth import get_current_user, get_current_user_optional, require_admin

    current = {"user": user(0)}
    app = FastAPI()
    app.include_router(mcp_api.router)
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    app.dependency_overrides[get_current_user_optional] = lambda: current["user"]

    def admin_only():
        if not current["user"].get("is_admin"):
            from fastapi import HTTPException
            raise HTTPException(status_code=403)
        return current["user"]
    app.dependency_overrides[require_admin] = admin_only

    oauth.MCP_ALLOW_PRIVATE_URLS = True
    try:
        with TestClient(app) as client:
            assert client.get("/api/mcp/config").json()["encryption"] is True
            response = client.post("/api/mcp/servers", json={"name": "T api", "slug": "t_api", "url": url("plain")})
            assert response.status_code == 201, response.text
            server_id = response.json()["id"]
            assert client.post("/api/mcp/servers", json={"name": "T api", "slug": "t_api", "url": url("plain")}).status_code == 409
            test = client.post(f"/api/mcp/servers/{server_id}/test").json()
            assert test["ok"] and test["serverName"] == "plain" and len(test["tools"]) == 5, test
            body = client.put(f"/api/mcp/servers/{server_id}", json={"tools": ["add"], "enabled": False}).json()
            assert body["tools"] == ["add"] and body["enabled"] is False
            assert [s["slug"] for s in client.get("/api/mcp/servers").json()["own"]] == ["t_api"]

            # Admin servers: only admins edit them; users see the OAuth ones to sign in to
            assert client.post("/api/admin/mcp-servers", json={"name": "x", "url": url("plain")}).status_code == 403
            current["user"] = user(2, admin=True)
            response = client.post("/api/admin/mcp-servers", json={"name": "T shared", "slug": "t_shared",
                                                                   "url": url("oauth"), "auth": "oauth"})
            assert response.status_code == 201, response.text
            shared_id = response.json()["id"]
            assert client.post(f"/api/mcp/servers/{server_id}/test").status_code == 404  # Another user's own server
            current["user"] = user(1)
            shared = client.get("/api/mcp/servers").json()["shared"]
            assert [s["id"] for s in shared] == [shared_id] and shared[0]["headers"] is None
            assert shared[0]["command"] is None and shared[0]["oauthClientId"] is None
            assert client.put(f"/api/mcp/servers/{server_id}", json={"name": "mine"}).status_code == 404
            connect = client.post(f"/api/mcp/servers/{shared_id}/connect")
            assert connect.status_code == 200 and "/authorize?" in connect.json()["authorizationUrl"], connect.text
            callback = browser(connect.json()["authorizationUrl"])
            response = client.get("/api/mcp/oauth/callback", params=callback, follow_redirects=False)
            assert response.headers["location"].endswith(f"/mcp?connected={shared_id}"), response.headers
            response = client.get("/api/mcp/oauth/callback", params=callback, follow_redirects=False)
            assert response.headers["location"].endswith("/mcp?error=expired")
            assert client.get("/api/mcp/servers").json()["shared"][0]["connected"] is True
            assert client.delete(f"/api/mcp/servers/{shared_id}/connection").status_code == 204

            current["user"] = user(1, guest=True)
            assert client.get("/api/mcp/servers").status_code == 403
            assert client.get("/api/mcp/config").status_code == 200
            current["user"] = user(0)
            assert client.delete(f"/api/mcp/servers/{server_id}").status_code == 204
    finally:
        oauth.MCP_ALLOW_PRIVATE_URLS = False
    # The test client ran the app on a loop of its own, which is gone now
    pool._connections.clear()
    pool._locks.clear()
    pool._reaper = None


TESTS = [
    test_argument_check_with_type_lists,
    test_definitions,
    test_agents_and_users_servers,
    test_answer_tools,
    test_pool,
    test_headers,
    test_sse_transport,
    test_private_addresses,
    test_oauth,
    test_stdio,
    test_answer_context,
    test_catalog_file,
    test_api,
]


async def run() -> int:
    failures = 0
    for test in TESTS:
        reset()
        try:
            await test()
            print(f"PASS  {test.__name__}")
        except Exception:
            failures += 1
            print(f"FAIL  {test.__name__}")
            traceback.print_exc()
        finally:
            if test is not test_api:
                await pool.close_all()
    with db.connection() as conn:
        cleanup(conn)
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} passed")
    return 1 if failures else 0


def main() -> int:
    global db
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--database", default=f"{config.POSTGRES_DB}_mcp_test",
                        help="Test database, created if needed (default: <POSTGRES_DB>_mcp_test)")
    args = parser.parse_args()
    if "test" not in args.database:
        print(f"Refusing to run against '{args.database}': the name must contain 'test'")
        return 2

    logging.basicConfig(level=logging.WARNING)
    for name in ("backend", "crud", "httpx", "mcp", "uvicorn"):
        logging.getLogger(name).setLevel(logging.CRITICAL if name in ("mcp", "uvicorn") else logging.WARNING)
    from backend.database.db_init import create_database_if_not_exists, migrate_schema
    create_database_if_not_exists(config.POSTGRES_HOST, config.POSTGRES_PORT, config.POSTGRES_USER,
                                  config.POSTGRES_PASSWORD, args.database, logging.getLogger("mcp-test"))
    db = Database(database=args.database)
    migrate_schema(db.engine, logging.getLogger("mcp-test"))
    db.init_tables()
    for module in (store, mcp_tools, service, resolver, catalog_file):
        module.db = db
    servers.MCP_STDIO_ENABLED = True
    start_servers()
    try:
        return asyncio.run(run())
    finally:
        db.close_all()


if __name__ == "__main__":
    sys.exit(main())
