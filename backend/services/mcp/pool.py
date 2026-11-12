"""
Connections to MCP servers, kept per server and user (docs/mcp.md, "How an answer gets the tools").

Each connection is owned by a task of its own: it enters the client (transport, session, the
protocol handshake) and leaves it again in that task, as anyio requires, and in between waits
until it is told to close. Tool calls from the answers' tasks go through its client. A
connection is closed after MCP_IDLE_TIMEOUT without use, when its server's definition changes
(the fingerprint), and when the backend stops. Every user has their own connection, also to an
admin server (and their own process of a stdio server), so servers never share state between
users.
"""
import asyncio
import ipaddress
import logging
import socket
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx2
from mcp import Client, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import get_default_environment
from mcp.client.streamable_http import streamable_http_client
from mcp_types import Implementation

from backend.config import MCP_CONNECT_TIMEOUT, MCP_IDLE_TIMEOUT, MCP_TOOL_TIMEOUT
from backend.services.mcp import elicitation
from backend.services.mcp.servers import ServerSpec

log = logging.getLogger(__name__)

CLIENT_INFO = Implementation(name="advanced-llm-chat", version="1.0")
# Most tool pages read when listing a server's tools
MAX_TOOL_PAGES = 20


class McpAuthRequired(Exception):
    """The user has to sign in to the server (again)."""


class McpConnectError(Exception):
    """The server can't be reached or refused the connection."""


class BlockedAddress(httpx2.ConnectError):
    """A user's server on an address it may not use (MCP_ALLOW_PRIVATE_URLS)."""


def root_cause(error: BaseException) -> BaseException:
    """The first exception inside (nested) exception groups and chained causes that says the most."""
    seen = set()
    while id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, BaseExceptionGroup) and error.exceptions:
            auth = [e for e in error.exceptions if isinstance(root_cause(e), McpAuthRequired)]
            error = auth[0] if auth else error.exceptions[0]
            continue
        if isinstance(error, (McpAuthRequired, BlockedAddress)):
            return error
        cause = error.__cause__ or error.__context__
        if cause is not None and isinstance(cause, (McpAuthRequired, BlockedAddress, BaseExceptionGroup)):
            error = cause
            continue
        return error
    return error


def status_message(code: int) -> str:
    """What an HTTP error status of an MCP server means for the user."""
    if code == 401:
        return "The server asks for a sign-in (401): set up OAuth or headers"
    if code == 403:
        return "The server refused access (403)"
    if code == 404:
        return "Not found (404): check the URL"
    return f"The server answered {code}"


def describe_error(error: BaseException, http_status: Optional[int] = None) -> str:
    """A short message about why a connection or call failed (http_status: the last error status seen)."""
    error = root_cause(error)
    if isinstance(error, (TimeoutError, asyncio.TimeoutError)):
        return "The server didn't answer in time"
    if isinstance(error, httpx2.HTTPStatusError):
        return status_message(error.response.status_code)
    if http_status is not None and not isinstance(error, (BlockedAddress, McpAuthRequired)):
        # The transport turns error statuses into a generic JSON-RPC error
        return status_message(http_status)
    if isinstance(error, httpx2.ConnectError):
        return str(error) or "Can't connect to the server"
    if isinstance(error, FileNotFoundError):
        return f"Command not found: {error.filename or error}"
    message = str(error).strip() or type(error).__name__
    return message[:500]


# =========================================================================
# HTTP: address guard for users' servers
# =========================================================================

def _blocked(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved
            or ip.is_unspecified or not ip.is_global)


async def check_host(host: str) -> None:
    """Raise BlockedAddress if the host is or resolves to a private, loopback or other non-public address."""
    try:
        addresses = [host] if _is_ip(host) else [
            info[4][0] for info in await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)]
    except socket.gaierror as e:
        raise httpx2.ConnectError(f"Can't resolve {host}: {e}")
    for address in addresses:
        if _blocked(address.split("%")[0]):
            raise BlockedAddress(f"{host} is a private address, which own servers may not use "
                                 "(MCP_ALLOW_PRIVATE_URLS)")


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


