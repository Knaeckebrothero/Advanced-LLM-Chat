# MCP servers

Agents can use the tools of [Model Context Protocol](https://modelcontextprotocol.io) servers. There are two kinds:

- **Servers of the agents** (admin servers): an admin adds them on the Agents page (tab "MCP servers") and picks them per agent, like tool groups. Their secrets come from environment variables, like provider keys. A server with OAuth sign-in is shared by its definition, but every user signs in with their own account.
- **Users' own servers**: a signed-in user adds them on the MCP servers page (`/mcp`, sidebar). They reach the chat only through agents that select the opt-in tool group `user_mcp` ("Users' own MCP servers"), never for guests.

Decided by the user on 2026-11-04: both kinds (admin servers first), remote HTTP plus stdio for admins, OAuth sign-in from the start, users' own servers only through agents that opt in.

The client is the official `mcp` Python SDK (2.x, `mcp.Client`), which talks to servers of the 2026-07-28 protocol and falls back to the initialize handshake of older ones.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `MCP_ENABLED` | `true` | Master switch. Off: no MCP tools, the pages say so |
| `MCP_STDIO_ENABLED` | `false` | Admins may define **stdio** servers: commands the backend starts as subprocesses (e.g. `npx -y @modelcontextprotocol/server-filesystem /data`). They run with the backend's rights in its container, so whoever edits agents can run code there; the operator has to allow that. The backend image has neither Node nor uv; a derived image adds what the commands need |
| `MCP_USER_SERVERS` | `true` | Signed-in users may add their own servers |
| `MCP_ALLOW_PRIVATE_URLS` | `false` | Users' own servers (and the OAuth endpoints they name) may be on private, loopback or link-local addresses. Admins' servers, and servers of users who are admins, always may |
| `ENCRYPTION_KEY` | – | Encrypts the users' header values and everyone's OAuth tokens in Postgres (any long random string, e.g. `openssl rand -hex 32`). Without it, OAuth sign-in and users' servers with headers are unavailable (the API says why). Changing it makes the stored secrets unreadable: users sign in again |
| `MCP_OAUTH_REDIRECT_URI` | `${API_URL}/api/mcp/oauth/callback`, else the request's address | Where OAuth providers send the browser back |
| `MCP_OAUTH_CLIENT_NAME` | `LLM Chat` | The client name shown on the provider's consent page (dynamic client registration) |
| `MCP_CONNECT_TIMEOUT` | `20` | Seconds to connect and list a server's tools |
| `MCP_TOOL_TIMEOUT` | `120` | Seconds a tool call may take |
| `MCP_IDLE_TIMEOUT` | `300` | Seconds a connection stays open without use |
| `MCP_MAX_RESULT_CHARS` | `50000` | Longer tool results are cut |

`${VAR}` in an admin server's URL, header values and stdio environment is filled from the backend's environment. The variable's name must end in `_KEY`, `_TOKEN`, `_SECRET` or `_API`, so a definition can't send other server settings (such as `POSTGRES_PASSWORD`) anywhere. An unset variable makes the server unavailable, with the reason.

## Data

- `mcp_servers`: both kinds. `user_id` NULL is an admin server, else the user's own. `slug` (unique per owner, fixed after creation) is the prefix of its tool names. Transport `http` (Streamable HTTP), `sse` (the older HTTP+SSE transport) or `stdio` (admin only). Auth `none`, `headers` or `oauth`. Admin servers keep header values as written (with `${VAR}`); users' header values are encrypted (`headers_encrypted`). `tools`: the MCP tool names offered to the model, NULL for all. `oauth_client_encrypted`: the client from dynamic client registration.
- `mcp_tokens`: a user's OAuth sign-in to a server (`server_id`, `user_id`), encrypted, with the token endpoint and client needed to refresh it.
- `mcp_oauth_flows`: sign-ins in progress (state, PKCE verifier encrypted, user, server), at most 15 minutes old.
- `personas.mcp_servers`: the slugs of the admin servers an agent uses (NULL or `[]` for none).

Deleting a user deletes their servers and tokens (foreign keys); deleting an admin server removes its slug from the agents.

## How an answer gets the tools

`backend/services/mcp/` (`tools.py`, `pool.py`, `oauth.py`, `store.py`):

1. The servers of the answer: the agent's `mcp_servers` (enabled admin servers; for a guest only those marked available to guests), plus the user's own enabled servers if the agent selects `user_mcp` (never for guests). A chat without an agent gets no MCP servers. The admin servers are picked one by one, also by an agent with "all tools" (`tools: null`), which never includes them on its own.
2. Each server is connected (in parallel, `MCP_CONNECT_TIMEOUT`) and its tools listed. Connections are kept per server and user in a pool (`pool.py`), each owned by its own task, and closed after `MCP_IDLE_TIMEOUT` without use, so a conversation doesn't reconnect for every answer and stdio servers don't restart. Every user gets their own connection (and stdio process), so servers never share state between users.
3. Each tool becomes a `Tool` of the registry named `<slug>__<tool name>` (characters other than letters, digits, `_` and `-` become `_`, at most 64 characters, made unique). Its step title is `<server name>: <tool title>`. Only the tools in the server's `tools` selection are offered.
4. A server that can't be reached, or one with OAuth the user hasn't signed in to, gives no tools. The answer starts with an `observation` step "MCP server unavailable" (or "Sign-in needed") naming the server and the reason; its metadata is `{"mcpServer": id, "authRequired": bool}`, which the chat links to the MCP servers page.
5. The system prompt gets a section `## Tools from MCP servers:` listing each connected server, its tool prefix, its description and the instructions the server sends (cut at 2000 characters), and the servers that give no tools this time with the reason. Without that, a model that sees earlier answers with results from a server (as text: the history has no tool calls) but no tools for it now decided it had made those results up (DeepSeek V4.1 Flash, seen live).

Tool results: text content goes to the model as it is; structured content as JSON when there is no text; images, audio and blobs become a short placeholder (`[image/png, 12 KB, not shown]`), resource links their name and URI. A result with `isError` becomes a failed step. Results are cut at `MCP_MAX_RESULT_CHARS`. Arguments are checked against the top level of the tool's schema like every other tool.

## OAuth sign-in

For servers with auth `oauth` (`oauth.py`), as the MCP authorization spec describes:

1. `POST /api/mcp/servers/{id}/connect`: the backend asks the server without a token, reads the protected resource metadata (from the `WWW-Authenticate` header or the well-known URLs), then the authorization server's metadata. It uses the server's configured client (`oauth_client_id`, with the secret from `oauth_client_secret_env` for admin servers), else a client registered earlier, else registers one (dynamic client registration) and stores it. It stores the flow (state, PKCE verifier) and answers with the authorization URL, which the frontend opens.
2. The provider sends the browser to `GET /api/mcp/oauth/callback`. The flow must belong to the session's user. The backend swaps the code for tokens (with the `resource` parameter, RFC 8707), stores them encrypted and redirects to `{FRONTEND_URL}/mcp?connected=<id>`, or `?error=<reason>&server=<id>`.
3. Connections send the access token and refresh it with the refresh token when it has expired or the server answers 401. A refresh that fails deletes the tokens: the user has to sign in again (the step says so).

`DELETE /api/mcp/servers/{id}/connection` signs out (deletes the tokens).

## HTTP API

All bodies are camelCase JSON; authentication and CSRF as for the other endpoints. Guests get 403 everywhere except `GET /api/mcp/config`.

### For signed-in users

| Method and path | Body | Response |
|---|---|---|
| `GET /api/mcp/config` | | `McpConfig` |
| `GET /api/mcp/servers` | | `McpServerList`: `own` (the user's servers) and `shared` (enabled admin servers with OAuth, to sign in to; for users who aren't admins without headers, environment, command and OAuth client) |
| `POST /api/mcp/servers` | `McpServerCreate` | `McpServerOut` (an own server; `http` or `sse`) |
| `PUT /api/mcp/servers/{id}` | `McpServerUpdate` | `McpServerOut` (own servers only) |
| `DELETE /api/mcp/servers/{id}` | | 204 (own servers only) |
| `POST /api/mcp/servers/{id}/test` | | `McpTestResult`: connects as the current user and lists the tools (own servers, shared OAuth servers, and any admin server for admins) |
| `POST /api/mcp/servers/{id}/connect` | | `{"authorizationUrl": str}` (OAuth servers the user may sign in to) |
| `DELETE /api/mcp/servers/{id}/connection` | | 204 |
| `GET /api/mcp/oauth/callback` | | redirect to the frontend |

### Admin only

| Method and path | Body | Response |
|---|---|---|
| `GET /api/admin/mcp-servers` | | `McpServerOut[]` (admin servers) |
| `POST /api/admin/mcp-servers` | `McpServerCreate` | `McpServerOut` |
| `PUT /api/admin/mcp-servers/{id}` | `McpServerUpdate` | `McpServerOut` |
| `DELETE /api/admin/mcp-servers/{id}` | | 204 |

Errors: 400 invalid input (message in `detail`), 403 not allowed, 404 unknown server, 409 slug taken, 503 a feature the configuration switches off (e.g. no `ENCRYPTION_KEY`).

### Models (`backend/models/mcp.py`)

```text
McpConfig        enabled, userServers, stdio, encryption, privateUrls (bools),
                 reason (why MCP or users' servers are off; null otherwise)

McpServerCreate  name                       "GitHub"
                 slug?                      tool name prefix: a-z, 0-9 and _, starting with a letter, at most
                                            24 characters; made from the name if left out; can't be changed
                 description?               what it is for (also shown to the model)
                 transport = "http"         "http" | "sse" | "stdio" (stdio: admins with MCP_STDIO_ENABLED)
                 url?                       http and sse; admin servers may use ${VAR}
                 command?, args = [],       stdio
                 env = {}
                 auth = "none"              "none" | "headers" | "oauth"
                 headers?                   auth "headers": {"Authorization": "Bearer ${GITHUB_TOKEN}"};
                                            users' values are stored encrypted and never returned
                 oauthClientId?             OAuth with a client registered by hand (else dynamic registration)
                 oauthClientSecretEnv?      admin servers: env var with that client's secret (_KEY/_TOKEN/_SECRET)
                 oauthScopes?               space-separated; else what the server asks for
                 tools = null               MCP tool names offered to the model; null = all
                 availableToGuests = false  admin servers
                 enabled = true
                 sortOrder = 0

McpServerUpdate  the same fields, all optional; left out = unchanged. slug can't change. headers: an object
                 replaces them; for users' servers a header sent with an empty value keeps its stored value.

McpServerOut     id, shared (true for admin servers), name, slug, description, transport, url, command, args,
                 env, auth, headers (admin servers: as written; users' servers: null), headerNames,
                 oauthClientId, oauthClientSecretEnv, oauthScopes, tools, availableToGuests, enabled,
                 sortOrder,
                 connected (OAuth: the current user has signed in; null for other auth),
                 unavailableReason (e.g. "MCP_STDIO_ENABLED is off", "ENCRYPTION_KEY is not set",
                 "GITHUB_TOKEN is not set"; null when usable),
                 createdAt, updatedAt

McpToolInfo      name, title?, description?, readOnly?, destructive? (the server's annotations),
                 enabled (in the server's tools selection)

McpTestResult    ok, error?, authRequired, serverName?, serverVersion?, protocolVersion?, instructions?,
                 tools: McpToolInfo[]
```

### Agents

- `PersonaCreate`, `PersonaUpdate`, `PersonaOut`: `mcpServers` (list of admin server slugs, null = none). Unknown slugs are a 400.
- Tool group `user_mcp` ("Users' own MCP servers"): opt-in like `knowledge_base`; `GET /api/admin/tools` lists it, unavailable when `MCP_ENABLED` or `MCP_USER_SERVERS` is off.
- Catalog file: a top-level `mcp_servers` section (snake_case keys of `mcp_servers`, natural key `slug`, never the encrypted columns) and `mcp_servers` on personas. Seeding creates missing servers only, the import upserts them, the export writes the admin servers.

## Tests

`python backend/services/tests/mcp_test.py` (13 checks) runs against real MCP servers of the SDK on free local ports (Streamable HTTP, one that wants a header, the older SSE transport, one behind a small OAuth authorization server with dynamic client registration, PKCE and refresh tokens, and one over stdio) and a real Postgres, in a `<POSTGRES_DB>_mcp_test` database it creates itself. It covers the definitions and their rules, which servers an answer gets, the tools and their results, the pool, the address guard, the OAuth sign-in from start to refresh, the catalog file, the answer's tools in `messages.py` and the API.

## Not built yet

- **Asking before a tool runs.** Many MCP tools write or delete; the agent loop can't pause for the user's approval yet. Until then, offer only the tools an agent should run on its own (the server's tool selection), and mind the `destructive` hint in the tool list.
- Images from tool results for vision models, resources and prompts of MCP servers, sampling and elicitation requests from servers.
- Revoking tokens at the provider when signing out.
