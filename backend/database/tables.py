"""
SQLAlchemy Core table definitions for the database schema.

This module defines all database tables using SQLAlchemy's Core API (not ORM).
Tables are defined using MetaData for use with raw SQL queries via SQLAlchemy Core.
"""
from sqlalchemy import (
    MetaData,
    Table,
    Column,
    Integer,
    BigInteger,
    String,
    Text,
    Boolean,
    Date,
    DateTime,
    Float,
    Numeric,
    UniqueConstraint,
    ForeignKey,
    Index,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

# Create metadata instance
metadata = MetaData()

# Users table
users = Table(
    'users',
    metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('email', Text, unique=True, nullable=False),
    Column('name', Text),
    Column('is_guest', Boolean, server_default='false'),  # One user per guest login
    Column('created_at', DateTime, server_default=func.now()),
    Column('oidc_sub', Text, unique=True),  # The OIDC provider's subject id (AUTH_MODE=oidc)
)

# Conversations table with UUID support
conversations = Table(
    'conversations',
    metadata,
    Column('id', Text, primary_key=True),  # UUID as text
    Column('userId', Integer, ForeignKey('users.id'), nullable=False),
    Column('name', Text, nullable=False),
    Column('participants', Text),  # JSON-encoded list
    Column('createdAt', DateTime, server_default=func.now()),
    Column('updatedAt', DateTime, server_default=func.now(), onupdate=func.now()),
    Column('lastMessageAt', DateTime),  # When the newest message was stored (naive UTC), the sidebar's order
    Column('version', Integer, server_default='1'),
    Column('lastModified', BigInteger),
    # Model catalog selection (NULL = the user's default model, no persona)
    Column('model_id', Integer),  # llm_models.id (no FK: deleting a model keeps conversations)
    Column('persona_id', Integer),  # personas.id
    Column('persona_values', JSONB),  # Values for the persona's variables
    # Memory review (backend/services/memory_review.py)
    Column('memory_reviewed_until', BigInteger),  # The newest message id the review has read
    Column('memory_review_failed_at', DateTime),  # The last failed review (naive UTC), NULL after a success
    Column('hidden', Boolean, nullable=False, server_default='false'),  # Hidden
    Column('hidden_by', Text),  # Who set hidden: 'user' (agents leave it alone) or 'agent', None = nobody
    # The conversation's own system prompt (manual editing): None = built from its agent, '' = none
    Column('system_prompt', Text),
)

# Messages table
messages = Table(
    'messages',
    metadata,
    Column('id', BigInteger, primary_key=True),  # Millisecond timestamp-based ID
    Column('conversationId', Text, ForeignKey('conversations.id'), nullable=False),
    Column('roleName', Text, nullable=False),
    Column('content', Text, nullable=False),
    Column('time', BigInteger, nullable=False),  # Unix timestamp
    Column('type', Text, server_default='text'),  # 'text', 'voice', or 'agent'
    Column('version', Integer, server_default='1'),
    Column('lastModified', BigInteger),
    Column('updated_at', DateTime, server_default=func.now(), onupdate=func.now()),
    Column('rating', Integer),  # 0 (thumbs down), 1 (thumbs up), or NULL
    # Agent message columns (JSONB strategy)
    # Note: Agent response text is stored in 'content' column (unified with text messages)
    Column('agent_status', Text),  # thinking, responding, complete, error
    Column('agent_steps', JSONB),  # Array of reasoning steps
    Column('agent_error', Text),  # Error message if status is 'error'
    # Which model wrote an assistant message, and what it cost
    Column('model_id', Integer),  # llm_models.id at the time (NULL for the environment model)
    Column('model_name', Text),  # Copy of the display name, kept if the model is deleted
    Column('usage', JSONB),  # inputTokens, outputTokens, reasoningTokens, cachedInputTokens, cost, currency
    # The memory it belongs to, set by a trigger when it is stored (docs/past_chats.md): None none,
    # 0 the shared knowledge base, else the personas.id of an agent with its own
    Column('memory_vault', Integer),
)

# The tool record of an answer: its tool calls and their results as the model got them
# (backend/llm/tool_record.py). Only answers that called tools have one.
message_tool_records = Table(
    'message_tool_records',
    metadata,
    Column('message_id', BigInteger, ForeignKey('messages.id', ondelete='CASCADE'), primary_key=True),
    Column('conversation_id', Text, ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False),
    Column('record', JSONB, nullable=False),  # Messages in the OpenAI format
)

# The summary the model gets instead of a conversation's oldest messages (one per conversation)
conversation_summaries = Table(
    'conversation_summaries',
    metadata,
    Column('conversation_id', Text, ForeignKey('conversations.id', ondelete='CASCADE'), primary_key=True),
    Column('covers_until', BigInteger, nullable=False),  # Id of the newest message it covers
    Column('message_count', Integer, nullable=False),  # How many messages it covers
    Column('content', Text, nullable=False),
    Column('model_name', Text),  # The model that wrote it
    Column('created_at', BigInteger, nullable=False),  # Unix seconds
)

# The agent's memory as a conversation's system prompt shows it (backend/services/memory_snapshot.py)
conversation_memory_snapshots = Table(
    'conversation_memory_snapshots',
    metadata,
    Column('conversation_id', Text, ForeignKey('conversations.id', ondelete='CASCADE'), primary_key=True),
    Column('vault', Integer, nullable=False),  # The knowledge base of the memory: 0 = the user's shared one
    Column('family_mode', Boolean, nullable=False),  # Taken for a device in family mode (no hidden lines)
    Column('content', Text, nullable=False),  # The memory as the prompt shows it ('' = empty)
    Column('day', Date, nullable=False),  # The day the prompt calls today
    Column('taken_at', DateTime, nullable=False, server_default=func.now()),
)

# Sessions table
sessions = Table(
    'sessions',
    metadata,
    Column('session_key', Text, primary_key=True),
    Column('user_id', Integer, ForeignKey('users.id'), nullable=False),
    Column('email', Text, nullable=False),
    Column('is_guest', Boolean, server_default='false'),
    Column('created_at', DateTime, server_default=func.now()),
    Column('expires_at', DateTime, nullable=False),
    Column('last_activity', DateTime, server_default=func.now()),
    Column('csrf_token', Text),
    Column('auth_method', Text),  # guest, mock or oidc (NULL: sessions from before, guest or mock)
    Column('is_admin', Boolean, server_default='false'),  # Granted at login (OIDC_ADMIN_ROLE)
    Column('id_token', Text),  # The OIDC ID token, for logging out at the provider
)

# Guest usage table for rate limiting
guest_usage = Table(
    'guest_usage',
    metadata,
    Column('ip_address', Text, primary_key=True),
    Column('request_count', Integer, nullable=False),
    Column('last_request_at', DateTime, nullable=False),
)

# User settings table
user_settings = Table(
    'user_settings',
    metadata,
    Column('user_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('theme', Text, nullable=False),
    Column('language', Text, nullable=False),
    Column('default_model_id', Integer),  # llm_models.id for new conversations
    Column('background', Text, server_default='none'),  # 'none' | 'aurora' | 'ridges' | 'custom'
    Column('background_dim', Integer, server_default='25'),  # 0-80 %
    Column('background_blur', Integer, server_default='0'),  # 0-20 px
    Column('editing_mode', Text, server_default='guided'),  # 'guided' | 'manual'
    Column('memory_model_id', Integer),  # llm_models.id that reviews conversations for the memory, NULL = the chat's
    Column('auto_hide_prompt', Text),  # What agents hide on their own, in the user's words; NULL = the server's
    Column('updated_at', DateTime, server_default=func.now(), onupdate=func.now()),
)

# File description cache table
# Caches vision-generated descriptions to avoid repeated API calls
file_description_cache = Table(
    'file_description_cache',
    metadata,
    Column('cache_key', Text, primary_key=True),  # SHA256(file_id + query)
    Column('file_id', Text, nullable=False),
    Column('query', Text),  # Optional query used for description
    Column('description', Text, nullable=False),
    Column('created_at', DateTime, server_default=func.now()),
)

# The stored files (docs/files.md): uploads and what tools create. The owner reads a file through
# the files API; the agent of the conversation it belongs to reads it through the file tools
uploaded_files = Table(
    'uploaded_files',
    metadata,
    Column('file_id', Text, primary_key=True),  # file_<ms>_<hex>, the stored filename without extension
    Column('user_id', Integer, ForeignKey('users.id'), nullable=False),
    Column('created_at', DateTime, server_default=func.now()),
    Column('conversation_id', Text, ForeignKey('conversations.id', ondelete='SET NULL')),  # NULL: in none (yet)
    Column('message_id', BigInteger),  # The message it came with: the user's, or the answer a tool made it in
    Column('name', Text),  # Tools' files have names that are unique in the conversation
    Column('mime_type', Text),
    Column('size_bytes', BigInteger),
    Column('width', Integer),  # Images: pixels
    Column('height', Integer),
    Column('source', Text, nullable=False, server_default='upload'),  # 'upload' | 'tool'
    Column('origin', Text),  # Tools' files: the tool's title
    Column('details', Text),  # Tools' files: the call's arguments (JSON, cut)
)

# Model catalog: one row per API account, seeded from MODEL_CATALOG_FILE
llm_providers = Table(
    'llm_providers',
    metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('name', Text, unique=True, nullable=False),
    Column('kind', Text, nullable=False),  # 'openai_compatible' | 'anthropic'
    Column('base_url', Text),  # NULL = the SDK default
    Column('api_key_env', Text),  # Name of the environment variable holding the key
    Column('privacy_tier', Text, nullable=False),  # 'local' | 'eu' | 'trusted' | 'untrusted'
    Column('currency', Text, nullable=False, server_default='USD'),  # Currency of the model prices
    Column('reported_cost_unit', Numeric),  # One unit of a response's usage.cost in that currency; NULL = not used
    Column('default_headers', JSONB),
    Column('notes', Text),
    Column('enabled', Boolean, server_default='true'),
    Column('created_at', DateTime, server_default=func.now()),
    Column('updated_at', DateTime, server_default=func.now(), onupdate=func.now()),
)

# Model catalog: one row per model offered in the picker
llm_models = Table(
    'llm_models',
    metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('provider_id', Integer, ForeignKey('llm_providers.id', ondelete='CASCADE'), nullable=False),
    Column('display_name', Text, nullable=False),
    Column('model_id', Text, nullable=False),  # API model name
    Column('description', Text),
    Column('supports_tools', Boolean, server_default='true'),
    Column('supports_vision', Boolean, server_default='false'),
    Column('reasoning', Text, server_default='none'),  # 'none' | 'optional' | 'always'
    Column('reasoning_passback', Boolean, server_default='false'),
    Column('context_window', Integer),
    Column('max_output_tokens', Integer),
    Column('temperature', Float),
    Column('top_p', Float),
    Column('reasoning_effort', Text),
    Column('extra_body', JSONB),
    Column('privacy_tier', Text),  # NULL = inherit from the provider
    Column('input_price_per_mtok', Numeric),
    Column('output_price_per_mtok', Numeric),
    Column('cached_input_price_per_mtok', Numeric),  # Input read from the provider's cache; NULL = the input price
    Column('is_auxiliary', Boolean, server_default='false'),  # Used for titles and speech preprocessing
    Column('available_to_guests', Boolean, server_default='false'),
    Column('enabled', Boolean, server_default='true'),
    Column('sort_order', Integer, server_default='0'),
    Column('notes', Text),
    Column('created_at', DateTime, server_default=func.now()),
    Column('updated_at', DateTime, server_default=func.now(), onupdate=func.now()),
    UniqueConstraint('provider_id', 'display_name'),
)

# Model catalog: a named system prompt with fill-in variables and a tool selection ("agents" in the UI)
personas = Table(
    'personas',
    metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('name', Text, unique=True, nullable=False),
    Column('description', Text),
    Column('system_prompt', Text, nullable=False),  # May contain {{variable}} placeholders
    Column('variables', JSONB),  # [{"name", "label", "default"}]
    Column('tools', JSONB),  # Tool groups, e.g. ["files", "web_search"], NULL = every enabled tool
    Column('available_to_guests', Boolean, server_default='false'),
    Column('enabled', Boolean, server_default='true'),
    Column('sort_order', Integer, server_default='0'),
    Column('own_memory', Boolean, server_default='false'),  # Its own knowledge base and memory per user
    Column('mcp_servers', JSONB),  # Slugs of the admin MCP servers it uses (docs/mcp.md), NULL = none
    Column('skills', JSONB),  # Names of its skills (docs/skills.md), NULL = none
    Column('hidden', Boolean, nullable=False, server_default='false'),  # Hidden with its chats and own knowledge base
    Column('created_at', DateTime, server_default=func.now()),
    Column('updated_at', DateTime, server_default=func.now(), onupdate=func.now()),
)

# Skills (docs/skills.md): texts that tell an agent how to do one kind of work, written by admins,
# attached to agents (personas.skills) and loaded by the agent with use_skill
skills = Table(
    'skills',
    metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('name', Text, unique=True, nullable=False),  # "image-generation" (SKILL.md: lowercase, digits, hyphens)
    Column('description', Text, nullable=False),  # What it does and when to use it: all the model sees before loading it
    Column('content', Text, nullable=False),  # The instructions, Markdown
    Column('enabled', Boolean, nullable=False, server_default='true'),
    Column('created_at', DateTime, server_default=func.now()),
    Column('updated_at', DateTime, server_default=func.now(), onupdate=func.now()),
)

# Knowledge base: a user's Markdown notes, read and written by the agent's kb_* tools. The note
# "memory" of a knowledge base is the agent's memory, part of every answer.
kb_notes = Table(
    'kb_notes',
    metadata,
    Column('id', BigInteger, primary_key=True, autoincrement=True),
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
    # 0: the user's shared knowledge base, else the personas.id of an agent with its own (no FK)
    Column('vault', Integer, nullable=False, server_default='0'),
    Column('slug', Text, nullable=False),  # Stable id made from the first title, unique per knowledge base
    Column('title', Text, nullable=False),
    Column('description', Text),  # One sentence for lists and search results
    Column('tags', ARRAY(Text), nullable=False, server_default='{}'),
    Column('content', Text, nullable=False),  # Markdown, links as [[slug]]
    Column('status', Text, nullable=False, server_default='active'),  # 'active' | 'archived'
    Column('hidden', Boolean, nullable=False, server_default='false'),  # Hidden
    Column('hidden_by', Text),  # Who set hidden: 'user' (agents leave it alone) or 'agent', None = nobody
    Column('created_at', DateTime, server_default=func.now()),
    Column('updated_at', DateTime, server_default=func.now(), onupdate=func.now()),
    UniqueConstraint('user_id', 'vault', 'slug'),
)

# Every version of a note, with who wrote it and in which conversation
kb_note_revisions = Table(
    'kb_note_revisions',
    metadata,
    Column('id', BigInteger, primary_key=True, autoincrement=True),
    Column('note_id', BigInteger, ForeignKey('kb_notes.id', ondelete='CASCADE'), nullable=False),
    Column('action', Text, nullable=False),  # 'create' | 'update' | 'archive' | 'restore'
    Column('title', Text, nullable=False),
    Column('description', Text),
    Column('tags', ARRAY(Text), nullable=False, server_default='{}'),
    Column('content', Text, nullable=False),
    Column('status', Text, nullable=False),
    Column('author', Text, nullable=False),  # 'agent' | 'review' | 'dream' (memory review, consolidation) | 'user' (the page)
    Column('conversation_id', Text),  # No FK: kept when the conversation is deleted
    Column('persona_id', Integer),  # No FK
    Column('reason', Text),  # Why it was archived, or which version was restored
    Column('created_at', DateTime, server_default=func.now()),
)

# The slugs a note links to, rebuilt with every write (backlinks)
kb_links = Table(
    'kb_links',
    metadata,
    Column('note_id', BigInteger, ForeignKey('kb_notes.id', ondelete='CASCADE'), primary_key=True),
    Column('target_slug', Text, primary_key=True),  # Need not exist (yet)
)

# The nightly consolidation of a knowledge base (backend/services/memory_dream.py): how far it got
memory_dreams = Table(
    'memory_dreams',
    metadata,
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('vault', Integer, primary_key=True),  # As kb_notes.vault
    Column('dreamed_until', BigInteger),  # The end of the last period it consolidated (ms, like message ids)
    Column('failed_at', DateTime),  # The last run that failed (naive UTC), NULL after a success
    Column('updated_at', DateTime, server_default=func.now(), onupdate=func.now()),
)

# MCP servers (docs/mcp.md): the admins' servers, which agents pick (user_id NULL), and users' own
mcp_servers = Table(
    'mcp_servers',
    metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE')),  # NULL: an admin server
    Column('slug', Text, nullable=False),  # Prefix of its tool names, unique per owner, fixed
    Column('name', Text, nullable=False),
    Column('description', Text),
    Column('transport', Text, nullable=False, server_default='http'),  # 'http' | 'sse' | 'stdio'
    Column('url', Text),
    Column('command', Text),
    Column('args', JSONB),
    Column('env', JSONB),
    Column('auth', Text, nullable=False, server_default='none'),  # 'none' | 'headers' | 'oauth'
    Column('headers', JSONB),  # Admin servers, values may use ${VAR}
    Column('headers_encrypted', Text),  # Users' servers
    Column('oauth_client_id', Text),
    Column('oauth_client_secret_env', Text),
    Column('oauth_scopes', Text),
    Column('oauth_client_encrypted', Text),  # The client from dynamic client registration
    Column('tools', JSONB),  # MCP tool names offered to the model, NULL = all
    Column('available_to_guests', Boolean, server_default='false'),
    Column('enabled', Boolean, server_default='true'),
    Column('sort_order', Integer, server_default='0'),
    Column('created_at', DateTime, server_default=func.now()),
    Column('updated_at', DateTime, server_default=func.now(), onupdate=func.now()),
)

# A user's OAuth sign-in to an MCP server (encrypted)
mcp_tokens = Table(
    'mcp_tokens',
    metadata,
    Column('server_id', Integer, ForeignKey('mcp_servers.id', ondelete='CASCADE'), primary_key=True),
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('tokens_encrypted', Text, nullable=False),
    Column('expires_at', DateTime),  # Naive UTC
    Column('created_at', DateTime, server_default=func.now()),
    Column('updated_at', DateTime, server_default=func.now(), onupdate=func.now()),
)

# OAuth sign-ins to MCP servers in progress
mcp_oauth_flows = Table(
    'mcp_oauth_flows',
    metadata,
    Column('state', Text, primary_key=True),
    Column('server_id', Integer, ForeignKey('mcp_servers.id', ondelete='CASCADE'), nullable=False),
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
    Column('flow_encrypted', Text, nullable=False),
    Column('created_at', DateTime, server_default=func.now()),
)

# Confirmations of an MCP server a user accepts without being asked (elicitation): in one
# conversation, or in every one (conversation_id NULL)
mcp_auto_accept = Table(
    'mcp_auto_accept',
    metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('server_id', Integer, ForeignKey('mcp_servers.id', ondelete='CASCADE'), nullable=False),
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
    Column('conversation_id', Text, ForeignKey('conversations.id', ondelete='CASCADE')),
    Column('created_at', DateTime, server_default=func.now()),
)

# Define indexes
idx_conversation_time = Index('idx_conversation_time', messages.c.conversationId, messages.c.time)
idx_message_tool_records_conversation = Index(
    'idx_message_tool_records_conversation', message_tool_records.c.conversation_id)
idx_conversations_user = Index('idx_conversations_user', conversations.c.userId)
idx_sessions_expires = Index('idx_sessions_expires', sessions.c.expires_at)
idx_sessions_user = Index('idx_sessions_user', sessions.c.user_id)
# Partial index for agent messages - only index rows where type='agent'
idx_messages_agent_status = Index(
    'idx_messages_agent_status',
    messages.c.agent_status,
    postgresql_where=(messages.c.type == 'agent')
)
# Index for file description cache - enables efficient deletion by file_id
idx_cache_file_id = Index('idx_cache_file_id', file_description_cache.c.file_id)
idx_uploaded_files_user = Index('idx_uploaded_files_user', uploaded_files.c.user_id)
idx_uploaded_files_conversation = Index('idx_uploaded_files_conversation', uploaded_files.c.conversation_id)
idx_llm_models_provider = Index('idx_llm_models_provider', llm_models.c.provider_id)
idx_kb_notes_user_updated = Index('idx_kb_notes_user_updated', kb_notes.c.user_id, kb_notes.c.updated_at.desc())
idx_kb_note_revisions_note = Index('idx_kb_note_revisions_note', kb_note_revisions.c.note_id)
idx_kb_links_target = Index('idx_kb_links_target', kb_links.c.target_slug)
