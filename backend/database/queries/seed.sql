-- Seed Data for Fessi Chat Application
-- This file contains test data for development and testing purposes.
-- Run with: python -m backend.database.db_init --seed

-- name: seed_guest_user
-- Guest user placeholder (ID 0) for guest sessions
-- This must exist for guest session FK constraint
INSERT INTO users (id, email, name)
OVERRIDING SYSTEM VALUE
VALUES (0, 'guest@guest.local', 'Guest User')
ON CONFLICT (id) DO NOTHING;

-- name: seed_users
-- Test users for development
INSERT INTO users (email, name) VALUES
    ('test@example.com', 'Test User'),
    ('admin@example.com', 'Admin User'),
    ('demo@example.com', 'Demo User')
ON CONFLICT (email) DO NOTHING;

-- name: seed_user_settings
-- Default settings for test users
INSERT INTO user_settings (user_id, theme, language)
SELECT id, 'auto', 'en'
FROM users
WHERE email IN ('test@example.com', 'admin@example.com', 'demo@example.com')
ON CONFLICT (user_id) DO NOTHING;

-- name: seed_conversations
-- Example conversations for test user
INSERT INTO conversations (id, "userId", name, participants, version, "lastModified")
SELECT
    'welcome-' || u.id::text,
    u.id,
    'Welcome Conversation',
    '["user", "assistant"]',
    1,
    floor(extract(epoch from now()) * 1000)::bigint
FROM users u
WHERE u.email = 'test@example.com'
ON CONFLICT (id) DO NOTHING;

-- name: seed_messages
-- Welcome message in the example conversation
INSERT INTO messages (id, "conversationId", "roleName", content, time, type, version, "lastModified")
SELECT
    floor(extract(epoch from now()) * 1000)::bigint,
    c.id,
    'assistant',
    'Welcome to Fessi! I''m your AI assistant for waste disposal questions. How can I help you today?',
    floor(extract(epoch from now()) * 1000)::bigint,
    'text',
    1,
    floor(extract(epoch from now()) * 1000)::bigint
FROM conversations c
JOIN users u ON c."userId" = u.id
WHERE u.email = 'test@example.com'
  AND c.id = 'welcome-' || u.id::text
ON CONFLICT (id) DO NOTHING;