class GuardedTransport(httpx2.AsyncBaseTransport):
    """An HTTP transport that only reaches public addresses (for users' own servers)."""

    def __init__(self):
        self._inner = httpx2.AsyncHTTPTransport(trust_env=False)

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        await check_host(request.url.host.strip("[]"))
        return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self._inner.aclose()


def http_client(*, guarded: bool, headers: Optional[dict] = None, auth: Optional[httpx2.Auth] = None,
                timeout: Optional[httpx2.Timeout] = None, on_response=None) -> httpx2.AsyncClient:
    """An HTTP client for an MCP server or its OAuth endpoints (on_response: an async response hook)."""
    return httpx2.AsyncClient(
        headers=headers or None,
        auth=auth,
        timeout=timeout or httpx2.Timeout(MCP_CONNECT_TIMEOUT, read=max(MCP_TOOL_TIMEOUT, 300)),
        transport=GuardedTransport() if guarded else None,
        follow_redirects=False,
        event_hooks={"response": [on_response]} if on_response else None,
    )


# =========================================================================
# Connections
# =========================================================================

@dataclass
class Connection:
    """One open connection to a server for one user."""

    spec: ServerSpec
    user_id: int
    guarded: bool
    auth: Optional[httpx2.Auth] = None
    client: Optional[Client] = None
    tools: list = field(default_factory=list)  # mcp_types.Tool
    instructions: Optional[str] = None
    server_name: Optional[str] = None
    server_version: Optional[str] = None
    protocol_version: Optional[str] = None
    error: Optional[BaseException] = None
    http_status: Optional[int] = None  # The last HTTP error status of the server
    last_used: float = field(default_factory=time.monotonic)
    fingerprint: str = ""
    askers: list = field(default_factory=list)  # elicitation.Asker of the running tool calls
    _task: Optional[asyncio.Task] = None
    _ready: asyncio.Event = field(default_factory=asyncio.Event)
    _close: asyncio.Event = field(default_factory=asyncio.Event)

    @property
    def alive(self) -> bool:
        return self.client is not None and self.error is None and self._task is not None and not self._task.done()

    def touch(self) -> None:
        self.last_used = time.monotonic()

    async def _elicit(self, context, params):
        """The server asks the user something while a tool runs (elicitation.py)."""
        return await elicitation.handle(self.askers, params)

    def _transport(self):
        spec = self.spec
        if spec.transport == "stdio":
            env = {**get_default_environment(), **spec.env}
            return StdioServerParameters(command=spec.command, args=list(spec.args), env=env)
        if spec.transport == "sse":
            def factory(headers=None, timeout=None, auth=None):
                return http_client(guarded=self.guarded, headers={**(headers or {}), **spec.headers},
                                   auth=self.auth, timeout=timeout, on_response=self._record_status)
            return sse_client(spec.url, timeout=MCP_CONNECT_TIMEOUT, sse_read_timeout=max(MCP_TOOL_TIMEOUT, 300),
                              httpx_client_factory=factory)
        return None  # http: made in _run, the client must be entered first

    async def _record_status(self, response: httpx2.Response) -> None:
        if response.status_code >= 400:
            self.http_status = response.status_code

    async def _run(self) -> None:
        try:
            async with AsyncExitStack() as stack:
                server: Any = self._transport()
                if server is None:
                    client = await stack.enter_async_context(
                        http_client(guarded=self.guarded, headers=self.spec.headers, auth=self.auth,
                                    on_response=self._record_status))
                    server = streamable_http_client(self.spec.url, http_client=client)
                mcp_client = Client(server, read_timeout_seconds=MCP_TOOL_TIMEOUT, client_info=CLIENT_INFO,
                                    cache=None, elicitation_callback=self._elicit)
                await stack.enter_async_context(mcp_client)
                self.tools = await _list_tools(mcp_client)
                self.client = mcp_client
                self.instructions = mcp_client.instructions
                info = mcp_client.server_info
                self.server_name = info.name if info else None
                self.server_version = info.version if info else None
                self.protocol_version = mcp_client.protocol_version
                self._ready.set()
                await self._close.wait()
        except BaseException as e:  # Also cancellation: the waiting side sees the error
            if not self._ready.is_set() or not isinstance(e, asyncio.CancelledError):
                self.error = e
            if not isinstance(e, (Exception, asyncio.CancelledError)):
                raise
        finally:
            self.client = None if self.error is not None else self.client
            self._ready.set()

    async def open(self) -> None:
        """Connect and list the tools; raises McpAuthRequired or McpConnectError."""
        self._task = asyncio.create_task(self._run(), name=f"mcp-{self.spec.slug}-{self.user_id}")
        try:
            await asyncio.wait_for(self._ready.wait(), MCP_CONNECT_TIMEOUT)
        except asyncio.TimeoutError:
            await self.close()
            raise McpConnectError("The server didn't answer in time")
        if self.error is not None or self.client is None:
            error = self.error or RuntimeError("The connection closed")
            await self.close()
            cause = root_cause(error)
            if isinstance(cause, McpAuthRequired):
                raise cause
            if getattr(self.auth, "failed", None):
                raise McpAuthRequired(self.auth.failed) from error
            raise McpConnectError(describe_error(error, self.http_status)) from error

    async def close(self) -> None:
        self._close.set()
        task = self._task
        if task is None or task.done():
            return
        try:
            await asyncio.wait_for(asyncio.shield(task), 5)
        except (asyncio.TimeoutError, Exception):
            task.cancel()
            try:
                await task
            except BaseException:
                pass


