/**
 * MCP servers as the API returns them (backend/models/mcp.py, docs/mcp.md): servers of the
 * Model Context Protocol whose tools agents use. Admin servers (`shared`) are picked per agent on
 * the Agents page; signed-in users add their own on the MCP servers page, which reach the chat only
 * through agents with the tool group `user_mcp`.
 */

/** `http`: Streamable HTTP; `sse`: the older HTTP+SSE transport; `stdio`: a command (admins only). */
export type McpTransport = 'http' | 'sse' | 'stdio';
export type McpAuth = 'none' | 'headers' | 'oauth';

export const MCP_TRANSPORTS: McpTransport[] = ['http', 'sse', 'stdio'];
export const MCP_AUTH_MODES: McpAuth[] = ['none', 'headers', 'oauth'];

/** `${VAR}` in admin servers must name a variable ending in one of these (docs/mcp.md). */
export const MCP_SECRET_VAR_SUFFIXES = ['_KEY', '_TOKEN', '_SECRET', '_API'];

/** Tool name prefix: a-z, 0-9 and _, starting with a letter, at most 24 characters. */
export const MCP_SLUG_PATTERN = /^[a-z][a-z0-9_]{0,23}$/;

/** GET /api/mcp/config: what the server's configuration allows. */
export interface IMcpConfig {
  enabled: boolean;
  userServers: boolean;  // Signed-in users may add their own servers
  stdio: boolean;  // Admins may define stdio servers (MCP_STDIO_ENABLED)
  encryption: boolean;  // ENCRYPTION_KEY is set: OAuth sign-in and users' headers work
  privateUrls: boolean;  // Users' own servers may be on private addresses
  reason?: string | null;  // Why MCP or users' servers are off
}

export interface IMcpServerCreate {
  name: string;
  slug?: string | null;  // Made from the name if left out; can't be changed later
  description?: string | null;
  transport: McpTransport;
  url?: string | null;  // http and sse; admin servers may use ${VAR}
  command?: string | null;  // stdio
  args?: string[];
  env?: Record<string, string>;
  auth: McpAuth;
  /** auth "headers". Users' values are stored encrypted and never returned; an empty value on update keeps the stored one. */
  headers?: Record<string, string> | null;
  oauthClientId?: string | null;  // A client registered by hand (else dynamic registration)
  oauthClientSecretEnv?: string | null;  // Admin servers: env var with that client's secret
  oauthScopes?: string | null;  // Space-separated; else what the server asks for
  tools?: string[] | null;  // MCP tool names offered to the model; null = all
  availableToGuests?: boolean;  // Admin servers
  enabled?: boolean;
  sortOrder?: number;
}

/** Partial update: fields left out stay unchanged; the slug can't change. */
export type IMcpServerUpdate = Partial<Omit<IMcpServerCreate, 'slug'>>;

export interface IMcpServerOut {
  id: number;
  shared: boolean;  // An admin server (the agents'), not a user's own
  name: string;
  slug: string;
  description?: string | null;
  transport: McpTransport;
  url?: string | null;
  command?: string | null;
  args: string[];
  env: Record<string, string>;
  auth: McpAuth;
  headers?: Record<string, string> | null;  // Admin servers: as written; users' servers: null
  headerNames: string[];
  oauthClientId?: string | null;
  oauthClientSecretEnv?: string | null;
  oauthScopes?: string | null;
  tools?: string[] | null;
  availableToGuests: boolean;
  enabled: boolean;
  sortOrder: number;
  connected?: boolean | null;  // OAuth: the current user has signed in; null for other auth
  autoAccept?: boolean | null;  // The current user accepts its confirmations without asking (elicitation)
  unavailableReason?: string | null;  // null when usable
  createdAt?: string | null;
  updatedAt?: string | null;
}

/** GET /api/mcp/servers */
export interface IMcpServerList {
  own: IMcpServerOut[];  // The user's own servers
  shared: IMcpServerOut[];  // Enabled admin servers with OAuth, to sign in to
  autoAccepted?: IMcpServerOut[];  // Other agents' servers whose confirmations the user accepts without asking
}

export interface IMcpToolInfo {
  name: string;
  title?: string | null;
  description?: string | null;
  readOnly?: boolean | null;  // The server's annotations
  destructive?: boolean | null;
  enabled: boolean;  // In the server's tools selection
}

/** POST /api/mcp/servers/{id}/test: connects as the current user and lists the tools. */
export interface IMcpTestResult {
  ok: boolean;
  error?: string | null;
  authRequired: boolean;
  serverName?: string | null;
  serverVersion?: string | null;
  protocolVersion?: string | null;
  instructions?: string | null;
  tools: IMcpToolInfo[];
}

/** POST /api/mcp/servers/{id}/connect */
export interface IMcpConnectResult {
  authorizationUrl: string;
}

/**
 * A server's question to the user while one of its tools runs (elicitation, docs/mcp.md
 * "Questions from servers"): the `elicitation` metadata of an answer's step (an observation
 * with the id `elicitation-<id>`, the question as its content). While it is `pending`, the chat
 * shows it with its fields and buttons and answers with POST /api/mcp/elicitations/{id}; the
 * stream then replaces the step with the outcome.
 */
export type McpElicitationStatus = 'pending' | 'accept' | 'decline' | 'cancel' | 'timeout';
export type McpElicitationAction = 'accept' | 'decline' | 'cancel';
/** How long a plain confirmation is accepted without asking: in this conversation, or in every one. */
export type McpAutoAcceptScope = 'conversation' | 'always';

/** One field of a form question: a flat JSON schema property (strings, numbers, booleans, enums). */
export interface IMcpElicitationProperty {
  type?: 'string' | 'number' | 'integer' | 'boolean' | 'array';
  title?: string;
  description?: string;
  default?: unknown;
  enum?: string[];
  enumNames?: string[];  // Labels of `enum` (older servers)
  oneOf?: Array<{ const: string; title?: string }>;  // Choices with labels
  anyOf?: Array<{ const: string; title?: string }>;
  items?: { type?: string; enum?: string[]; anyOf?: Array<{ const: string; title?: string }> };
  format?: 'email' | 'uri' | 'date' | 'date-time';
  minimum?: number;
  maximum?: number;
  minLength?: number;
  maxLength?: number;
  minItems?: number;
  maxItems?: number;
}

export interface IMcpElicitation {
  id: string;
  server: string;  // The name of the server that asks
  mode: 'form' | 'url';
  status: McpElicitationStatus;
  schema?: { properties?: Record<string, IMcpElicitationProperty>; required?: string[] };  // Form mode
  url?: string;  // URL mode: the page the server wants the user to open
  answer?: Record<string, unknown>;  // The values the user sent (form mode, accepted)
  confirmation?: boolean;  // A plain confirmation (no input needed): may be accepted without asking from now on
  conversation?: boolean;  // Asked within a conversation ("for the rest of this chat" is possible)
  auto?: McpAutoAcceptScope;  // Accepted without asking, by the user's earlier choice
  remember?: McpAutoAcceptScope;  // Accepted, and from now on without asking
}
