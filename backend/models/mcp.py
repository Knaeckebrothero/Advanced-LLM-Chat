"""
MCP server API models (docs/mcp.md): the admins' servers, which agents pick, and users' own.
"""
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel

from backend.models.common import UtcDatetime

McpTransport = Literal["http", "sse", "stdio"]
McpAuth = Literal["none", "headers", "oauth"]


class McpConfig(BaseModel):
    """GET /api/mcp/config: what the server's configuration allows."""
    enabled: bool
    userServers: bool  # Signed-in users may add their own servers
    stdio: bool  # Admins may define stdio servers
    encryption: bool  # ENCRYPTION_KEY is set: OAuth sign-in and users' headers work
    privateUrls: bool  # Users' own servers may be on private addresses
    reason: Optional[str] = None  # Why MCP or users' servers are off


class McpServerCreate(BaseModel):
    name: str
    slug: Optional[str] = None  # Tool name prefix; made from the name if left out; fixed after creation
    description: Optional[str] = None
    transport: McpTransport = "http"
    url: Optional[str] = None  # http, sse
    command: Optional[str] = None  # stdio
    args: List[str] = []
    env: Dict[str, str] = {}
    auth: McpAuth = "none"
    headers: Optional[Dict[str, str]] = None
    oauthClientId: Optional[str] = None
    oauthClientSecretEnv: Optional[str] = None  # Admin servers only
    oauthScopes: Optional[str] = None
    tools: Optional[List[str]] = None  # MCP tool names offered to the model; None = all
    availableToGuests: bool = False  # Admin servers only
    enabled: bool = True
    sortOrder: int = 0


class McpServerUpdate(BaseModel):
    """Partial update; fields left out stay unchanged. The slug can't change."""
    name: Optional[str] = None
    description: Optional[str] = None
    transport: Optional[McpTransport] = None
    url: Optional[str] = None
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    auth: Optional[McpAuth] = None
    # Replaces the headers; for users' servers a header with an empty value keeps its stored value
    headers: Optional[Dict[str, str]] = None
    oauthClientId: Optional[str] = None
    oauthClientSecretEnv: Optional[str] = None
    oauthScopes: Optional[str] = None
    tools: Optional[List[str]] = None  # null = all tools
    availableToGuests: Optional[bool] = None
    enabled: Optional[bool] = None
    sortOrder: Optional[int] = None


class McpServerOut(BaseModel):
    id: int
    shared: bool  # An admin server (the agents'), not a user's own
    name: str
    slug: str
    description: Optional[str] = None
    transport: McpTransport
    url: Optional[str] = None
    command: Optional[str] = None
    args: List[str] = []
    env: Dict[str, str] = {}
    auth: McpAuth
    headers: Optional[Dict[str, str]] = None  # Admin servers: as written; users' servers: never returned
    headerNames: List[str] = []
    oauthClientId: Optional[str] = None
    oauthClientSecretEnv: Optional[str] = None
    oauthScopes: Optional[str] = None
    tools: Optional[List[str]] = None
    availableToGuests: bool = False
    enabled: bool = True
    sortOrder: int = 0
    connected: Optional[bool] = None  # OAuth: the current user has signed in; None for other auth
    autoAccept: Optional[bool] = None  # The current user accepts its confirmations without asking (elicitation)
    unavailableReason: Optional[str] = None
    createdAt: Optional[UtcDatetime] = None
    updatedAt: Optional[UtcDatetime] = None


class McpServerList(BaseModel):
    """GET /api/mcp/servers."""
    own: List[McpServerOut]  # The user's own servers
    shared: List[McpServerOut]  # Enabled admin servers with OAuth, to sign in to
    autoAccepted: List[McpServerOut] = []  # Other admin servers whose confirmations the user accepts without asking


class McpToolInfo(BaseModel):
    name: str
    title: Optional[str] = None
    description: Optional[str] = None
    readOnly: Optional[bool] = None
    destructive: Optional[bool] = None
    enabled: bool = True  # In the server's tools selection


class McpTestResult(BaseModel):
    """POST /api/mcp/servers/{id}/test."""
    ok: bool
    error: Optional[str] = None
    authRequired: bool = False
    serverName: Optional[str] = None
    serverVersion: Optional[str] = None
    protocolVersion: Optional[str] = None
    instructions: Optional[str] = None
    tools: List[McpToolInfo] = []


class McpConnectResult(BaseModel):
    """POST /api/mcp/servers/{id}/connect."""
    authorizationUrl: str


class McpElicitationAnswer(BaseModel):
    """POST /api/mcp/elicitations/{id}: the user's answer to a server's question (elicitation)."""
    action: Literal["accept", "decline", "cancel"]
    content: Optional[Dict[str, Any]] = None  # The form's values (form mode with accept)
    # With accept of a plain confirmation: accept the server's confirmations without asking from now on
    remember: Optional[Literal["conversation", "always"]] = None


class McpAutoAccept(BaseModel):
    """PUT /api/mcp/servers/{id}/auto-accept: accept a server's confirmations without asking, in every conversation."""
    enabled: bool