async def _list_tools(client: Client) -> list:
    tools, cursor = [], None
    for _ in range(MAX_TOOL_PAGES):
        result = await client.list_tools(cursor=cursor)
        tools.extend(result.tools)
        cursor = result.next_cursor
        if not cursor:
            break
    return tools


class Pool:
    """The open connections, by (server id, user id)."""

    def __init__(self):
        self._connections: dict[tuple[int, int], Connection] = {}
        self._locks: dict[tuple[int, int], asyncio.Lock] = {}
        self._reaper: Optional[asyncio.Task] = None

    async def get(self, spec: ServerSpec, user_id: int, *, guarded: bool,
                  auth_factory=None, fresh: bool = False) -> Connection:
        """
        An open connection to the server for the user, made if needed.

        Args:
            spec: The resolved server.
            user_id: The user it is for.
            guarded: Only public addresses (users' own servers).
            auth_factory: Makes the httpx2.Auth of a new connection (OAuth), or None.
            fresh: Close an existing connection and make a new one.

        Raises:
            McpAuthRequired, McpConnectError
        """
        key = (spec.id, user_id)
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            connection = self._connections.get(key)
            fingerprint = spec.fingerprint()
            if connection is not None and (fresh or not connection.alive or connection.fingerprint != fingerprint):
                self._connections.pop(key, None)
                await connection.close()
                connection = None
            if connection is None:
                connection = Connection(spec=spec, user_id=user_id, guarded=guarded,
                                        auth=auth_factory() if auth_factory else None, fingerprint=fingerprint)
                await connection.open()
                self._connections[key] = connection
                self._start_reaper()
            connection.touch()
            return connection

    async def close(self, server_id: int, user_id: Optional[int] = None) -> None:
        """Close the connections to a server (of one user, or of everyone)."""
        keys = [key for key in self._connections if key[0] == server_id and (user_id is None or key[1] == user_id)]
        for key in keys:
            connection = self._connections.pop(key, None)
            if connection is not None:
                await connection.close()

    async def close_all(self) -> None:
        connections = list(self._connections.values())
        self._connections.clear()
        await asyncio.gather(*(connection.close() for connection in connections), return_exceptions=True)
        if self._reaper is not None:
            self._reaper.cancel()
            self._reaper = None

    def _start_reaper(self) -> None:
        if self._reaper is None or self._reaper.done():
            self._reaper = asyncio.create_task(self._reap(), name="mcp-pool-reaper")

    async def _reap(self) -> None:
        while self._connections:
            await asyncio.sleep(min(60.0, MCP_IDLE_TIMEOUT / 2))
            now = time.monotonic()
            for key, connection in list(self._connections.items()):
                if not connection.alive or now - connection.last_used > MCP_IDLE_TIMEOUT:
                    if self._connections.get(key) is connection:
                        self._connections.pop(key, None)
                    log.debug(f"Closing idle MCP connection {connection.spec.slug} of user {key[1]}")
                    await connection.close()


pool = Pool()
