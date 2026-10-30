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
    version INTEGER DEFAULT 1,
    "lastModified" BIGINT,
    -- Model catalog selection (NULL = the user's default model, no persona)
    model_id INTEGER,            -- llm_models.id (no FK: models can be deleted, conversations stay)
    persona_id INTEGER,          -- personas.id
    persona_values JSONB         -- values for the persona's variables: {"style": "pirate"}
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
    usage JSONB                  -- {"inputTokens", "outputTokens", "reasoningTokens", "cachedInputTokens", "cost", "currency"}
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
-- Who uploaded which file. Only the owner can read it, through the files API and the agent's file tool
CREATE TABLE IF NOT EXISTS uploaded_files (
    file_id TEXT PRIMARY KEY,                -- file_<ms>_<hex>, the stored filename without extension
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- name: create_indexes
CREATE INDEX IF NOT EXISTS idx_conversation_time ON messages("conversationId", time);
CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations("userId");
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_agent_status ON messages(agent_status) WHERE type = 'agent';
CREATE INDEX IF NOT EXISTS idx_cache_file_id ON file_description_cache(file_id);
CREATE INDEX IF NOT EXISTS idx_uploaded_files_user ON uploaded_files(user_id);
CREATE INDEX IF NOT EXISTS idx_llm_models_provider ON llm_models(provider_id);

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
DROP TRIGGER IF EXISTS update_conversations_timestamp ON conversations;
CREATE TRIGGER update_conversations_timestamp
    BEFORE UPDATE ON conversations
    FOR EACH ROW
    EXECUTE FUNCTION update_conversation_timestamp();

-- name: create_messages_trigger
DROP TRIGGER IF EXISTS update_messages_timestamp ON messages;
CREATE TRIGGER update_messages_timestamp
    BEFORE UPDATE ON messages
    FOR EACH ROW
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
