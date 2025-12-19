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
    DateTime,
    ForeignKey,
    Index,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

# Create metadata instance
metadata = MetaData()

# Users table
users = Table(
    'users',
    metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('email', Text, unique=True, nullable=False),
    Column('name', Text),
    Column('created_at', DateTime, server_default=func.now()),
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
    Column('version', Integer, server_default='1'),
    Column('lastModified', BigInteger),
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
    Column('agent_status', Text),  # thinking, responding, complete, error
    Column('agent_steps', JSONB),  # Array of reasoning steps
    Column('final_response', Text),  # Final response text
    Column('agent_error', Text),  # Error message if status is 'error'
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

# Define indexes
idx_conversation_time = Index('idx_conversation_time', messages.c.conversationId, messages.c.time)
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
