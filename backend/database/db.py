"""
PostgreSQL Database Manager.

This module provides a Database class for managing PostgreSQL connections and
performing CRUD operations on all database entities. It uses SQLAlchemy Core
for simple operations and loads complex queries from external .sql files.

Example usage:
    from backend.database import db

    # Get a user
    user = db.get_user_by_email("user@example.com")

    # Create a message
    message = db.create_message(
        message_id=1234567890,
        conversation_id="conv-uuid",
        role_name="user",
        content="Hello!",
        time=1234567890
    )
"""
import logging
import os
import re
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional, Generator

from sqlalchemy import create_engine, text, select, insert, update, delete
from sqlalchemy.engine import Engine, Connection
from sqlalchemy.pool import QueuePool

from backend.config import (
    POSTGRES_HOST,
    POSTGRES_PORT,
    POSTGRES_DB,
    POSTGRES_USER,
    POSTGRES_PASSWORD,
    POSTGRES_MIN_CONNECTIONS,
    POSTGRES_MAX_CONNECTIONS,
    DATABASE_URL,
)
from backend.database.tables import (
    metadata,
    users,
    conversations,
    messages,
    sessions,
    guest_usage,
    user_settings,
    file_description_cache,
)

log = logging.getLogger(__name__)

# Path to SQL query files
QUERIES_DIR = Path(__file__).parent / "queries"


