"""
Database operations and initialization.
"""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from backend.config import DB_DIR

# Database configuration
Path(DB_DIR).mkdir(exist_ok=True)
DB_PATH = os.path.join(DB_DIR, 'chat.db')


@contextmanager
def get_db():
    """
    Manages a context for database connection, ensuring proper cleanup of resources.

    This function is used to provide a managed context for database interaction.
    It opens a SQLite database connection and ensures it is properly closed after
    use, even if an exception occurs during the interaction. The connection uses
    a row factory to allow access to columns by name.

    :param DB_PATH: The file path to the SQLite database.

    :yield: A SQLite database connection object.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """
    Initializes the database by creating necessary tables, indices, and triggers, as well as modifying
    tables to add new columns if they are missing. Existing data migrations and structural changes are
    also handled to enhance database schema integrity and functionality.

    :raises Exception: If the database connection or operations fail.
    :returns: None
    """
    with get_db() as conn:
        cur = conn.cursor()

        # Create users table
        cur.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                                                       id INTEGER PRIMARY KEY,
                                                       email TEXT UNIQUE NOT NULL,
                                                       name TEXT,
                                                       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    ''')

        # Create conversations table with UUID support
        cur.execute('''
                    CREATE TABLE IF NOT EXISTS conversations (
                                                               id TEXT PRIMARY KEY,
                                                               userId INTEGER NOT NULL,
                                                               name TEXT NOT NULL,
                                                               participants TEXT,
                                                               createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                                               updatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                                               version INTEGER DEFAULT 1,
                                                               lastModified INTEGER,
                                                               FOREIGN KEY(userId) REFERENCES users(id)
                      )
                    ''')

        # Create messages table to store chat messages
        cur.execute('''
                    CREATE TABLE IF NOT EXISTS messages (
                                                          id INTEGER PRIMARY KEY,
                                                          conversationId TEXT NOT NULL,
                                                          roleName TEXT NOT NULL,
                                                          content TEXT NOT NULL,
                                                          time INTEGER NOT NULL,
                                                          type TEXT DEFAULT 'text',
                                                          version INTEGER DEFAULT 1,
                                                          lastModified INTEGER,
                                                          FOREIGN KEY(conversationId) REFERENCES conversations(id)
                      )
                    ''')

        # Create sessions table to manage user sessions
        cur.execute('''
                    CREATE TABLE IF NOT EXISTS sessions (
                                                          session_key TEXT PRIMARY KEY,
                                                          user_id INTEGER NOT NULL,
                                                          email TEXT NOT NULL,
                                                          is_guest BOOLEAN DEFAULT FALSE,
                                                          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                                          expires_at TIMESTAMP NOT NULL,
                                                          last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                                          FOREIGN KEY(user_id) REFERENCES users(id)
                      )
                    ''')

        # Check if is_guest column exists, if not add it (for existing databases)
        cur.execute("PRAGMA table_info(sessions)")
        columns = [column[1] for column in cur.fetchall()]
        if 'is_guest' not in columns:
            print("Adding is_guest column to sessions table...")
            cur.execute('ALTER TABLE sessions ADD COLUMN is_guest BOOLEAN DEFAULT FALSE')

        # Check if csrf_token column exists, if not add it
        if 'csrf_token' not in columns:
            print("Adding csrf_token column to sessions table...")
            cur.execute('ALTER TABLE sessions ADD COLUMN csrf_token TEXT')

        # Check if type column exists in messages table, if not add it
        cur.execute("PRAGMA table_info(messages)")
        columns = [column[1] for column in cur.fetchall()]
        if 'type' not in columns:
            print("Adding type column to messages table...")
            cur.execute("ALTER TABLE messages ADD COLUMN type TEXT DEFAULT 'text'")

        # Add version columns for optimistic locking
        if 'version' not in columns:
            print("Adding version column to messages table...")
            cur.execute("ALTER TABLE messages ADD COLUMN version INTEGER DEFAULT 1")

        if 'lastModified' not in columns:
            print("Adding lastModified column to messages table...")
            cur.execute("ALTER TABLE messages ADD COLUMN lastModified INTEGER")

        # Check conversations table for version columns
        cur.execute("PRAGMA table_info(conversations)")
        columns = [column[1] for column in cur.fetchall()]
        if 'version' not in columns:
            print("Adding version column to conversations table...")
            cur.execute("ALTER TABLE conversations ADD COLUMN version INTEGER DEFAULT 1")

        if 'lastModified' not in columns:
            print("Adding lastModified column to conversations table...")
            cur.execute("ALTER TABLE conversations ADD COLUMN lastModified INTEGER")

        # Create guest_usage table
        cur.execute('''
                    CREATE TABLE IF NOT EXISTS guest_usage (
                                                             ip_address TEXT PRIMARY KEY,
                                                             request_count INTEGER NOT NULL,
                                                             last_request_at TIMESTAMP NOT NULL
                    )
                    ''')

        # Create index for faster querying by conversationId and time
        cur.execute('''
                    CREATE INDEX IF NOT EXISTS idx_conversation_time
                      ON messages(conversationId, time)
                    ''')

        # Create index for faster querying by userId on conversations
        cur.execute('''
                    CREATE INDEX IF NOT EXISTS idx_conversations_user
                      ON conversations(userId)
                    ''')

        conn.commit()

        # Create Table for user-based settings
        cur.execute('''
                    CREATE TABLE IF NOT EXISTS user_settings (
                                                               user_id INTEGER PRIMARY KEY,
                                                               theme TEXT NOT NULL,
                                                               language TEXT NOT NULL,
                                                               updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    ''')

        # Add updated_at column to messages table if it doesn't exist
        cur.execute("PRAGMA table_info(messages)")
        columns = [column[1] for column in cur.fetchall()]
        if 'updated_at' not in columns:
            print("Adding updated_at column to messages table...")
            cur.execute("ALTER TABLE messages ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

        # Add updated_at column to user_settings table if it doesn't exist
        cur.execute("PRAGMA table_info(user_settings)")
        columns = [column[1] for column in cur.fetchall()]
        if 'updated_at' not in columns:
            print("Adding updated_at column to user_settings table...")
            cur.execute("ALTER TABLE user_settings ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

        # Add rating column to messages table if it doesn't exist
        cur.execute("PRAGMA table_info(messages)")
        columns = [column[1] for column in cur.fetchall()]
        if 'rating' not in columns:
            print("Adding rating column to messages table...")
            cur.execute("ALTER TABLE messages ADD COLUMN rating INTEGER")

        # Create trigger to update conversations timestamp
        cur.execute('''
                    CREATE TRIGGER IF NOT EXISTS update_conversations_timestamp
                    AFTER UPDATE ON conversations
                    BEGIN
                    UPDATE conversations SET updatedAt = CURRENT_TIMESTAMP WHERE id = NEW.id;
                    END;
                    ''')

        # Create trigger to update messages timestamp
        cur.execute('''
                    CREATE TRIGGER IF NOT EXISTS update_messages_timestamp
                    AFTER UPDATE ON messages
                    BEGIN
                    UPDATE messages SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
                    END;
                    ''')

        # Create trigger to update user_settings timestamp
        cur.execute('''
                    CREATE TRIGGER IF NOT EXISTS update_user_settings_timestamp
                    AFTER UPDATE ON user_settings
                    BEGIN
                    UPDATE user_settings SET updated_at = CURRENT_TIMESTAMP WHERE user_id = NEW.user_id;
                    END;
                    ''')

        conn.commit()
