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
    c.model_id,
    c.persona_id,
    c.persona_values,
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
    c.model_id,
    c.persona_id,
    c.persona_values,
    COUNT(m.id) as message_count
FROM conversations c
LEFT JOIN messages m ON c.id = m."conversationId"
WHERE c.id = :conversation_id
GROUP BY c.id;

-- name: get_messages_before_timestamp
-- Get messages before a given timestamp (pagination going back in time)
-- Note: Agent response is now in 'content' column (unified with text messages)
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
    agent_error,
    model_id,
    model_name,
    usage
FROM messages
WHERE "conversationId" = :conversation_id AND time < :before_timestamp
ORDER BY time DESC
LIMIT :limit;

-- name: get_messages_after_timestamp
-- Get messages after a given timestamp (incremental sync)
-- Note: Agent response is now in 'content' column (unified with text messages)
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
    agent_error,
    model_id,
    model_name,
    usage
FROM messages
WHERE "conversationId" = :conversation_id AND time > :after_timestamp
ORDER BY time ASC;

-- name: get_recent_messages_for_context
-- Get recent messages for LLM context building
-- Note: Agent response is now in 'content' column (unified with text messages)
SELECT
    id,
    "roleName",
    content,
    time,
    type,
    agent_status,
    agent_steps,
    agent_error,
    model_id,
    model_name,
    usage
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
    c.model_id,
    c.persona_id,
    c.persona_values,
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

-- name: get_llm_providers_with_model_count
-- All catalog providers with the number of models each one has
SELECT
    p.*,
    COUNT(m.id) AS model_count
FROM llm_providers p
LEFT JOIN llm_models m ON m.provider_id = p.id
GROUP BY p.id
ORDER BY p.name;

-- name: get_llm_provider_with_model_count
-- One catalog provider with its number of models
SELECT
    p.*,
    COUNT(m.id) AS model_count
FROM llm_providers p
LEFT JOIN llm_models m ON m.provider_id = p.id
WHERE p.id = :provider_id
GROUP BY p.id;

-- name: get_llm_models_with_provider
-- Catalog models with their provider's name, kind, currency and tier.
-- The flags narrow the list: enabled models of enabled providers, guest models, auxiliary models, one provider.
SELECT
    m.*,
    p.name AS provider_name,
    p.kind AS provider_kind,
    p.currency AS currency,
    p.privacy_tier AS provider_privacy_tier,
    COALESCE(p.enabled, TRUE) AS provider_enabled,
    COALESCE(m.privacy_tier, p.privacy_tier) AS effective_privacy_tier
FROM llm_models m
JOIN llm_providers p ON p.id = m.provider_id
WHERE (CAST(:enabled_only AS BOOLEAN) IS FALSE OR (COALESCE(m.enabled, TRUE) AND COALESCE(p.enabled, TRUE)))
  AND (CAST(:guests_only AS BOOLEAN) IS FALSE OR COALESCE(m.available_to_guests, FALSE))
  AND (CAST(:auxiliary_only AS BOOLEAN) IS FALSE OR COALESCE(m.is_auxiliary, FALSE))
  AND (CAST(:provider_id AS INTEGER) IS NULL OR m.provider_id = :provider_id)
ORDER BY m.sort_order, m.display_name, m.id;

-- name: get_llm_model_with_provider
-- One catalog model with its provider's name, kind, currency and tier (same columns as above)
SELECT
    m.*,
    p.name AS provider_name,
    p.kind AS provider_kind,
    p.currency AS currency,
    p.privacy_tier AS provider_privacy_tier,
    COALESCE(p.enabled, TRUE) AS provider_enabled,
    COALESCE(m.privacy_tier, p.privacy_tier) AS effective_privacy_tier
FROM llm_models m
JOIN llm_providers p ON p.id = m.provider_id
WHERE m.id = :model_id;
