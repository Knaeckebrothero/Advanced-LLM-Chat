-- PostgreSQL Schema Definition
-- This file contains the DDL for creating all database tables, indexes, and triggers.

-- name: create_users_table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    "lastModified" BIGINT
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
    agent_status TEXT,           -- thinking, responding, complete, error
    agent_steps JSONB,           -- Array of reasoning steps
    final_response TEXT,         -- Final response text
    agent_error TEXT             -- Error message if status is 'error'
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
    csrf_token TEXT
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
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- name: create_indexes
CREATE INDEX IF NOT EXISTS idx_conversation_time ON messages("conversationId", time);
CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations("userId");
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_agent_status ON messages(agent_status) WHERE type = 'agent';

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