class Database:
    """
    PostgreSQL database manager with connection pooling and CRUD operations.

    This class provides a clean interface for database operations using SQLAlchemy
    Core for simple CRUD and external .sql files for complex queries. Connection
    pooling is handled automatically via SQLAlchemy's engine.

    Attributes:
        engine: SQLAlchemy engine with connection pooling.
        _queries: Cache of loaded SQL queries from .sql files.

    Example:
        db = Database()
        db.init_tables()
        user = db.create_user("user@example.com", "John Doe")
    """

    def __init__(
        self,
        host: str = None,
        port: int = None,
        database: str = None,
        user: str = None,
        password: str = None,
        min_connections: int = None,
        max_connections: int = None,
        database_url: str = None,
    ):
        """
        Initialize the database connection pool.

        Args:
            host: PostgreSQL host (default from config).
            port: PostgreSQL port (default from config).
            database: Database name (default from config).
            user: Database user (default from config).
            password: Database password (default from config).
            min_connections: Minimum pool size (default from config).
            max_connections: Maximum pool size (default from config).
            database_url: Full connection URL (overrides individual settings).
        """
        # Use provided values or fall back to config
        self._host = host or POSTGRES_HOST
        self._port = port or POSTGRES_PORT
        self._database = database or POSTGRES_DB
        self._user = user or POSTGRES_USER
        self._password = password or POSTGRES_PASSWORD
        self._min_connections = min_connections or POSTGRES_MIN_CONNECTIONS
        self._max_connections = max_connections or POSTGRES_MAX_CONNECTIONS

        # Build connection URL
        if database_url or DATABASE_URL:
            url = database_url or DATABASE_URL
        else:
            url = f"postgresql://{self._user}:{self._password}@{self._host}:{self._port}/{self._database}"

        log.debug(f"Initializing database connection to {self._host}:{self._port}/{self._database}")

        # Create engine with connection pooling
        self.engine: Engine = create_engine(
            url,
            poolclass=QueuePool,
            pool_size=self._min_connections,
            max_overflow=self._max_connections - self._min_connections,
            pool_pre_ping=True,  # Verify connections before use
            echo=False,  # Set to True for SQL debugging
        )

        # Cache for loaded queries
        self._queries: dict[str, str] = {}

        log.info("Database connection pool initialized")

    @contextmanager
    def connection(self) -> Generator[Connection, None, None]:
        """
        Context manager for database connections.

        Yields a connection from the pool that is automatically returned
        when the context exits. Transactions are automatically committed
        on success or rolled back on exception.

        Yields:
            SQLAlchemy Connection object.

        Example:
            with db.connection() as conn:
                result = conn.execute(select(users))
        """
        conn = self.engine.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def close_all(self) -> None:
        """
        Close all connections in the pool.

        Should be called when shutting down the application.
        """
        self.engine.dispose()
        log.info("Database connection pool closed")

    def _load_query(self, filename: str, query_name: str) -> str:
        """
        Load a named query from a .sql file.

        SQL files use '-- name: query_name' comments to separate queries.

        Args:
            filename: Name of the .sql file (e.g., 'complex.sql').
            query_name: Name of the query to load.

        Returns:
            The SQL query string.

        Raises:
            ValueError: If the query is not found.
        """
        cache_key = f"{filename}:{query_name}"
        if cache_key in self._queries:
            return self._queries[cache_key]

        file_path = QUERIES_DIR / filename
        if not file_path.exists():
            raise ValueError(f"Query file not found: {file_path}")

        content = file_path.read_text()

        # Parse named queries using regex
        pattern = r"--\s*name:\s*(\w+)\s*\n(.*?)(?=--\s*name:|\Z)"
        matches = re.findall(pattern, content, re.DOTALL)

        for name, sql in matches:
            self._queries[f"{filename}:{name}"] = sql.strip()

        if cache_key not in self._queries:
            raise ValueError(f"Query '{query_name}' not found in {filename}")

        return self._queries[cache_key]

    def _row_to_dict(self, row) -> Optional[dict]:
        """
        Convert a SQLAlchemy row to a dictionary.

        Args:
            row: SQLAlchemy Row object or None.

        Returns:
            Dictionary with column names as keys, or None if row is None.
        """
        if row is None:
            return None
        return dict(row._mapping)

    def init_tables(self) -> None:
        """
        Create all database tables if they don't exist.

        This method reads the schema.sql file and executes all DDL statements
        to create tables, indexes, and triggers.
        """
        log.info("Initializing database tables...")

        schema_file = QUERIES_DIR / "schema.sql"
        if not schema_file.exists():
            raise ValueError(f"Schema file not found: {schema_file}")

        # Read and execute schema SQL
        schema_sql = schema_file.read_text()

        # Split by -- name: comments and execute each block
        pattern = r"--\s*name:\s*\w+\s*\n"
        blocks = re.split(pattern, schema_sql)

        with self.connection() as conn:
            for block in blocks:
                block = block.strip()
                if block:
                    # Execute each statement in the block
                    statements = [s.strip() for s in block.split(';') if s.strip()]
                    for stmt in statements:
                        try:
                            conn.execute(text(stmt))
                        except Exception as e:
                            log.warning(f"Statement warning (may be expected): {e}")

        log.info("Database tables initialized successfully")

    # =========================================================================
    # User CRUD Operations
    # =========================================================================

    def get_user_by_id(self, user_id: int) -> Optional[dict]:
        """
        Get a user by their ID.

        Args:
            user_id: The user's ID.

        Returns:
            User dictionary or None if not found.
        """
        log.debug(f"Getting user by id: {user_id}")
        with self.connection() as conn:
            stmt = select(users).where(users.c.id == user_id)
            result = conn.execute(stmt).fetchone()
            user = self._row_to_dict(result)
            if user:
                log.debug(f"Found user: {user.get('email')}")
            else:
                log.debug(f"User not found: {user_id}")
            return user

    def get_user_by_email(self, email: str) -> Optional[dict]:
        """
        Get a user by their email address (case-insensitive).

        Args:
            email: The user's email address.

        Returns:
            User dictionary or None if not found.
        """
        log.debug(f"Getting user by email: {email}")
        with self.connection() as conn:
            stmt = select(users).where(users.c.email.ilike(email))
            result = conn.execute(stmt).fetchone()
            user = self._row_to_dict(result)
            if user:
                log.debug(f"Found user id: {user.get('id')}")
            else:
                log.debug(f"User not found: {email}")
            return user

    def create_user(self, email: str, name: str = None) -> dict:
        """
        Create a new user.

        Args:
            email: The user's email address.
            name: The user's name (optional).

        Returns:
            The created user dictionary.
        """
        with self.connection() as conn:
            stmt = insert(users).values(email=email, name=name).returning(users)
            result = conn.execute(stmt).fetchone()
            log.info(f"Created user: {email}")
            return self._row_to_dict(result)

    def update_user(self, user_id: int, name: str = None, email: str = None) -> Optional[dict]:
        """
        Update a user's information.

        Args:
            user_id: The user's ID.
            name: New name (optional).
            email: New email (optional).

        Returns:
            Updated user dictionary or None if not found.
        """
        log.debug(f"Updating user {user_id}: name={name}, email={email}")
        values = {}
        if name is not None:
            values['name'] = name
        if email is not None:
            values['email'] = email

        if not values:
            log.debug("No values to update")
            return self.get_user_by_id(user_id)

        with self.connection() as conn:
            stmt = update(users).where(users.c.id == user_id).values(**values).returning(users)
            result = conn.execute(stmt).fetchone()
            if result:
                log.info(f"Updated user: {user_id}")
            return self._row_to_dict(result)

    def delete_user(self, user_id: int) -> bool:
        """
        Delete a user.

        Args:
            user_id: The user's ID.

        Returns:
            True if deleted, False if not found.
        """
        log.debug(f"Deleting user: {user_id}")
        with self.connection() as conn:
            stmt = delete(users).where(users.c.id == user_id)
            result = conn.execute(stmt)
            deleted = result.rowcount > 0
            if deleted:
                log.info(f"Deleted user: {user_id}")
            else:
                log.debug(f"User not found for deletion: {user_id}")
            return deleted

    # =========================================================================
    # Conversation CRUD Operations
    # =========================================================================

    def get_conversation_by_id(
        self,
        conversation_id: str,
        user_id: int = None,
        include_message_count: bool = False
    ) -> Optional[dict]:
        """
        Get a conversation by its ID.

        Args:
            conversation_id: The conversation's UUID.
            user_id: Optional user ID for ownership check (None allows any).
            include_message_count: If True, include message count in result.

        Returns:
            Conversation dictionary or None if not found.
        """
        log.debug(f"Getting conversation: {conversation_id}, user_id: {user_id}")
        with self.connection() as conn:
            if include_message_count:
                if user_id is not None:
                    query = self._load_query("complex.sql", "get_conversation_with_message_count")
                    result = conn.execute(
                        text(query),
                        {"conversation_id": conversation_id, "user_id": user_id}
                    ).fetchone()
                else:
                    query = self._load_query("complex.sql", "get_conversation_with_message_count_guest")
                    result = conn.execute(
                        text(query),
                        {"conversation_id": conversation_id}
                    ).fetchone()
            else:
                stmt = select(conversations).where(conversations.c.id == conversation_id)
                if user_id is not None:
                    stmt = stmt.where(conversations.c.userId == user_id)
                result = conn.execute(stmt).fetchone()

            conv = self._row_to_dict(result)
            if conv:
                log.debug(f"Found conversation: {conversation_id}")
            else:
                log.debug(f"Conversation not found: {conversation_id}")
            return conv

    def get_conversations_by_user(self, user_id: int) -> list[dict]:
        """
        Get all conversations for a user.

        Args:
            user_id: The user's ID.

        Returns:
            List of conversation dictionaries.
        """
        log.debug(f"Getting conversations for user: {user_id}")
        with self.connection() as conn:
            stmt = (
                select(conversations)
                .where(conversations.c.userId == user_id)
                .order_by(conversations.c.updatedAt.desc())
            )
            results = conn.execute(stmt).fetchall()
            conv_list = [self._row_to_dict(row) for row in results]
            log.debug(f"Found {len(conv_list)} conversations for user {user_id}")
            return conv_list

    def create_conversation(
        self,
        conversation_id: str,
        user_id: int,
        name: str,
        participants: str = None,
        last_modified: int = None
    ) -> dict:
        """
        Create a new conversation.

        Args:
            conversation_id: UUID for the conversation.
            user_id: Owner's user ID.
            name: Conversation name.
            participants: JSON-encoded participant list (optional).
            last_modified: Unix timestamp (optional).

        Returns:
            The created conversation dictionary.
        """
        with self.connection() as conn:
            stmt = insert(conversations).values(
                id=conversation_id,
                userId=user_id,
                name=name,
                participants=participants,
                lastModified=last_modified,
            ).returning(conversations)
            result = conn.execute(stmt).fetchone()
            log.info(f"Created conversation: {conversation_id}")
            return self._row_to_dict(result)

    def update_conversation(
        self,
        conversation_id: str,
        user_id: int = None,
        name: str = None,
        version: int = None,
        last_modified: int = None
    ) -> Optional[dict]:
        """
        Update a conversation.

        Args:
            conversation_id: The conversation's UUID.
            user_id: Optional user ID for ownership check.
            name: New name (optional).
            version: New version for optimistic locking (optional).
            last_modified: Unix timestamp (optional).

        Returns:
            Updated conversation dictionary or None if not found.
        """
        log.debug(f"Updating conversation {conversation_id}: name={name}, version={version}")
        values = {}
        if name is not None:
            values['name'] = name
        if version is not None:
            values['version'] = version
        if last_modified is not None:
            values['lastModified'] = last_modified

        if not values:
            log.debug("No values to update")
            return self.get_conversation_by_id(conversation_id, user_id)

        with self.connection() as conn:
            stmt = update(conversations).where(conversations.c.id == conversation_id)
            if user_id is not None:
                stmt = stmt.where(conversations.c.userId == user_id)
            stmt = stmt.values(**values).returning(conversations)
            result = conn.execute(stmt).fetchone()
            if result:
                log.info(f"Updated conversation: {conversation_id}")
            return self._row_to_dict(result)

    def delete_conversation(self, conversation_id: str, user_id: int = None) -> bool:
        """
        Delete a conversation and all its messages.

        Messages are automatically deleted via ON DELETE CASCADE.

        Args:
            conversation_id: The conversation's UUID.
            user_id: Optional user ID for ownership check.

        Returns:
            True if deleted, False if not found.
        """
        with self.connection() as conn:
            stmt = delete(conversations).where(conversations.c.id == conversation_id)
            if user_id is not None:
                stmt = stmt.where(conversations.c.userId == user_id)
            result = conn.execute(stmt)
            if result.rowcount > 0:
                log.info(f"Deleted conversation: {conversation_id}")
            return result.rowcount > 0

    def get_conversation_owner(self, conversation_id: str) -> Optional[int]:
        """
        Get the owner's user ID for a conversation.

        Args:
            conversation_id: The conversation's UUID.

        Returns:
            User ID or None if conversation not found.
        """
        log.debug(f"Getting owner for conversation: {conversation_id}")
        with self.connection() as conn:
            stmt = select(conversations.c.userId).where(conversations.c.id == conversation_id)
            result = conn.execute(stmt).fetchone()
            owner_id = result[0] if result else None
            log.debug(f"Conversation {conversation_id} owner: {owner_id}")
            return owner_id

    # =========================================================================
    # Message CRUD Operations
    # =========================================================================

    def get_message_by_id(self, message_id: int, conversation_id: str) -> Optional[dict]:
        """
        Get a message by its ID.

        Args:
            message_id: The message's ID.
            conversation_id: The conversation's UUID.

        Returns:
            Message dictionary or None if not found.
        """
        log.debug(f"Getting message: {message_id} from conversation {conversation_id}")
        with self.connection() as conn:
            stmt = select(messages).where(
                (messages.c.id == message_id) &
                (messages.c.conversationId == conversation_id)
            )
            result = conn.execute(stmt).fetchone()
            msg = self._row_to_dict(result)
            if msg:
                log.debug(f"Found message: {message_id}")
            else:
                log.debug(f"Message not found: {message_id}")
            return msg

    def get_messages_by_conversation(
        self,
        conversation_id: str,
        before_timestamp: int = None,
        after_timestamp: int = None,
        limit: int = 30
    ) -> list[dict]:
        """
        Get messages from a conversation.

        Args:
            conversation_id: The conversation's UUID.
            before_timestamp: Get messages before this timestamp (pagination).
            after_timestamp: Get messages after this timestamp (incremental sync).
            limit: Maximum number of messages to return.

        Returns:
            List of message dictionaries.
        """
        log.debug(f"Getting messages for {conversation_id}: before={before_timestamp}, after={after_timestamp}, limit={limit}")
        with self.connection() as conn:
            if before_timestamp is not None:
                query = self._load_query("complex.sql", "get_messages_before_timestamp")
                results = conn.execute(
                    text(query),
                    {"conversation_id": conversation_id, "before_timestamp": before_timestamp, "limit": limit}
                ).fetchall()
            elif after_timestamp is not None:
                query = self._load_query("complex.sql", "get_messages_after_timestamp")
                results = conn.execute(
                    text(query),
                    {"conversation_id": conversation_id, "after_timestamp": after_timestamp}
                ).fetchall()
            else:
                stmt = (
                    select(messages)
                    .where(messages.c.conversationId == conversation_id)
                    .order_by(messages.c.time.desc())
                    .limit(limit)
                )
                results = conn.execute(stmt).fetchall()

            msg_list = [self._row_to_dict(row) for row in results]
            log.debug(f"Retrieved {len(msg_list)} messages for conversation {conversation_id}")
            return msg_list

    def get_message_count(self, conversation_id: str) -> int:
        """
        Get the number of messages in a conversation.

        Args:
            conversation_id: The conversation's UUID.

        Returns:
            Number of messages.
        """
        from sqlalchemy import func
        log.debug(f"Getting message count for conversation: {conversation_id}")
        with self.connection() as conn:
            stmt = select(func.count(messages.c.id)).where(
                messages.c.conversationId == conversation_id
            )
            result = conn.execute(stmt).scalar()
            count = result or 0
            log.debug(f"Message count for {conversation_id}: {count}")
            return count

    def create_message(
        self,
        message_id: int,
        conversation_id: str,
        role_name: str,
        content: str,
        time: int,
        msg_type: str = 'text',
        version: int = 1,
        last_modified: int = None
    ) -> dict:
        """
        Create a new message.

        Args:
            message_id: The message's ID (usually timestamp-based).
            conversation_id: The conversation's UUID.
            role_name: Message sender role ('user', 'assistant', etc.).
            content: Message content (text or JSON for complex types).
            time: Unix timestamp when sent.
            msg_type: Message type ('text' or 'voice').
            version: Version for optimistic locking.
            last_modified: Unix timestamp (optional).

        Returns:
            The created message dictionary.
        """
        with self.connection() as conn:
            stmt = insert(messages).values(
                id=message_id,
                conversationId=conversation_id,
                roleName=role_name,
                content=content,
                time=time,
                type=msg_type,
                version=version,
                lastModified=last_modified,
            ).returning(messages)
            result = conn.execute(stmt).fetchone()
            log.debug(f"Created message: {message_id} in conversation {conversation_id}")
            return self._row_to_dict(result)

    def update_message(
        self,
        message_id: int,
        conversation_id: str,
        content: str,
        version: int,
        last_modified: int = None
    ) -> Optional[dict]:
        """
        Update a message's content with optimistic locking.

        Args:
            message_id: The message's ID.
            conversation_id: The conversation's UUID.
            content: New message content.
            version: Expected current version (for optimistic locking).
            last_modified: Unix timestamp (optional).

        Returns:
            Updated message dictionary or None if version mismatch/not found.
        """
        log.debug(f"Updating message {message_id}: version={version}")
        with self.connection() as conn:
            values = {
                'content': content,
                'version': version + 1,
            }
            if last_modified is not None:
                values['lastModified'] = last_modified

            stmt = (
                update(messages)
                .where(
                    (messages.c.id == message_id) &
                    (messages.c.conversationId == conversation_id) &
                    (messages.c.version == version)
                )
                .values(**values)
                .returning(messages)
            )
            result = conn.execute(stmt).fetchone()
            if result:
                log.debug(f"Updated message: {message_id}")
            else:
                log.warning(f"Message update failed (version mismatch or not found): {message_id}")
            return self._row_to_dict(result)

    def update_message_rating(
        self,
        message_id: int,
        conversation_id: str,
        rating: Optional[int]
    ) -> Optional[dict]:
        """
        Update a message's rating.

        Args:
            message_id: The message's ID.
            conversation_id: The conversation's UUID.
            rating: Rating value (0, 1, or None to clear).

        Returns:
            Updated message dictionary or None if not found.
        """
        log.debug(f"Updating message rating: {message_id}, rating={rating}")
        with self.connection() as conn:
            stmt = (
                update(messages)
                .where(
                    (messages.c.id == message_id) &
                    (messages.c.conversationId == conversation_id)
                )
                .values(rating=rating)
                .returning(messages)
            )
            result = conn.execute(stmt).fetchone()
            if result:
                log.info(f"Updated message rating: {message_id} -> {rating}")
            return self._row_to_dict(result)

    def delete_message(self, message_id: int, conversation_id: str) -> bool:
        """
        Delete a message.

        Args:
            message_id: The message's ID.
            conversation_id: The conversation's UUID.

        Returns:
            True if deleted, False if not found.
        """
        log.debug(f"Deleting message: {message_id}")
        with self.connection() as conn:
            stmt = delete(messages).where(
                (messages.c.id == message_id) &
                (messages.c.conversationId == conversation_id)
            )
            result = conn.execute(stmt)
            deleted = result.rowcount > 0
            if deleted:
                log.info(f"Deleted message: {message_id}")
            else:
                log.debug(f"Message not found for deletion: {message_id}")
            return deleted

    def delete_messages_by_conversation(self, conversation_id: str) -> int:
        """
        Delete all messages in a conversation.

        Args:
            conversation_id: The conversation's UUID.

        Returns:
            Number of messages deleted.
        """
        log.debug(f"Deleting all messages for conversation: {conversation_id}")
        with self.connection() as conn:
            stmt = delete(messages).where(messages.c.conversationId == conversation_id)
            result = conn.execute(stmt)
            count = result.rowcount
            if count > 0:
                log.info(f"Deleted {count} messages from conversation {conversation_id}")
            return count

    def get_message_version(self, message_id: int, conversation_id: str) -> Optional[int]:
        """
        Get the current version of a message.

        Args:
            message_id: The message's ID.
            conversation_id: The conversation's UUID.

        Returns:
            Version number or None if not found.
        """
        log.debug(f"Getting version for message: {message_id}")
        with self.connection() as conn:
            stmt = select(messages.c.version).where(
                (messages.c.id == message_id) &
                (messages.c.conversationId == conversation_id)
            )
            result = conn.execute(stmt).fetchone()
            version = result[0] if result else None
            log.debug(f"Message {message_id} version: {version}")
            return version

    def get_recent_messages_for_context(
        self,
        conversation_id: str,
        limit: int = 20
    ) -> list[dict]:
        """
        Get recent messages for LLM context building.

        Args:
            conversation_id: The conversation's UUID.
            limit: Maximum number of messages.

        Returns:
            List of message dictionaries (id, roleName, content, time, type).
        """
        log.debug(f"Getting recent messages for context: {conversation_id}, limit={limit}")
        with self.connection() as conn:
            query = self._load_query("complex.sql", "get_recent_messages_for_context")
            results = conn.execute(
                text(query),
                {"conversation_id": conversation_id, "limit": limit}
            ).fetchall()
            msg_list = [self._row_to_dict(row) for row in results]
            log.debug(f"Retrieved {len(msg_list)} messages for LLM context")
            return msg_list

    # =========================================================================
    # Agent Message Operations
    # =========================================================================

    def create_agent_message(
        self,
        message_id: int,
        conversation_id: str,
        role_name: str,
        time: int,
        final_response: str,
        status: str = 'complete',
        error: str = None,
        steps: list = None
    ) -> dict:
        """
        Create an agent message with steps stored as JSONB.

        Args:
            message_id: The message's ID (usually timestamp-based).
            conversation_id: The conversation's UUID.
            role_name: Message sender role (e.g., 'Assistant').
            time: Unix timestamp when created.
            final_response: The final response text.
            status: Agent status ('thinking', 'responding', 'complete', 'error').
            error: Error message if status is 'error'.
            steps: List of AgentStep dictionaries.

        Returns:
            The created message dictionary.
        """
        import json as json_module
        with self.connection() as conn:
            stmt = insert(messages).values(
                id=message_id,
                conversationId=conversation_id,
                roleName=role_name,
                content='',  # Empty for agent messages using new schema
                time=time,
                type='agent',
                version=1,
                lastModified=time,
                agent_status=status,
                agent_steps=steps,  # Stored directly as JSONB
                final_response=final_response,
                agent_error=error
            ).returning(messages)
            result = conn.execute(stmt).fetchone()
            log.debug(f"Created agent message: {message_id} in conversation {conversation_id}")
            return self._row_to_dict(result)

    def update_agent_message(
        self,
        message_id: int,
        conversation_id: str,
        final_response: str = None,
        status: str = None,
        error: str = None,
        steps: list = None
    ) -> Optional[dict]:
        """
        Update an existing agent message.

        Args:
            message_id: The message's ID.
            conversation_id: The conversation's UUID.
            final_response: New final response text (optional).
            status: New status (optional).
            error: New error message (optional).
            steps: New steps list (optional).

        Returns:
            Updated message dictionary or None if not found.
        """
        log.debug(f"Updating agent message {message_id}: status={status}")
        import time as time_module
        values = {"lastModified": int(time_module.time())}
        if final_response is not None:
            values["final_response"] = final_response
        if status is not None:
            values["agent_status"] = status
        if error is not None:
            values["agent_error"] = error
        if steps is not None:
            values["agent_steps"] = steps

        with self.connection() as conn:
            stmt = (
                update(messages)
                .where(
                    (messages.c.id == message_id) &
                    (messages.c.conversationId == conversation_id)
                )
                .values(**values)
                .returning(messages)
            )
            result = conn.execute(stmt).fetchone()
            if result:
                log.debug(f"Updated agent message: {message_id}")
            return self._row_to_dict(result)

    # =========================================================================
    # Session CRUD Operations
    # =========================================================================

    def get_session(self, session_key: str) -> Optional[dict]:
        """
        Get a session by its key.

        Args:
            session_key: The session key.

        Returns:
            Session dictionary or None if not found/expired.
        """
        log.debug(f"Getting session: {session_key[:8]}...")
        with self.connection() as conn:
            stmt = select(sessions).where(
                (sessions.c.session_key == session_key) &
                (sessions.c.expires_at > datetime.utcnow())
            )
            result = conn.execute(stmt).fetchone()
            session = self._row_to_dict(result)
            if session:
                log.debug(f"Found valid session for user {session.get('user_id')}")
            else:
                log.debug("Session not found or expired")
            return session

    def create_session(
        self,
        session_key: str,
        user_id: int,
        email: str,
        expires_at: datetime,
        is_guest: bool = False,
        csrf_token: str = None
    ) -> dict:
        """
        Create a new session.

        Args:
            session_key: Unique session key.
            user_id: User ID for the session.
            email: User's email.
            expires_at: Session expiration datetime.
            is_guest: Whether this is a guest session.
            csrf_token: CSRF token (optional).

        Returns:
            The created session dictionary.
        """
        with self.connection() as conn:
            stmt = insert(sessions).values(
                session_key=session_key,
                user_id=user_id,
                email=email,
                expires_at=expires_at,
                is_guest=is_guest,
                csrf_token=csrf_token,
            ).returning(sessions)
            result = conn.execute(stmt).fetchone()
            log.debug(f"Created session for user {user_id}")
            return self._row_to_dict(result)

    def update_session_activity(self, session_key: str) -> bool:
        """
        Update a session's last activity timestamp.

        Args:
            session_key: The session key.

        Returns:
            True if updated, False if not found.
        """
        log.debug(f"Updating session activity: {session_key[:8]}...")
        with self.connection() as conn:
            stmt = (
                update(sessions)
                .where(sessions.c.session_key == session_key)
                .values(last_activity=datetime.utcnow())
            )
            result = conn.execute(stmt)
            updated = result.rowcount > 0
            if not updated:
                log.debug("Session not found for activity update")
            return updated

    def delete_session(self, session_key: str) -> bool:
        """
        Delete a session.

        Args:
            session_key: The session key.

        Returns:
            True if deleted, False if not found.
        """
        log.debug(f"Deleting session: {session_key[:8]}...")
        with self.connection() as conn:
            stmt = delete(sessions).where(sessions.c.session_key == session_key)
            result = conn.execute(stmt)
            deleted = result.rowcount > 0
            if deleted:
                log.debug("Session deleted")
            else:
                log.debug("Session not found for deletion")
            return deleted

    def delete_expired_sessions(self) -> int:
        """
        Delete all expired sessions.

        Returns:
            Number of sessions deleted.
        """
        with self.connection() as conn:
            stmt = delete(sessions).where(sessions.c.expires_at < datetime.utcnow())
            result = conn.execute(stmt)
            count = result.rowcount
            if count > 0:
                log.info(f"Cleaned up {count} expired sessions")
            return count

    def delete_sessions_by_user(self, user_id: int) -> int:
        """
        Delete all sessions for a user.

        Args:
            user_id: The user's ID.

        Returns:
            Number of sessions deleted.
        """
        log.debug(f"Deleting all sessions for user: {user_id}")
        with self.connection() as conn:
            stmt = delete(sessions).where(sessions.c.user_id == user_id)
            result = conn.execute(stmt)
            count = result.rowcount
            if count > 0:
                log.info(f"Deleted {count} sessions for user {user_id}")
            return count

    # =========================================================================
    # Guest Usage CRUD Operations
    # =========================================================================

    def get_guest_usage(self, ip_address: str) -> Optional[dict]:
        """
        Get guest usage record for an IP address.

        Args:
            ip_address: The IP address.

        Returns:
            Guest usage dictionary or None if not found.
        """
        log.debug(f"Getting guest usage for IP: {ip_address}")
        with self.connection() as conn:
            stmt = select(guest_usage).where(guest_usage.c.ip_address == ip_address)
            result = conn.execute(stmt).fetchone()
            usage = self._row_to_dict(result)
            if usage:
                log.debug(f"Guest usage: count={usage.get('request_count')}")
            return usage

    def create_or_update_guest_usage(
        self,
        ip_address: str,
        request_count: int,
        last_request_at: datetime
    ) -> dict:
        """
        Create or update guest usage record (upsert).

        Args:
            ip_address: The IP address.
            request_count: Number of requests.
            last_request_at: Timestamp of last request.

        Returns:
            The guest usage dictionary.
        """
        with self.connection() as conn:
            # Try to update first
            stmt = (
                update(guest_usage)
                .where(guest_usage.c.ip_address == ip_address)
                .values(request_count=request_count, last_request_at=last_request_at)
                .returning(guest_usage)
            )
            result = conn.execute(stmt).fetchone()

            if result is None:
                # Insert if not exists
                stmt = insert(guest_usage).values(
                    ip_address=ip_address,
                    request_count=request_count,
                    last_request_at=last_request_at,
                ).returning(guest_usage)
                result = conn.execute(stmt).fetchone()

            return self._row_to_dict(result)

    def increment_guest_usage(self, ip_address: str) -> dict:
        """
        Increment the request count for a guest IP.

        Creates a new record if it doesn't exist.

        Args:
            ip_address: The IP address.

        Returns:
            Updated guest usage dictionary.
        """
        log.debug(f"Incrementing guest usage for IP: {ip_address}")
        now = datetime.utcnow()
        current = self.get_guest_usage(ip_address)

        if current is None:
            log.debug(f"Creating new guest usage record for {ip_address}")
            return self.create_or_update_guest_usage(ip_address, 1, now)

        new_count = current['request_count'] + 1
        log.debug(f"Incrementing guest usage to {new_count} for {ip_address}")
        return self.create_or_update_guest_usage(
            ip_address,
            new_count,
            now
        )

    def reset_guest_usage(self, ip_address: str) -> dict:
        """
        Reset the request count for a guest IP.

        Args:
            ip_address: The IP address.

        Returns:
            Updated guest usage dictionary.
        """
        log.debug(f"Resetting guest usage for IP: {ip_address}")
        return self.create_or_update_guest_usage(ip_address, 0, datetime.utcnow())

    # =========================================================================
    # User Settings CRUD Operations
    # =========================================================================

    def get_user_settings(self, user_id: int) -> Optional[dict]:
        """
        Get user settings.

        Args:
            user_id: The user's ID.

        Returns:
            User settings dictionary or None if not found.
        """
        log.debug(f"Getting settings for user: {user_id}")
        with self.connection() as conn:
            stmt = select(user_settings).where(user_settings.c.user_id == user_id)
            result = conn.execute(stmt).fetchone()
            settings = self._row_to_dict(result)
            if settings:
                log.debug(f"Found settings: theme={settings.get('theme')}, language={settings.get('language')}")
            else:
                log.debug(f"No settings found for user {user_id}")
            return settings

    def upsert_user_settings(self, user_id: int, theme: str, language: str) -> dict:
        """
        Create or update user settings.

        Args:
            user_id: The user's ID.
            theme: Theme setting ('auto', 'dark', 'light').
            language: Language setting ('en', 'de', etc.).

        Returns:
            The user settings dictionary.
        """
        log.debug(f"Upserting settings for user {user_id}: theme={theme}, language={language}")
        with self.connection() as conn:
            # Try to update first
            stmt = (
                update(user_settings)
                .where(user_settings.c.user_id == user_id)
                .values(theme=theme, language=language)
                .returning(user_settings)
            )
            result = conn.execute(stmt).fetchone()

            if result is None:
                # Insert if not exists
                log.debug(f"Creating new settings for user {user_id}")
                stmt = insert(user_settings).values(
                    user_id=user_id,
                    theme=theme,
                    language=language,
                ).returning(user_settings)
                result = conn.execute(stmt).fetchone()
                log.info(f"Created settings for user {user_id}")
            else:
                log.debug(f"Updated settings for user {user_id}")

            return self._row_to_dict(result)

    # ==================== File Description Cache ====================

    def get_cache_entry(self, cache_key: str) -> Optional[str]:
        """
        Get a cached file description.

        Args:
            cache_key: The cache key (SHA256 of file_id + query).

        Returns:
            The cached description or None if not found.
        """
        log.debug(f"Getting cache entry: {cache_key[:16]}...")
        with self.connection() as conn:
            stmt = select(file_description_cache.c.description).where(
                file_description_cache.c.cache_key == cache_key
            )
            result = conn.execute(stmt).fetchone()
            if result:
                log.debug("Cache hit")
            else:
                log.debug("Cache miss")
            return result[0] if result else None

    def set_cache_entry(
        self,
        cache_key: str,
        file_id: str,
        description: str,
        query: Optional[str] = None
    ) -> None:
        """
        Store a file description in the cache.

        Args:
            cache_key: The cache key (SHA256 of file_id + query).
            file_id: The original file ID.
            description: The generated description.
            query: Optional query used for the description.
        """
        log.debug(f"Setting cache entry for file: {file_id}")
        with self.connection() as conn:
            # Use upsert pattern (ON CONFLICT DO UPDATE)
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            stmt = pg_insert(file_description_cache).values(
                cache_key=cache_key,
                file_id=file_id,
                query=query,
                description=description,
            ).on_conflict_do_update(
                index_elements=['cache_key'],
                set_={'description': description}
            )
            conn.execute(stmt)
            log.debug(f"Cached description for file {file_id}")

    def delete_cache_by_file(self, file_id: str) -> int:
        """
        Delete all cached descriptions for a file.

        Args:
            file_id: The file ID to delete cache entries for.

        Returns:
            Number of entries deleted.
        """
        log.debug(f"Deleting cache entries for file: {file_id}")
        with self.connection() as conn:
            stmt = delete(file_description_cache).where(
                file_description_cache.c.file_id == file_id
            )
            result = conn.execute(stmt)
            count = result.rowcount
            if count > 0:
                log.debug(f"Deleted {count} cache entries for file {file_id}")
            return count
