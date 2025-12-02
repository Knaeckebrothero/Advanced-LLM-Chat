-- Complex SQL Queries
-- This file contains queries involving JOINs, aggregations, and business logic.

-- name: get_conversation_with_message_count
-- Get a conversation with its message count
SELECT
    c.id,
    c."userId",
    c.name,
    c.participants,
    c."createdAt",
    c."updatedAt",
    c.version,
    c."lastModified",
    COUNT(m.id) as message_count
FROM conversations c
LEFT JOIN messages m ON c.id = m."conversationId"
WHERE c.id = :conversation_id AND c."userId" = :user_id
GROUP BY c.id;

-- name: get_conversation_with_message_count_guest
-- Get a conversation with its message count (for guest users - no user check)
SELECT
    c.id,
    c."userId",
    c.name,
    c.participants,
    c."createdAt",
    c."updatedAt",
    c.version,
    c."lastModified",
    COUNT(m.id) as message_count
FROM conversations c
LEFT JOIN messages m ON c.id = m."conversationId"
WHERE c.id = :conversation_id
GROUP BY c.id;

-- name: get_messages_before_timestamp
-- Get messages before a given timestamp (pagination going back in time)
SELECT
    id,
    "conversationId",
    "roleName",
    content,
    time,
    type,
    version,
    "lastModified",
    updated_at,
    rating,
    agent_status,
    agent_steps,
    final_response,
    agent_error
FROM messages
WHERE "conversationId" = :conversation_id AND time < :before_timestamp
ORDER BY time DESC
LIMIT :limit;

-- name: get_messages_after_timestamp
-- Get messages after a given timestamp (incremental sync)
SELECT
    id,
    "conversationId",
    "roleName",
    content,
    time,
    type,
    version,
    "lastModified",
    updated_at,
    rating,
    agent_status,
    agent_steps,
    final_response,
    agent_error
FROM messages
WHERE "conversationId" = :conversation_id AND time > :after_timestamp
ORDER BY time ASC;

-- name: get_recent_messages_for_context
-- Get recent messages for LLM context building
SELECT
    id,
    "roleName",
    content,
    time,
    type,
    agent_status,
    agent_steps,
    final_response,
    agent_error
FROM messages
WHERE "conversationId" = :conversation_id
ORDER BY time DESC
LIMIT :limit;

-- name: get_conversations_with_last_message
-- Get all conversations for a user with their last message timestamp
SELECT
    c.id,
    c."userId",
    c.name,
    c.participants,
    c."createdAt",
    c."updatedAt",
    c.version,
    c."lastModified",
    MAX(m.time) as last_message_time
FROM conversations c
LEFT JOIN messages m ON c.id = m."conversationId"
WHERE c."userId" = :user_id
GROUP BY c.id
ORDER BY COALESCE(MAX(m.time), EXTRACT(EPOCH FROM c."createdAt") * 1000) DESC;

-- name: delete_conversation_cascade
-- Delete a conversation and all its messages (handled by ON DELETE CASCADE, but explicit for clarity)
DELETE FROM conversations WHERE id = :conversation_id AND "userId" = :user_id;

-- name: cleanup_expired_sessions
-- Delete all expired sessions
DELETE FROM sessions WHERE expires_at < CURRENT_TIMESTAMP;

-- name: get_active_session_count
-- Count active sessions for a user
SELECT COUNT(*) as count
FROM sessions
WHERE user_id = :user_id AND expires_at > CURRENT_TIMESTAMP;
