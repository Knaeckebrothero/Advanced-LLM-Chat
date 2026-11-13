-- PostgreSQL Schema Definition
-- This file contains the DDL for creating all database tables, indexes, and triggers.

-- name: create_users_table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    is_guest BOOLEAN DEFAULT FALSE,  -- created per guest login, deleted once its sessions have expired
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    oidc_sub TEXT UNIQUE  -- the OIDC provider's subject id (AUTH_MODE=oidc)
);

-- name: create_conversations_table
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    "userId" INTEGER NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    participants TEXT,
    "createdAt" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    "lastMessageAt" TIMESTAMP,   -- when the newest message was stored (the sidebar's order), NULL = none yet
    version INTEGER DEFAULT 1,
    "lastModified" BIGINT,
    -- Model catalog selection (NULL = the user's default model, no persona)
    model_id INTEGER,            -- llm_models.id (no FK: models can be deleted, conversations stay)
    persona_id INTEGER,          -- personas.id
    persona_values JSONB,        -- values for the persona's variables: {"style": "pirate"}
    -- Memory review (backend/services/memory_review.py)
    memory_reviewed_until BIGINT,        -- the newest message id the review has read, NULL = none yet
    memory_review_failed_at TIMESTAMP    -- the last review that failed (retried an hour later), NULL after a success
);

-- name: create_messages_table
CREATE TABLE IF NOT EXISTS messages (
    id BIGINT PRIMARY KEY,
    "conversationId" TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    "roleName" TEXT NOT NULL,
    content TEXT NOT NULL,
    time BIGINT NOT NULL,
    type TEXT DEFAULT 'text',
    version INTEGER DEFAULT 1,
    "lastModified" BIGINT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    rating INTEGER,
    -- Agent message columns (JSONB strategy)
    -- Note: Agent response text is stored in 'content' column (unified with text messages)
    agent_status TEXT,           -- thinking, responding, complete, error
    agent_steps JSONB,           -- Array of reasoning steps
    agent_error TEXT,            -- Error message if status is 'error'
    -- Which model wrote an assistant message, and what it cost
    model_id INTEGER,            -- llm_models.id at the time (NULL for the environment model)
    model_name TEXT,             -- copy of the display name, kept if the model is deleted
    usage JSONB,                 -- {"inputTokens", "outputTokens", "reasoningTokens", "cachedInputTokens", "cost", "currency"}
    -- The memory the message belongs to, set when it is stored (docs/past_chats.md): NULL none, 0 the shared
    -- knowledge base, else the personas.id of an agent with its own (no FK)
    memory_vault INTEGER
);

-- name: create_message_tool_records_table
-- The tool record of an answer: the model's tool calls and their results as the model got them,
-- which later answers get back as part of the history (backend/llm/tool_record.py). Only answers
-- that called tools have one. Kept apart from messages, so it never travels with a message list.
CREATE TABLE IF NOT EXISTS message_tool_records (
    message_id BIGINT PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    record JSONB NOT NULL        -- messages in the OpenAI format
);
CREATE INDEX IF NOT EXISTS idx_message_tool_records_conversation ON message_tool_records(conversation_id);

-- name: create_conversation_summaries_table
-- The summary the model gets instead of a conversation's oldest messages, when they no longer
-- fit its context window (backend/services/conversation_summary.py). Deleted when a message it
-- covers is edited, deleted or inserted.
CREATE TABLE IF NOT EXISTS conversation_summaries (
    conversation_id TEXT PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
    covers_until BIGINT NOT NULL,    -- id of the newest message it covers (it covers every message up to it)
    message_count INTEGER NOT NULL,  -- how many messages it covers
    content TEXT NOT NULL,           -- the summary (Markdown)
    model_name TEXT,                 -- the model that wrote it
    created_at BIGINT NOT NULL       -- unix seconds
);

-- name: create_sessions_table
CREATE TABLE IF NOT EXISTS sessions (
    session_key TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    email TEXT NOT NULL,
    is_guest BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    csrf_token TEXT,
    auth_method TEXT,  -- guest, mock or oidc (NULL: sessions from before, guest or mock)
    is_admin BOOLEAN DEFAULT FALSE,  -- granted at login (OIDC_ADMIN_ROLE)
    id_token TEXT  -- the OIDC ID token, for logging out at the provider
);

-- name: create_guest_usage_table
CREATE TABLE IF NOT EXISTS guest_usage (
    ip_address TEXT PRIMARY KEY,
    request_count INTEGER NOT NULL,
    last_request_at TIMESTAMP NOT NULL
);

-- name: create_user_settings_table
CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    theme TEXT NOT NULL,
    language TEXT NOT NULL,
    default_model_id INTEGER,    -- llm_models.id for new conversations
    background TEXT DEFAULT 'none',          -- chat background: 'none' | 'aurora' | 'ridges' | 'custom' (image kept in the browser)
    background_dim INTEGER DEFAULT 25,       -- 0-80, % of the theme background color over the image
    background_blur INTEGER DEFAULT 0,       -- 0-20 px
    editing_mode TEXT DEFAULT 'guided',      -- 'guided' (an edited message is answered again) | 'manual' (edit and insert any message)
    memory_model_id INTEGER,                 -- llm_models.id that reviews conversations for the memory, NULL = the chat's model
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- name: create_file_description_cache_table
-- Caches vision-generated descriptions to avoid repeated API calls
CREATE TABLE IF NOT EXISTS file_description_cache (
    cache_key VARCHAR(64) PRIMARY KEY,
    file_id TEXT NOT NULL,
    query TEXT,
    description TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- name: create_uploaded_files_table
-- The stored files (docs/files.md): what users upload and what tools create (e.g. the images of an MCP
-- server). A file has an owner, who reads it through the files API, and belongs to one conversation,
-- whose agent reads it through the file tools
CREATE TABLE IF NOT EXISTS uploaded_files (
    file_id TEXT PRIMARY KEY,                -- file_<ms>_<hex>, the stored filename without extension
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,  -- NULL: in no conversation (yet)
    message_id BIGINT,                       -- the message it came with: the user's, or the answer a tool made it in
    name TEXT,                               -- "report.pdf" (a name a tool gives is unique in the conversation)
    mime_type TEXT,
    size_bytes BIGINT,
    width INTEGER,                           -- images: pixels
    height INTEGER,
    source TEXT NOT NULL DEFAULT 'upload',   -- 'upload' | 'tool'
    origin TEXT,                             -- a file of a tool: the title of the tool, "Civitai: Run step"
    details TEXT                             -- a file of a tool: the arguments of the call (JSON, cut), e.g. the prompt
);

-- name: create_llm_providers_table
-- One row per API account, seeded from MODEL_CATALOG_FILE. See docs/model_catalog_api.md
CREATE TABLE IF NOT EXISTS llm_providers (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,               -- "Cortecs", "Homelab"
    kind TEXT NOT NULL,                      -- 'openai_compatible' | 'anthropic'
    base_url TEXT,                           -- NULL = the SDK default
    api_key_env TEXT,                        -- name of the environment variable holding the key
    privacy_tier TEXT NOT NULL,              -- 'local' | 'eu' | 'trusted' | 'untrusted'
    currency TEXT NOT NULL DEFAULT 'USD',    -- currency of the model prices: 'USD' | 'EUR'
    default_headers JSONB,                   -- extra HTTP headers, e.g. OpenRouter's HTTP-Referer
    notes TEXT,                              -- jurisdiction, retention, account settings
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- name: create_llm_models_table
-- One row per model offered in the picker
CREATE TABLE IF NOT EXISTS llm_models (
    id SERIAL PRIMARY KEY,
    provider_id INTEGER NOT NULL REFERENCES llm_providers(id) ON DELETE CASCADE,
    display_name TEXT NOT NULL,              -- "Kimi K3 (Cortecs)"
    model_id TEXT NOT NULL,                  -- API model name: "kimi-k3"
    description TEXT,
    supports_tools BOOLEAN DEFAULT TRUE,
    supports_vision BOOLEAN DEFAULT FALSE,
    reasoning TEXT DEFAULT 'none',           -- 'none' | 'optional' | 'always'
    reasoning_passback BOOLEAN DEFAULT FALSE, -- send reasoning_content back in tool loops
    context_window INTEGER,
    max_output_tokens INTEGER,
    temperature REAL,                        -- NULL = provider default
    top_p REAL,
    reasoning_effort TEXT,
    extra_body JSONB,                        -- merged into the request body as-is
    privacy_tier TEXT,                       -- NULL = inherit from the provider
    input_price_per_mtok NUMERIC,            -- in the provider's currency
    output_price_per_mtok NUMERIC,
    is_auxiliary BOOLEAN DEFAULT FALSE,      -- used for background tasks (titles, speech preprocessing)
    available_to_guests BOOLEAN DEFAULT FALSE,
    enabled BOOLEAN DEFAULT TRUE,
    sort_order INTEGER DEFAULT 0,
    notes TEXT,                              -- smoke test results etc.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (provider_id, display_name)
);

-- name: create_personas_table
-- A named system prompt with fill-in variables ({{name}}) and a tool selection ("agents" in the UI)
CREATE TABLE IF NOT EXISTS personas (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,               -- "Pirate"
    description TEXT,
    system_prompt TEXT NOT NULL,             -- "Answer like a {{style}}. Today is {{date}}."
    variables JSONB,                         -- [{"name": "style", "label": "Style", "default": "pirate"}]
    tools JSONB,                             -- tool groups, e.g. ["files", "web_search"], NULL = every enabled tool
    available_to_guests BOOLEAN DEFAULT FALSE,
    enabled BOOLEAN DEFAULT TRUE,
    sort_order INTEGER DEFAULT 0,
    own_memory BOOLEAN DEFAULT FALSE,        -- its own knowledge base and memory per user instead of the user's shared one
    mcp_servers JSONB,                       -- slugs of the admin MCP servers it uses (docs/mcp.md), NULL = none
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- name: create_kb_notes_table
-- A user's knowledge base: Markdown notes the agent reads and writes with the kb_* tools, across all
-- of the user's conversations (backend/services/knowledge_base.py, docs/knowledge_base.md). The note
-- "memory" of a knowledge base is the agent's memory, which is part of every answer.
CREATE TABLE IF NOT EXISTS kb_notes (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    vault INTEGER NOT NULL DEFAULT 0,        -- 0: the user's shared knowledge base, else the personas.id of an agent with its own (no FK)
    slug TEXT NOT NULL,                      -- stable id made from the first title, unique per knowledge base: "project-apollo"
    title TEXT NOT NULL,
    description TEXT,                        -- one sentence, shown in lists and search results
    tags TEXT[] NOT NULL DEFAULT '{}',       -- lowercase
    content TEXT NOT NULL,                   -- Markdown, links to other notes as [[slug]]
    status TEXT NOT NULL DEFAULT 'active',   -- 'active' | 'archived' (kb_archive, an update restores it)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, vault, slug)
);

-- name: kb_notes_unique_per_vault
-- Knowledge bases from before agents could have their own one: add the vault, make slugs unique per vault
ALTER TABLE kb_notes ADD COLUMN IF NOT EXISTS vault INTEGER NOT NULL DEFAULT 0;
CREATE UNIQUE INDEX IF NOT EXISTS kb_notes_user_id_vault_slug_key ON kb_notes(user_id, vault, slug);
ALTER TABLE kb_notes DROP CONSTRAINT IF EXISTS kb_notes_user_id_slug_key;

-- name: add_memory_columns
-- Databases from before the memory get its columns (the CREATE TABLEs above have them), also without
-- app_init --prod, as the conversations trigger below uses them
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS memory_reviewed_until BIGINT;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS memory_review_failed_at TIMESTAMP;
ALTER TABLE personas ADD COLUMN IF NOT EXISTS own_memory BOOLEAN DEFAULT FALSE;
ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS memory_model_id INTEGER;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS memory_vault INTEGER;

-- name: add_mcp_columns
-- Databases from before MCP servers (the CREATE TABLE above has it)
ALTER TABLE personas ADD COLUMN IF NOT EXISTS mcp_servers JSONB;

-- name: add_file_columns
-- Databases from before files belonged to a conversation (the CREATE TABLE above has the columns). The run
-- that adds conversation_id links the existing uploads to their conversations (backfill_file_conversations)
ALTER TABLE uploaded_files ADD COLUMN IF NOT EXISTS conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL;
ALTER TABLE uploaded_files ADD COLUMN IF NOT EXISTS message_id BIGINT;
ALTER TABLE uploaded_files ADD COLUMN IF NOT EXISTS name TEXT;
ALTER TABLE uploaded_files ADD COLUMN IF NOT EXISTS mime_type TEXT;
ALTER TABLE uploaded_files ADD COLUMN IF NOT EXISTS size_bytes BIGINT;
ALTER TABLE uploaded_files ADD COLUMN IF NOT EXISTS width INTEGER;
ALTER TABLE uploaded_files ADD COLUMN IF NOT EXISTS height INTEGER;
ALTER TABLE uploaded_files ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'upload';
ALTER TABLE uploaded_files ADD COLUMN IF NOT EXISTS origin TEXT;
ALTER TABLE uploaded_files ADD COLUMN IF NOT EXISTS details TEXT;

-- name: create_mcp_servers_table
-- MCP servers (docs/mcp.md): the admins' servers, which agents pick (user_id NULL), and users' own
CREATE TABLE IF NOT EXISTS mcp_servers (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,  -- NULL: an admin server, else the user's own
    slug TEXT NOT NULL,                      -- prefix of its tool names, unique per owner, fixed: "github"
    name TEXT NOT NULL,                      -- "GitHub"
    description TEXT,
    transport TEXT NOT NULL DEFAULT 'http',  -- 'http' (Streamable HTTP) | 'sse' | 'stdio' (admin servers only)
    url TEXT,                                -- http, sse (admin servers may use ${VAR})
    command TEXT,                            -- stdio
    args JSONB,                              -- stdio: ["-y", "@modelcontextprotocol/server-filesystem", "/data"]
    env JSONB,                               -- stdio: {"GITHUB_TOKEN": "${GITHUB_TOKEN}"}
    auth TEXT NOT NULL DEFAULT 'none',       -- 'none' | 'headers' | 'oauth'
    headers JSONB,                           -- admin servers: {"Authorization": "Bearer ${X_TOKEN}"}
    headers_encrypted TEXT,                  -- users' servers: the headers, encrypted with ENCRYPTION_KEY
    oauth_client_id TEXT,                    -- a client registered by hand (else dynamic client registration)
    oauth_client_secret_env TEXT,            -- admin servers: env var with that client's secret
    oauth_scopes TEXT,                       -- space-separated, NULL: what the server asks for
    oauth_client_encrypted TEXT,             -- the client from dynamic client registration (encrypted)
    tools JSONB,                             -- MCP tool names offered to the model, NULL = all
    available_to_guests BOOLEAN DEFAULT FALSE,
    enabled BOOLEAN DEFAULT TRUE,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS mcp_servers_owner_slug_key ON mcp_servers(coalesce(user_id, 0), slug);

-- name: create_mcp_tokens_table
-- A user's OAuth sign-in to an MCP server, encrypted (access and refresh token, token endpoint, client)
CREATE TABLE IF NOT EXISTS mcp_tokens (
    server_id INTEGER NOT NULL REFERENCES mcp_servers(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tokens_encrypted TEXT NOT NULL,
    expires_at TIMESTAMP,                    -- when the access token expires (UTC), NULL: unknown
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (server_id, user_id)
);

-- name: create_mcp_oauth_flows_table
-- OAuth sign-ins to MCP servers in progress: between the redirect to the provider and its callback
CREATE TABLE IF NOT EXISTS mcp_oauth_flows (
    state TEXT PRIMARY KEY,
    server_id INTEGER NOT NULL REFERENCES mcp_servers(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    flow_encrypted TEXT NOT NULL,            -- PKCE verifier, redirect URI, token endpoint, client, resource
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- name: create_mcp_auto_accept_table
-- Confirmations of an MCP server a user accepts without being asked (elicitation, docs/mcp.md):
-- in one conversation, or in every one (conversation_id NULL)
CREATE TABLE IF NOT EXISTS mcp_auto_accept (
    id SERIAL PRIMARY KEY,
    server_id INTEGER NOT NULL REFERENCES mcp_servers(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS mcp_auto_accept_key ON mcp_auto_accept(server_id, user_id, coalesce(conversation_id, ''));

-- name: create_kb_note_revisions_table
-- Every version of a note, written in the same transaction as the note: what it was, who wrote it and where
CREATE TABLE IF NOT EXISTS kb_note_revisions (
    id BIGSERIAL PRIMARY KEY,
    note_id BIGINT NOT NULL REFERENCES kb_notes(id) ON DELETE CASCADE,
    action TEXT NOT NULL,                    -- 'create' | 'update' | 'archive' | 'restore'
    title TEXT NOT NULL,
    description TEXT,
    tags TEXT[] NOT NULL DEFAULT '{}',
    content TEXT NOT NULL,
    status TEXT NOT NULL,
    author TEXT NOT NULL,                    -- 'agent' | 'review' (memory review) | 'dream' (nightly consolidation) | 'user' (the page)
    conversation_id TEXT,                    -- where the agent wrote it (no FK: kept when the conversation is deleted)
    persona_id INTEGER,                      -- personas.id of that conversation's agent at the time (no FK)
    reason TEXT,                             -- why it was archived, or which version was restored
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- name: create_memory_dreams_table
-- The nightly consolidation of a knowledge base (backend/services/memory_dream.py): how far it got
CREATE TABLE IF NOT EXISTS memory_dreams (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    vault INTEGER NOT NULL,                  -- as kb_notes.vault: 0 the shared knowledge base, else an agent's id
    dreamed_until BIGINT,                    -- the end of the last period it consolidated (ms, like message ids)
    failed_at TIMESTAMP,                     -- the last run that failed, NULL after a success
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, vault)
);

-- name: create_kb_links_table
-- The notes a note links to ([[slug]] or [text](slug.md)), rebuilt with every write, for the backlinks
CREATE TABLE IF NOT EXISTS kb_links (
    note_id BIGINT NOT NULL REFERENCES kb_notes(id) ON DELETE CASCADE,
    target_slug TEXT NOT NULL,               -- the linked note's slug (it need not exist yet)
    PRIMARY KEY (note_id, target_slug)
);

-- name: create_indexes
CREATE INDEX IF NOT EXISTS idx_conversation_time ON messages("conversationId", time);
CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations("userId");
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_agent_status ON messages(agent_status) WHERE type = 'agent';
CREATE INDEX IF NOT EXISTS idx_cache_file_id ON file_description_cache(file_id);
CREATE INDEX IF NOT EXISTS idx_uploaded_files_user ON uploaded_files(user_id);
CREATE INDEX IF NOT EXISTS idx_uploaded_files_conversation ON uploaded_files(conversation_id);
CREATE INDEX IF NOT EXISTS idx_llm_models_provider ON llm_models(provider_id);
CREATE INDEX IF NOT EXISTS idx_kb_notes_user_updated ON kb_notes(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_kb_note_revisions_note ON kb_note_revisions(note_id);
CREATE INDEX IF NOT EXISTS idx_kb_links_target ON kb_links(target_slug);

-- name: create_update_timestamp_function
CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- name: create_update_conversation_timestamp_function
CREATE OR REPLACE FUNCTION update_conversation_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW."updatedAt" = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- name: create_conversations_trigger
-- A new message only moves "lastMessageAt", and a memory review only its own columns: "updatedAt"
-- stays the last change of the conversation itself
DROP TRIGGER IF EXISTS update_conversations_timestamp ON conversations;
CREATE TRIGGER update_conversations_timestamp
    BEFORE UPDATE ON conversations
    FOR EACH ROW
    WHEN (OLD."lastMessageAt" IS NOT DISTINCT FROM NEW."lastMessageAt"
          AND OLD.memory_reviewed_until IS NOT DISTINCT FROM NEW.memory_reviewed_until
          AND OLD.memory_review_failed_at IS NOT DISTINCT FROM NEW.memory_review_failed_at)
    EXECUTE FUNCTION update_conversation_timestamp();

-- name: create_messages_trigger
-- A message that only joins a memory (the memory review, docs/past_chats.md) keeps its updated_at
DROP TRIGGER IF EXISTS update_messages_timestamp ON messages;
CREATE TRIGGER update_messages_timestamp
    BEFORE UPDATE ON messages
    FOR EACH ROW
    WHEN (OLD.memory_vault IS NOT DISTINCT FROM NEW.memory_vault)
    EXECUTE FUNCTION update_timestamp();

-- name: create_user_settings_trigger
DROP TRIGGER IF EXISTS update_user_settings_timestamp ON user_settings;
CREATE TRIGGER update_user_settings_timestamp
    BEFORE UPDATE ON user_settings
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp();

-- name: create_llm_providers_trigger
DROP TRIGGER IF EXISTS update_llm_providers_timestamp ON llm_providers;
CREATE TRIGGER update_llm_providers_timestamp
    BEFORE UPDATE ON llm_providers
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp();

-- name: create_llm_models_trigger
DROP TRIGGER IF EXISTS update_llm_models_timestamp ON llm_models;
CREATE TRIGGER update_llm_models_timestamp
    BEFORE UPDATE ON llm_models
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp();

-- name: create_personas_trigger
DROP TRIGGER IF EXISTS update_personas_timestamp ON personas;
CREATE TRIGGER update_personas_timestamp
    BEFORE UPDATE ON personas
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp();

-- name: create_kb_notes_trigger
DROP TRIGGER IF EXISTS update_kb_notes_timestamp ON kb_notes;
CREATE TRIGGER update_kb_notes_timestamp
    BEFORE UPDATE ON kb_notes
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp();

-- name: create_mcp_servers_trigger
DROP TRIGGER IF EXISTS update_mcp_servers_timestamp ON mcp_servers;
CREATE TRIGGER update_mcp_servers_timestamp
    BEFORE UPDATE ON mcp_servers
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp();

-- name: create_mcp_tokens_trigger
DROP TRIGGER IF EXISTS update_mcp_tokens_timestamp ON mcp_tokens;
CREATE TRIGGER update_mcp_tokens_timestamp
    BEFORE UPDATE ON mcp_tokens
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp();

-- name: backfill_conversations_last_message_at
-- Conversations from before "lastMessageAt" get the time of their newest message (ids are the server's clock in ms)
UPDATE conversations c
SET "lastMessageAt" = to_timestamp((SELECT max(m.id) FROM messages m WHERE m."conversationId" = c.id) / 1000.0) AT TIME ZONE 'UTC'
WHERE c."lastMessageAt" IS NULL
  AND EXISTS (SELECT 1 FROM messages m WHERE m."conversationId" = c.id);

-- name: create_conversation_memory_vault_function
-- The memory a new message of a conversation belongs to (docs/past_chats.md), from the conversation's agent
-- now. NULL without an agent, for a disabled agent, an agent without the knowledge base, or a guest. The
-- agent's id with its own memory, else 0, the shared knowledge base. The same rule as persona_tool_groups()
-- and persona_vault() in backend/catalog/resolver.py. (No semicolons in these comments: init_tables() splits
-- the statements at them.)
CREATE OR REPLACE FUNCTION conversation_memory_vault(conversation TEXT)
RETURNS INTEGER AS $$
    SELECT CASE
        WHEN u.is_guest OR p.id IS NULL OR p.enabled IS FALSE THEN NULL
        WHEN jsonb_typeof(p.tools) IS DISTINCT FROM 'array' OR NOT (p.tools ? 'knowledge_base') THEN NULL
        WHEN p.own_memory THEN p.id
        ELSE 0
    END
    FROM conversations c
    JOIN users u ON u.id = c."userId"
    LEFT JOIN personas p ON p.id = c.persona_id
    WHERE c.id = conversation
$$ LANGUAGE sql STABLE;

-- name: create_message_memory_vault_trigger
-- Every new message gets its memory, wherever it is stored (sync, insert, import, insert between messages)
CREATE OR REPLACE FUNCTION set_message_memory_vault()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.memory_vault IS NULL THEN
        NEW.memory_vault := conversation_memory_vault(NEW."conversationId");
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS set_messages_memory_vault ON messages;
CREATE TRIGGER set_messages_memory_vault
    BEFORE INSERT ON messages
    FOR EACH ROW
    EXECUTE FUNCTION set_message_memory_vault();

-- name: create_message_search_text_function
-- The text of a message for the search over past chats (docs/past_chats.md). content is plain text, or a
-- JSON object with "content" and "attachments" (a message with attachments), as _parse_content() in
-- backend/services/conversation_history.py reads it. Never fails, since the index below uses it and a
-- failure would keep the message from being stored. Text that starts with "{" but isn't JSON (a pasted
-- snippet) is returned as it is.
CREATE OR REPLACE FUNCTION message_search_text(content TEXT)
RETURNS TEXT AS $$
DECLARE
    parsed JSONB;
BEGIN
    IF content IS NULL OR left(content, 1) <> '{' THEN
        RETURN content;
    END IF;
    BEGIN
        parsed := content::jsonb;
    EXCEPTION WHEN others THEN
        RETURN content;
    END;
    IF jsonb_typeof(parsed) = 'object' AND parsed ? 'content' THEN
        RETURN coalesce(parsed ->> 'content', '');
    END IF;
    RETURN content;
END;
$$ LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE;

-- name: create_message_search_index
-- The trigram index of the search over past chats, for its regular expressions. pg_trgm comes with Postgres
-- and prepare_database() creates it. A server without it gets no index, and the search scans the messages.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm') THEN
        CREATE INDEX IF NOT EXISTS idx_messages_search_trgm ON messages
            USING gin (message_search_text(content) gin_trgm_ops);
    END IF;
END $$;
