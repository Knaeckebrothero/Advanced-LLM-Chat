"""
This is a mockup of a backend server for a chat application.
It provides a simple API for sending and receiving messages in a conversation.
The server uses SQLite as a database to store messages and conversation data.
The server also uses Replicate to generate AI responses to messages in a conversation.
"""
import os
import sqlite3
import trustme
import time
import replicate
import secrets
import asyncio
import json
import hashlib
import uuid
from fastapi import FastAPI, Response, status, Request, HTTPException, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel
from typing import List, Dict, Optional, Union, Literal
from dotenv import load_dotenv, find_dotenv
from pathlib import Path
from contextlib import contextmanager, asynccontextmanager
from datetime import datetime, timedelta, UTC


# List of available LLMs
AVAILABLE_LLMS = [
  "deepseek-ai/deepseek-v3",
  "openai/gpt-4o",
  "meta/meta-llama-3-8b-instruct",
  "meta/meta-llama-3-70b-instruct",
  "meta/meta-llama-3.1-405b-instruct",
]


class ErrorResponse(BaseModel):
  """
  Represents an error response model for providing error details to clients.
  """
  error: str


class MockLoginRequest(BaseModel):
  email: str
  # In real implementation, this might include IDP tokens, SAML response, etc.

class GuestLoginRequest(BaseModel):
  ip_address: str


class LoginResponse(BaseModel):
  """
  Represents the response received upon a successful login attempt.
  """
  user: dict
  message: str
  token: Optional[str] = None


class ConversationState(BaseModel):
  """
  Represents the state of a conversation.
  """
  id: str  # Now using UUID
  hashsum: int


class ApiConversationsCheck(BaseModel):
  """
  Represents a model for checking the list of conversation states.
  """
  conversations: List[ConversationState]


# New content type models
class FileReference(BaseModel):
  """
  Reference to an uploaded file
  """
  id: str
  name: str
  size: int
  mimeType: str


class TextContent(BaseModel):
  """
  Text message content with optional attachments
  """
  content: str
  attachments: Optional[List[FileReference]] = []


class VoiceContent(BaseModel):
  """
  Voice message content
  """
  audioData: str  # Base64 encoded audio
  duration: float
  mimeType: str
  transcript: Optional[str] = None
  waveform: Optional[List[float]] = None


class ApiMessageSend(BaseModel):
  """
  Represents a message sent within a specific conversation.
  Supports multiple content types through a discriminated union.
  """
  conversationId: str  # Now using UUID
  roleName: str
  type: Literal["text", "voice"]
  content: Union[str, TextContent, VoiceContent]  # Backwards compatible - str for legacy, objects for new types
  time: int
  version: Optional[int] = 1
  lastModified: Optional[int] = None


class ApiMessageGenerate(BaseModel):
  """
  Represents a model for generating API messages.
  """
  conversationId: str  # Now using UUID
  roleName: str
  time: int
  temperature: Optional[float] = None
  top_p: Optional[float] = None
  systemPrompt: Optional[str] = None

class ApiMessageSendAndGenerate(BaseModel):
  """
  Combined request for sending a message and generating AI response.
  """
  # Message to send
  conversationId: str  # Now using UUID
  roleName: str
  type: Literal["text", "voice"]
  content: Union[str, TextContent, VoiceContent]
  time: int
  version: Optional[int] = 1
  lastModified: Optional[int] = None
  
  # AI generation settings
  generateResponse: bool = True
  aiParticipant: str = "Assistant"
  temperature: Optional[float] = None
  top_p: Optional[float] = None
  systemPrompt: Optional[str] = None


class MessagePatch(BaseModel):
  """
  Represents a model for updating message data within a conversation.
  """
  id: int
  conversationId: str  # Now using UUID
  content: str
  version: int  # Required for optimistic locking


class MessageResponse(BaseModel):
  """
  Represents a response message within a conversation context.
  """
  id: int
  conversationId: str  # Now using UUID
  roleName: str
  content: str
  time: int
  type: Optional[str] = "text"  # Default to "text" for backwards compatibility
  version: int = 1
  lastModified: Optional[int] = None

class SendAndGenerateResponse(BaseModel):
  """
  Response containing both the saved user message and generated AI response.
  """
  userMessage: MessageResponse
  aiMessage: Optional[MessageResponse] = None


class ConversationResponse(BaseModel):
  """
  Encapsulates the response details of a conversation.
  """
  id: str  # Now using UUID
  userId: int
  name: str
  participants: List[str]
  createdAt: datetime
  updatedAt: datetime
  hashsum: int
  version: int = 1
  lastModified: Optional[int] = None

class Conversation(BaseModel):
  id: str  # Now using UUID
  userId: int
  name: str
  participants: Optional[str] = None
  createdAt: datetime
  updatedAt: datetime

class ConversationCreateRequest(BaseModel):
  name: str
  participants: List[str]


class AppSettings(BaseModel):
  """
  Define the structure of the settings that the frontend can GET or PUT
  """
  model: str
  temperature: float
  top_p: float
  systemPrompt: str
  darkMode: int
  languageIsEnglish: int


class AppSettingsWithMetadata(AppSettings):
  """
  Settings with sync metadata for frontend sync architecture
  """
  id: Optional[str] = None
  timestamp: Optional[datetime] = None
  syncHash: Optional[str] = None


class ConversationWithDetails(Conversation):
  """
  Conversation with additional metadata for sync
  """
  lastModified: Optional[datetime] = None
  messageCount: Optional[int] = None
  syncHash: Optional[str] = None


@contextmanager
def get_db():
  """
  Provides a context manager to handle SQLite database connections. This ensures
  that the connection to the database is properly opened and closed after use,
  reducing the risk of resource leakage or runtime database errors. The method
  yields an SQLite connection object that can be used to interact with the
  database.

  Parameters and return types are defined to clarify usage and expected output.

  Yields:
      sqlite3.Connection: The SQLite connection object initialized with the
          given database path and custom row factory configuration.

  Raises:
      None
  """
  conn = sqlite3.connect(DB_PATH)  # Changed from 'chat.db' to DB_PATH
  conn.row_factory = sqlite3.Row
  try:
    yield conn
  finally:
    conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
  """
  Manages the lifespan of the FastAPI application.
  """
  asyncio.create_task(cleanup_expired_sessions())
  yield


def generate_session_key(length=32) -> str:
  """
  Generate a secure, random session key.
  """
  return secrets.token_urlsafe(length)


def generate_conversation_id() -> str:
  """
  Generate a unique conversation ID using UUID v4.
  Returns a string representation of the UUID.
  """
  return str(uuid.uuid4())


def generate_csrf_token() -> str:
  """
  Generate a secure CSRF token.
  """
  return secrets.token_urlsafe(32)


def create_session(user_id: int, user_email: str, session_duration_hours=24, is_guest=False, regenerate_from=None) -> tuple[str, str]:
  """
  Creates a session for a given user with a specified duration in hours.
  If regenerate_from is provided, deletes the old session first.
  Returns tuple of (session_key, csrf_token).
  """
  # Delete old session if regenerating
  if regenerate_from:
    delete_session(regenerate_from)
  
  session_key = generate_session_key()
  csrf_token = generate_csrf_token()
  
  # Use environment variable for session timeout if available
  session_timeout = int(os.getenv('SESSION_TIMEOUT_HOURS', str(session_duration_hours)))
  expires_at = datetime.now(UTC) + timedelta(hours=session_timeout)

  # Save session to database
  with get_db() as db:
    db.execute(
      """
      INSERT INTO sessions (session_key, user_id, email, expires_at, is_guest, csrf_token)
      VALUES (?, ?, ?, ?, ?, ?)
      """, (session_key, user_id, user_email, expires_at.isoformat(), is_guest, csrf_token))

    db.commit()

  return session_key, csrf_token


def validate_session(session_key: str) -> Optional[dict]:
  """
  Validates a provided session key by checking the database.
  Includes session timeout information.
  """
  if not session_key:
    return None

  with get_db() as conn:
    cur = conn.cursor()
    cur.execute(
      """
      SELECT user_id, email, expires_at, last_activity, is_guest, csrf_token
      FROM sessions
      WHERE session_key = ?
      """, (session_key,))
    result = cur.fetchone()

    if not result:
      return None

    expires_at = datetime.fromisoformat(result["expires_at"])
    current_time = datetime.now(UTC)
    
    if current_time > expires_at:
      # Session expired, clean up
      cur.execute("DELETE FROM sessions WHERE session_key = ?", (session_key,))
      conn.commit()
      return None

    # Update last activity timestamp
    cur.execute("""
                UPDATE sessions
                SET last_activity = ?
                WHERE session_key = ?
                """, (current_time.isoformat(), session_key))
    conn.commit()
    
    # Calculate time until expiry
    time_until_expiry = expires_at - current_time
    expires_in_seconds = int(time_until_expiry.total_seconds())

    return {
      "user_id": result["user_id"],
      "email": result["email"],
      "is_guest": result["is_guest"],
      "csrf_token": result["csrf_token"],
      "expires_at": expires_at.isoformat(),
      "expires_in": expires_in_seconds
    }


def delete_session(session_key: str):
  """
  Deletes a session from the database.
  """
  with get_db() as conn:
    cur = conn.cursor()
    cur.execute("DELETE FROM sessions WHERE session_key = ?", (session_key,))
    conn.commit()


async def validate_csrf_token(request: Request) -> bool:
  """
  Validates CSRF token from request headers against the session token.
  Returns True if valid, False otherwise.
  """
  # Skip CSRF validation for safe methods
  if request.method in ["GET", "HEAD", "OPTIONS"]:
    return True
  
  # Skip CSRF validation for authentication endpoints
  if request.url.path in ["/api/auth/mock-login", "/api/auth/guest-login", "/api/auth/logout", "/api/auth/refresh-session"]:
    return True
  
  # Get session key from cookie
  session_key = request.cookies.get("session")
  if not session_key:
    return False
  
  # Get session data
  session_data = validate_session(session_key)
  if not session_data:
    return False
  
  # Get CSRF token from header
  csrf_token_header = request.headers.get("X-CSRF-Token")
  if not csrf_token_header:
    return False
  
  # Compare tokens
  return csrf_token_header == session_data.get("csrf_token")


async def get_current_user(request: Request) -> dict:
  """
  Retrieves the current user based on the session information provided
  in the request cookies.
  """
  session_key = request.cookies.get("session")
  if not session_key:
    raise HTTPException(status_code=401, detail="Not authenticated")

  user_info = validate_session(session_key)
  if not user_info:
    raise HTTPException(status_code=401, detail="Invalid or expired session")

  return user_info


async def get_current_user_optional(request: Request) -> Optional[dict]:
  """
  Attempts to retrieve the current user based on the provided request.
  """
  try:
    return await get_current_user(request)
  except HTTPException:
    return None


async def cleanup_expired_sessions():
  """
  Periodically cleans up expired sessions from the database.
  """
  while True:
    try:
      # Clean database sessions
      with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
                    DELETE FROM sessions
                    WHERE datetime(expires_at) < datetime('now')
                    """)
        conn.commit()

    except Exception as e:
      print(f"Error cleaning up sessions: {e}")

    # Run every hour
    await asyncio.sleep(3600)


def migrate_to_uuid_conversations(conn):
  """
  Migrate existing conversations from integer IDs to UUID-based IDs.
  """
  cur = conn.cursor()
  
  # Check if we already have UUID-based conversations
  cur.execute("PRAGMA table_info(conversations)")
  columns = cur.fetchall()
  id_column = next((col for col in columns if col[1] == 'id'), None)
  
  # If ID column is already TEXT, migration is done
  if id_column and id_column[2] == 'TEXT':
    return
  
  print("Migrating conversations to UUID-based IDs...")
  
  # Create new tables with UUID support
  cur.execute('''
    CREATE TABLE IF NOT EXISTS conversations_new (
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
  
  cur.execute('''
    CREATE TABLE IF NOT EXISTS messages_new (
      id INTEGER PRIMARY KEY,
      conversationId TEXT NOT NULL,
      roleName TEXT NOT NULL,
      content TEXT NOT NULL,
      time INTEGER NOT NULL,
      type TEXT DEFAULT 'text',
      version INTEGER DEFAULT 1,
      lastModified INTEGER,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(conversationId) REFERENCES conversations_new(id)
    )
  ''')
  
  # Migrate existing conversations
  cur.execute("SELECT * FROM conversations")
  old_conversations = cur.fetchall()
  
  id_mapping = {}  # old_id -> new_uuid
  
  for conv in old_conversations:
    new_id = generate_conversation_id()
    id_mapping[conv['id']] = new_id
    
    cur.execute('''
      INSERT INTO conversations_new (id, userId, name, participants, createdAt, updatedAt)
      VALUES (?, ?, ?, ?, ?, ?)
    ''', (new_id, conv['userId'], conv['name'], conv['participants'], 
          conv['createdAt'], conv['updatedAt']))
  
  # Migrate messages
  cur.execute("SELECT * FROM messages")
  old_messages = cur.fetchall()
  
  for msg in old_messages:
    old_conv_id = msg['conversationId']
    new_conv_id = id_mapping.get(old_conv_id)
    
    if new_conv_id:
      # Handle sqlite3.Row objects which don't have .get() method
      msg_type = msg['type'] if 'type' in msg.keys() else 'text'
      updated_at = msg['updated_at'] if 'updated_at' in msg.keys() else None
      
      cur.execute('''
        INSERT INTO messages_new (id, conversationId, roleName, content, time, type, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
      ''', (msg['id'], new_conv_id, msg['roleName'], msg['content'], 
            msg['time'], msg_type, updated_at))
  
  # Drop old tables and rename new ones
  cur.execute("DROP TABLE IF EXISTS messages")
  cur.execute("DROP TABLE IF EXISTS conversations")
  cur.execute("ALTER TABLE conversations_new RENAME TO conversations")
  cur.execute("ALTER TABLE messages_new RENAME TO messages")
  
  # Recreate indexes
  cur.execute('''
    CREATE INDEX IF NOT EXISTS idx_conversation_time
    ON messages(conversationId, time)
  ''')
  
  cur.execute('''
    CREATE INDEX IF NOT EXISTS idx_conversations_user
    ON conversations(userId)
  ''')
  
  conn.commit()
  print("Migration to UUID-based conversations completed!")


def init_db():
  """
  Initializes the database and sets up the required tables if they are not already created.
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
                                                           model TEXT NOT NULL,
                                                           temperature REAL NOT NULL,
                                                           top_p REAL NOT NULL,
                                                           systemPrompt TEXT NOT NULL,
                                                           darkMode INTEGER NOT NULL,
                                                           languageIsEnglish INTEGER NOT NULL,
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
    
    # Migrate existing data to UUID-based conversations
    migrate_to_uuid_conversations(conn)



def setup_development_certificates():
  """
  Sets up self-signed SSL certificates for local development using the `trustme` library.
  """
  ca = trustme.CA()
  server_cert = ca.issue_cert("localhost")
  cert_dir = Path("devcerts")
  cert_dir.mkdir(exist_ok=True)

  server_cert.private_key_and_cert_chain_pem.write_to_path(cert_dir / "server.pem")
  server_cert.private_key_pem.write_to_path(cert_dir / "server.key")
  ca.cert_pem.write_to_path(cert_dir / "ca.pem")

  return str(cert_dir / "server.pem"), str(cert_dir / "server.key")


def generate_hash(messages: List[sqlite3.Row]) -> int:
  """
  Generates a hash value based on the content of the provided messages.
  """
  if not messages:
    return 0

  hash_value = 0
  hash_chars = ""

  for message in messages:
    content = message['content']
    if not content:
      hash_value += 0
      continue

    hash_value += ord(content[0])
    hash_value += ord(content[-1])
    hash_value *= len(content)
    hash_chars += content[0] + content[-1] + str(len(content))

  hash_value %= (2 ** 32)
  print(f"Generated hashsum: {hash_value} string rep: {hash_chars}")
  return hash_value


def generate_sha256_hash(content: str) -> str:
  """
  Generate SHA-256 hash matching frontend implementation
  """
  return hashlib.sha256(content.encode('utf-8')).hexdigest()


async def generate_llm_response(prompt: str, temperature: float, top_p: float, system_prompt: str, model: str) -> str:
  """
  Generates a text response using a Large Language Model (LLM) via Replicate API.
  """
  try:
    # Use Meta's Llama model through Replicate
    output = replicate.run(
      model,
      input={
        "prompt": prompt,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": 1024,
        "system_prompt": system_prompt,
      }
    )
    print("\n".join([
      f"LLM Input:",
      f"  model = {model}",
      f"  temp = {temperature}",
      f"  top_p = {top_p}",
      f"  system_prompt = {system_prompt}",
      "  prompt:",
      prompt
    ]))


    # Replicate returns a generator, collect all parts of the streamed response
    return "".join(output)
  except Exception as e:
    print(f"Error generating response: {str(e)}")
    return "I apologize, but I encountered an error generating a response."


async def get_conversation_context(conversation_id: str, limit: int = 5) -> str:
  """
  Retrieves the recent message history for a specific conversation.
  """
  try:
    with get_db() as conn:
      cur = conn.cursor()
      cur.execute(
        """
        SELECT roleName, content
        FROM messages
        WHERE conversationId = ?
        ORDER BY time DESC
        LIMIT ?
        """,
        (conversation_id, limit)
      )
      messages = cur.fetchall()

      # Build context string by joining messages
      context = []
      for msg in reversed(messages):
        context.append(f"{msg['roleName']}: {msg['content']}")

      return "\n".join(context)
  except Exception as e:
    print(f"Error getting conversation context: {str(e)}")
    return ""


def verify_conversation_ownership(conversation_id: str, user_id: int, is_guest: bool = False) -> bool:
  """
  Verifies that a user owns a specific conversation.
  Returns True if the user owns the conversation or if it's a guest user.
  """
  # Guest users can access any conversation (for offline mode)
  if is_guest:
    return True

  with get_db() as conn:
    cur = conn.cursor()
    cur.execute(
      "SELECT userId FROM conversations WHERE id = ?",
      (conversation_id,)
    )
    result = cur.fetchone()

    if not result:
      return False

    return result['userId'] == user_id

async def rate_limit_guest(request: Request, current_user: Optional[dict] = Depends(get_current_user_optional)):
  if current_user and not current_user.get("is_guest"):
    return  # Not a guest, no rate limit

  ip_address = request.client.host
  with get_db() as db:
    cur = db.cursor()
    cur.execute("SELECT request_count, last_request_at FROM guest_usage WHERE ip_address = ?", (ip_address,))
    usage = cur.fetchone()

    now = datetime.now(UTC)
    limit_duration = timedelta(hours=3)
    max_requests = 5

    if usage:
      last_request_at = datetime.fromisoformat(usage["last_request_at"])
      if now - last_request_at > limit_duration:
        # Reset counter
        cur.execute("UPDATE guest_usage SET request_count = 1, last_request_at = ? WHERE ip_address = ?", (now.isoformat(), ip_address))
      elif usage["request_count"] >= max_requests:
        reset_time = last_request_at + limit_duration
        retry_after_seconds = (reset_time - now).total_seconds()
        headers = {"Retry-After": str(int(retry_after_seconds))}
        raise HTTPException(
          status_code=429,
          detail=f"Too many requests. Please try again after {reset_time.isoformat()}",
          headers=headers
        )
      else:
        cur.execute("UPDATE guest_usage SET request_count = request_count + 1, last_request_at = ? WHERE ip_address = ?", (now.isoformat(), ip_address))
    else:
      cur.execute("INSERT INTO guest_usage (ip_address, request_count, last_request_at) VALUES (?, 1, ?)", (ip_address, now.isoformat()))
    db.commit()


# Load environment variables from .env file
load_dotenv(find_dotenv())

# Database configuration
DB_DIR = os.getenv('DB_DIR', './data')
Path(DB_DIR).mkdir(exist_ok=True)
DB_PATH = os.path.join(DB_DIR, 'chat.db')

# Session storage (in-memory cache for tracking active sessions)
sessions: Dict[str, dict] = {}

# Setup FastAPI app
app = FastAPI(
  title="Chat API",
  version="2.0.0",
  description="This is a backend server for a chat application.",
  docs_url=None,
  redoc_url=None,
  openapi_url="/api/openapi.json",
  lifespan=lifespan
)

# Initialize the database on startup
init_db()


@app.get("/api/llms", response_model=List[str], tags=["LLM"])
async def get_llms():
  """
  Get the list of available LLMs.
  """
  return AVAILABLE_LLMS


@app.get(app.openapi_url, include_in_schema=False)
async def custom_openapi():
  """
  Custom OpenAPI schema endpoint.
  """
  return get_openapi(
    title=app.title,
    version=app.version,
    description=app.description,
    routes=app.routes,
  )


@app.get("/api/docs", include_in_schema=False)
async def custom_swagger_ui_html(req: Request):
  """
  Serves the Swagger UI HTML for API documentation.
  """
  root_path = req.scope.get("root_path", "").rstrip("/")
  openapi_url = root_path + app.openapi_url
  return get_swagger_ui_html(
    openapi_url=openapi_url,
    title=app.title + " - Swagger UI"
  )

@app.post("/api/auth/guest-login", response_model=LoginResponse)
async def guest_login(request: GuestLoginRequest, req: Request, response: Response):
  ip_address = request.ip_address

  # If IP address is 'unknown', use a fallback
  if ip_address == 'unknown':
    ip_address = f"guest_{secrets.token_hex(4)}"

  with get_db() as db:
    cur = db.cursor()
    cur.execute("SELECT request_count, last_request_at FROM guest_usage WHERE ip_address = ?", (ip_address,))
    usage = cur.fetchone()

    now = datetime.now(UTC)
    limit_duration = timedelta(hours=3)
    max_requests = 5

    if usage:
      last_request_at = datetime.fromisoformat(usage["last_request_at"])
      if now - last_request_at > limit_duration:
        cur.execute("UPDATE guest_usage SET request_count = 1, last_request_at = ? WHERE ip_address = ?", (now.isoformat(), ip_address))
      elif usage["request_count"] >= max_requests:
        reset_time = last_request_at + limit_duration
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded. Please try again after {reset_time.isoformat()}.")
    else:
      cur.execute("INSERT INTO guest_usage (ip_address, request_count, last_request_at) VALUES (?, 1, ?)", (ip_address, now.isoformat()))

    db.commit()

  # Get existing session to regenerate from
  old_session_key = req.cookies.get("session")

  guest_email = f"guest_{secrets.token_hex(4)}@guest.com"
  guest_user = {"id": 0, "email": guest_email, "name": "Guest"}

  # Use shorter timeout for guest sessions
  guest_timeout_hours = int(os.getenv('GUEST_SESSION_TIMEOUT_HOURS', '6'))
  
  # Create new guest session with custom timeout, regenerating old session
  session_key, csrf_token = create_session(0, guest_email, session_duration_hours=guest_timeout_hours, is_guest=True, regenerate_from=old_session_key)
  
  max_age = guest_timeout_hours * 3600

  response.set_cookie(
    key="session",
    value=session_key,
    max_age=max_age,
    httponly=True,
    secure=True,
    samesite="lax",
    path="/"
  )
  
  # Set CSRF token in response header
  response.headers["X-CSRF-Token"] = csrf_token

  return LoginResponse(
    user=guest_user,
    message="Guest login successful",
    token=session_key
  )

@app.post("/api/auth/mock-login", response_model=LoginResponse)
async def mock_login(request: MockLoginRequest, req: Request, response: Response):
  """
  Handles a mock login process for a user with provided request data.
  """
  print(f"Login attempt for: {request.email}")

  # Get existing session to regenerate from
  old_session_key = req.cookies.get("session")

  with get_db() as db:
    cur = db.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (request.email,))
    user = cur.fetchone()

    if not user:
      # User doesn't exist, create a new one
      user_name = request.email.split('@')[0].title()
      cur.execute("INSERT INTO users (email, name) VALUES (?, ?)", (request.email, user_name))
      user_id = cur.lastrowid
      db.commit()
    else:
      user_id = user['id']
      user_name = user['name']

  # Create session with is_guest=False for regular users, regenerating old session
  session_key, csrf_token = create_session(user_id, request.email, is_guest=False, regenerate_from=old_session_key)
  
  # Calculate max_age based on session timeout
  session_timeout_hours = int(os.getenv('SESSION_TIMEOUT_HOURS', '24'))
  max_age = session_timeout_hours * 3600

  # Set session cookie
  response.set_cookie(
    key="session",
    value=session_key,
    max_age=max_age,
    httponly=True,  # Prevents JS access
    secure=True,  # HTTPS only
    samesite="lax",
    path="/"
  )
  
  # Set CSRF token in response header
  response.headers["X-CSRF-Token"] = csrf_token

  return LoginResponse(
    user={
      "id": user_id,
      "email": request.email,
      "name": user_name
    },
    message="Mock login successful"
  )


@app.post("/api/auth/logout")
async def logout(request: Request, response: Response):
  """
  Handles user logout by deleting the session and clearing the session cookie.
  Does not auto-create a guest session - let the frontend decide.
  """
  session_key = request.cookies.get("session")
  if session_key:
    delete_session(session_key)

  # Delete cookie
  response.delete_cookie(
    key="session",
    path="/",
    secure=True,
    httponly=True,
    samesite="lax"
  )
  return {"message": "Logged out successfully"}


@app.post("/api/auth/refresh-session")
async def refresh_session(request: Request, response: Response, current_user: dict = Depends(get_current_user)):
  """
  Refreshes the current session by extending its expiration time.
  Only works if the session has less than 1 hour remaining.
  """
  session_key = request.cookies.get("session")
  if not session_key:
    raise HTTPException(status_code=401, detail="No session to refresh")
  
  # Check if session is close to expiring (less than 1 hour)
  expires_in = current_user.get("expires_in", 0)
  if expires_in > 3600:  # More than 1 hour remaining
    return {
      "message": "Session does not need refresh yet",
      "expires_in": expires_in
    }
  
  # Create new session with same user info
  user_id = current_user["user_id"]
  email = current_user["email"]
  is_guest = current_user.get("is_guest", False)
  
  # Determine session duration based on user type
  if is_guest:
    session_hours = int(os.getenv('GUEST_SESSION_TIMEOUT_HOURS', '6'))
  else:
    session_hours = int(os.getenv('SESSION_TIMEOUT_HOURS', '24'))
  
  # Create new session, regenerating the old one
  new_session_key, new_csrf_token = create_session(
    user_id, email, session_hours, is_guest, regenerate_from=session_key
  )
  
  # Set new session cookie
  max_age = session_hours * 3600
  response.set_cookie(
    key="session",
    value=new_session_key,
    max_age=max_age,
    httponly=True,
    secure=True,
    samesite="lax",
    path="/"
  )
  
  # Set new CSRF token
  response.headers["X-CSRF-Token"] = new_csrf_token
  
  return {
    "message": "Session refreshed successfully",
    "expires_in": max_age
  }


@app.get("/api/auth/me")
async def get_me(request: Request, response: Response, current_user: dict = Depends(get_current_user)):
  """
  Retrieves the details of the currently authenticated user.
  Includes session timeout information.
  """
  # Include CSRF token in response header
  if "csrf_token" in current_user:
    response.headers["X-CSRF-Token"] = current_user["csrf_token"]
  
  # Prepare user data with session info
  user_data = {
    "user_id": current_user["user_id"],
    "email": current_user["email"],
    "is_guest": current_user.get("is_guest", False),
    "session_expires_at": current_user.get("expires_at"),
    "session_expires_in": current_user.get("expires_in")
  }
  
  return {"user": user_data}


# API endpoints with authentication
@app.get("/api/conversations",
         response_model=List[ConversationResponse],
         responses={
           status.HTTP_204_NO_CONTENT: {"description": "No conversations found"},
           status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Internal server error"}
         },
         tags=["Conversation"])
async def get_conversations(response: Response, current_user: dict = Depends(get_current_user)):
  """
  Get conversations for the authenticated user.
  """
  print("Get conversations for user called")
  user_id = current_user['user_id']

  # Guest users don't have server-side conversations
  if current_user.get("is_guest"):
    response.status_code = status.HTTP_204_NO_CONTENT
    return []

  try:
    with get_db() as conn:
      cur = conn.cursor()
      # Fetch conversations for the current user
      cur.execute(
        """
        SELECT id, userId, name, participants, createdAt, updatedAt, version, lastModified 
        FROM conversations 
        WHERE userId = ?
        ORDER BY updatedAt DESC
        """,
        (user_id,)
      )
      conversation_rows = cur.fetchall()

      if not conversation_rows:
        response.status_code = status.HTTP_204_NO_CONTENT
        return []

      conversation_responses = []
      for conv_row in conversation_rows:
        conversation_id = conv_row['id']
        # Fetch messages for each conversation to calculate hash
        cur.execute(
          "SELECT content FROM messages WHERE conversationId = ?",
          (conversation_id,)
        )
        messages = cur.fetchall()
        hashsum = generate_hash(messages)
        
        # Parse participants (stored as JSON string)
        participants = json.loads(conv_row['participants']) if conv_row['participants'] else []
        
        conversation_responses.append(ConversationResponse(
          id=conversation_id,
          userId=conv_row['userId'],
          name=conv_row['name'],
          participants=participants,
          createdAt=conv_row['createdAt'],
          updatedAt=conv_row['updatedAt'],
          hashsum=hashsum,
          version=conv_row['version'] or 1,
          lastModified=conv_row['lastModified'] or int(time.time())
        ))

      return conversation_responses

  except Exception as e:
    print(f"Error: {str(e)}")
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return ErrorResponse(error=str(e))


@app.get("/api/conversation/{conversation_id}", 
         response_model=ConversationWithDetails,
         responses={
           status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Conversation not found"},
           status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Access denied"}
         },
         tags=["Conversation"])
async def get_conversation(conversation_id: str, response: Response, current_user: dict = Depends(get_current_user)):
  """
  Get a single conversation with metadata for sync
  """
  user_id = current_user['user_id']
  
  try:
    with get_db() as conn:
      cur = conn.cursor()
      
      # Fetch conversation details
      cur.execute("""
        SELECT id, userId, name, participants, createdAt, updatedAt
        FROM conversations 
        WHERE id = ? AND userId = ?
      """, (conversation_id, user_id))
      
      conv_row = cur.fetchone()
      
      if not conv_row:
        response.status_code = status.HTTP_404_NOT_FOUND
        return ErrorResponse(error="Conversation not found")
      
      # Get message count
      cur.execute("SELECT COUNT(*) as count FROM messages WHERE conversationId = ?", (conversation_id,))
      message_count = cur.fetchone()['count']
      
      # Get all messages to compute hash
      cur.execute("SELECT content FROM messages WHERE conversationId = ? ORDER BY time", (conversation_id,))
      messages = cur.fetchall()
      
      # Compute SHA-256 hash of conversation content
      content_str = ''.join([msg['content'] for msg in messages if msg['content']])
      sync_hash = generate_sha256_hash(content_str) if content_str else None
      
      # Return conversation with details
      return ConversationWithDetails(
        id=conv_row['id'],
        userId=conv_row['userId'],
        name=conv_row['name'],
        participants=conv_row['participants'],
        createdAt=conv_row['createdAt'],
        lastModified=conv_row['updatedAt'],
        messageCount=message_count,
        syncHash=sync_hash
      )
      
  except Exception as e:
    print(f"Error fetching conversation: {str(e)}")
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return ErrorResponse(error=str(e))


@app.get("/api/settings", response_model=AppSettingsWithMetadata)
async def get_settings(current_user: dict = Depends(get_current_user)):
  user_id = current_user["user_id"]

  if current_user.get("is_guest"):
    # Generate consistent hash for guest settings
    guest_settings = AppSettings(
      model="openai/gpt-4o",
      temperature=0.5,
      top_p=0.5,
      systemPrompt="You are a helpful assistant!",
      darkMode=0,
      languageIsEnglish=0
    )
    settings_str = f"{guest_settings.model}:{guest_settings.temperature}:{guest_settings.top_p}:{guest_settings.systemPrompt}:{guest_settings.darkMode}:{guest_settings.languageIsEnglish}"
    return AppSettingsWithMetadata(
      **guest_settings.dict(),
      id=f"guest-{user_id}",
      timestamp=datetime.now(UTC),
      syncHash=generate_sha256_hash(settings_str)
    )

  with get_db() as db:
    cur = db.cursor()
    cur.execute("""
                SELECT model, temperature, top_p, systemPrompt, darkMode, languageIsEnglish, updated_at
                FROM user_settings
                WHERE user_id = ?
                """, (user_id,))
    row = cur.fetchone()

    if row:
      settings_dict = dict(row)
      # Extract timestamp
      timestamp = settings_dict.pop('updated_at', None)
      # Create settings object
      settings = AppSettings(**settings_dict)
      # Generate hash
      settings_str = f"{settings.model}:{settings.temperature}:{settings.top_p}:{settings.systemPrompt}:{settings.darkMode}:{settings.languageIsEnglish}"
      
      return AppSettingsWithMetadata(
        **settings.dict(),
        id=f"user-{user_id}",
        timestamp=timestamp,
        syncHash=generate_sha256_hash(settings_str)
      )
    else:
      # Fallback defaults if user has no settings yet
      default_settings = AppSettings(
        model="openai/gpt-4o",
        temperature=0.5,
        top_p=0.5,
        systemPrompt="You are a helpful assistant!",
        darkMode=0,
        languageIsEnglish=0
      )
      settings_str = f"{default_settings.model}:{default_settings.temperature}:{default_settings.top_p}:{default_settings.systemPrompt}:{default_settings.darkMode}:{default_settings.languageIsEnglish}"
      
      return AppSettingsWithMetadata(
        **default_settings.dict(),
        id=f"user-{user_id}",
        timestamp=datetime.now(UTC),
        syncHash=generate_sha256_hash(settings_str)
      )


@app.put("/api/settings", response_model=AppSettingsWithMetadata)
async def update_settings(new_settings: AppSettings, current_user: dict = Depends(get_current_user)):
  user_id = current_user["user_id"]
  if current_user.get("is_guest"):
    raise HTTPException(status_code=403, detail="Guests cannot save settings.")

  with get_db() as db:
    cur = db.cursor()
    cur.execute("""
                INSERT INTO user_settings (user_id, model, temperature, top_p, systemPrompt, darkMode, languageIsEnglish, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                                                 model = excluded.model,
                                                 temperature = excluded.temperature,
                                                 top_p = excluded.top_p,
                                                 systemPrompt = excluded.systemPrompt,
                                                 darkMode = excluded.darkMode,
                                                 languageIsEnglish = excluded.languageIsEnglish,
                                                 updated_at = CURRENT_TIMESTAMP
                """, (
                  user_id,
                  new_settings.model,
                  new_settings.temperature,
                  new_settings.top_p,
                  new_settings.systemPrompt,
                  new_settings.darkMode,
                  new_settings.languageIsEnglish
                ))
    db.commit()
    
    # Fetch the updated settings with timestamp
    cur.execute("""
                SELECT updated_at
                FROM user_settings
                WHERE user_id = ?
                """, (user_id,))
    row = cur.fetchone()
    timestamp = row['updated_at'] if row else datetime.now(UTC)
    
  # Generate hash for the settings
  settings_str = f"{new_settings.model}:{new_settings.temperature}:{new_settings.top_p}:{new_settings.systemPrompt}:{new_settings.darkMode}:{new_settings.languageIsEnglish}"
  
  return AppSettingsWithMetadata(
    **new_settings.dict(),
    id=f"user-{user_id}",
    timestamp=timestamp,
    syncHash=generate_sha256_hash(settings_str)
  )


@app.post("/api/conversation/create", response_model=Conversation, status_code=status.HTTP_201_CREATED, tags=["Conversation"])
async def create_conversation(req: ConversationCreateRequest, current_user: dict = Depends(get_current_user)):
  """
  Creates a new conversation for the authenticated user.
  """
  user_id = current_user['user_id']
  with get_db() as conn:
    cur = conn.cursor()
    participants_json = json.dumps(req.participants)
    new_id = generate_conversation_id()  # Generate UUID
    
    cur.execute(
      "INSERT INTO conversations (id, userId, name, participants) VALUES (?, ?, ?, ?)",
      (new_id, user_id, req.name, participants_json)
    )
    conn.commit()

    cur.execute("SELECT id, userId, name, participants, createdAt, updatedAt FROM conversations WHERE id = ?", (new_id,))
    new_conv_row = cur.fetchone()

    return Conversation(**dict(new_conv_row))


@app.get("/api/conversation/messages/{conversation_id}/{timestamp}/{messages_count}",
         response_model=List[MessageResponse],
         responses={
           status.HTTP_204_NO_CONTENT: {"description": "No messages found"},
           status.HTTP_206_PARTIAL_CONTENT: {"description": "Partial content, more messages available"},
           status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "Conversation ID or timestamp missing"},
           status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Access denied"},
           status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Conversation not found"},
           status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Internal server error"}
         },
         tags=["Conversation"])
async def get_conversation_messages(
  conversation_id: str,
  timestamp: int,
  messages_count: int,
  response: Response,
  current_user: dict = Depends(get_current_user),
  after_timestamp: Optional[int] = None
):
  """
  Get messages for a specific conversation.
  - If after_timestamp is provided, get messages newer than that timestamp (incremental sync)
  - Otherwise, get messages before the given timestamp (pagination)
  """
  print(f"Get conversation messages called - after_timestamp: {after_timestamp}")

  try:
    if not conversation_id or timestamp is None:
      response.status_code = status.HTTP_400_BAD_REQUEST
      return ErrorResponse(error="Conversation ID and latest timestamp are required")

    # Verify ownership (guests can access any conversation)
    if not verify_conversation_ownership(conversation_id, current_user['user_id'], current_user.get("is_guest", False)):
      response.status_code = status.HTTP_403_FORBIDDEN
      return ErrorResponse(error="Access denied to this conversation")

    with get_db() as conn:
      cur = conn.cursor()
      
      # Different queries for incremental sync vs pagination
      if after_timestamp is not None:
        # Incremental sync: get messages newer than after_timestamp
        cur.execute(
          """
          SELECT id, conversationId, roleName, content, time, type, version, lastModified
          FROM messages
          WHERE conversationId = ? AND time > ?
          ORDER BY time ASC
          """,
          (conversation_id, after_timestamp)
        )
      else:
        # Normal pagination: get messages before timestamp
        cur.execute(
          """
          SELECT id, conversationId, roleName, content, time, type, version, lastModified
          FROM messages
          WHERE conversationId = ? AND time < ?
          ORDER BY time DESC LIMIT ?
          """,
          (conversation_id, timestamp, min(messages_count, 30))
        )
      
      messages_rows = cur.fetchall()

      if messages_rows:
        messages_data = [dict(msg) for msg in messages_rows]
        
        # For pagination, reverse to get chronological order
        if after_timestamp is None:
          messages_data.reverse()
        
        # Check if there might be more messages
        has_more = False
        if after_timestamp is None and messages_count > 30 and len(messages_data) == 30:
          has_more = True
          response.status_code = status.HTTP_206_PARTIAL_CONTENT
        else:
          response.status_code = status.HTTP_200_OK
          
        # Add header to indicate if more messages exist
        if after_timestamp is not None:
          # For incremental sync, check if there are any messages we didn't fetch
          if messages_data:
            oldest_fetched = messages_data[0]['time']
            cur.execute(
              "SELECT COUNT(*) as count FROM messages WHERE conversationId = ? AND time < ?",
              (conversation_id, oldest_fetched)
            )
            older_count = cur.fetchone()['count']
            response.headers["X-Has-More-Messages"] = str(older_count > 0)
          else:
            # No new messages, but check if there are any messages at all
            cur.execute(
              "SELECT COUNT(*) as count FROM messages WHERE conversationId = ?",
              (conversation_id,)
            )
            total_count = cur.fetchone()['count']
            response.headers["X-Has-More-Messages"] = str(total_count > 0)
          
        return messages_data
      else:
        # Return empty list instead of None to satisfy response model
        response.status_code = status.HTTP_200_OK
        # Add header for incremental sync
        if after_timestamp is not None:
          response.headers["X-Has-More-Messages"] = "false"
        return []

  except Exception as e:
    print(f"Error in get_conversation_messages: {str(e)}")
    import traceback
    traceback.print_exc()
    # Return empty list on error to satisfy the response model
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return []


@app.post("/api/message/send",
          response_model=Dict[str, int],
          status_code=status.HTTP_201_CREATED,
          responses={
            status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "Message content cannot be empty"},
            status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Access denied"},
            status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Internal server error"}
          },
          tags=["Message"])
async def user_send_message(request_body: ApiMessageSend, response: Response,
                            current_user: dict = Depends(get_current_user)):
  """
  Endpoint for a user to send a message.
  """
  print("Message send called")

  try:
    if not request_body.content:
      response.status_code = status.HTTP_400_BAD_REQUEST
      return ErrorResponse(error="Message content cannot be empty")

    # Verify ownership
    if not verify_conversation_ownership(request_body.conversationId, current_user['user_id'], current_user.get("is_guest", False)):
      response.status_code = status.HTTP_403_FORBIDDEN
      return ErrorResponse(error="Access denied to this conversation")

    message_id = int(time.time() * 1000)

    # Extract content based on message type
    content_str = ""
    message_type = getattr(request_body, 'type', 'text')  # Default to 'text' for backwards compatibility

    if message_type == 'text':
      if isinstance(request_body.content, str):
        # Legacy format - just a string
        content_str = request_body.content
      elif isinstance(request_body.content, dict):
        # New format - TextContent object
        content_str = request_body.content.get('content', '')
        # Store attachments as JSON in content for now
        attachments = request_body.content.get('attachments', [])
        if attachments:
          content_obj = {
            'content': content_str,
            'attachments': attachments
          }
          content_str = json.dumps(content_obj)
    elif message_type == 'voice':
      # Voice messages store the entire content object as JSON
      if isinstance(request_body.content, dict):
        content_str = json.dumps(request_body.content)
      else:
        content_str = str(request_body.content)

    with get_db() as conn:
      cur = conn.cursor()
      cur.execute(
        """
        INSERT INTO messages (id, conversationId, roleName, content, time, type, version, lastModified)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (message_id, request_body.conversationId, request_body.roleName,
         content_str, request_body.time, message_type, 
         request_body.version or 1, request_body.lastModified or int(time.time()))
      )
      conn.commit()

    return {"id": message_id}

  except Exception as e:
    print(f"Error: {str(e)}")
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return ErrorResponse(error=str(e))


@app.post("/api/message/generate",
          response_model=MessageResponse,
          status_code=status.HTTP_201_CREATED,
          responses={
            status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "Conversation ID missing"},
            status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Access denied"},
            status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Internal server error"}
          },
          tags=["Message"],
          dependencies=[Depends(rate_limit_guest)])
async def generate_message(request_body: ApiMessageGenerate, response: Response,
                           current_user: dict = Depends(get_current_user)):
  """
  Endpoint to generate an AI response for a conversation.
  """
  print("Generate message called")

  try:
    # Verify ownership
    if not verify_conversation_ownership(request_body.conversationId, current_user['user_id'], current_user.get("is_guest", False)):
      response.status_code = status.HTTP_403_FORBIDDEN
      return ErrorResponse(error="Access denied to this conversation")

    if not request_body.conversationId:
      response.status_code = status.HTTP_400_BAD_REQUEST
      return ErrorResponse(error="Conversation ID missing or invalid in request")

    # Get latest user settings from DB
    user_id = current_user["user_id"]
    with get_db() as db:
      cur = db.cursor()
      cur.execute("""
                  SELECT model, temperature, top_p, systemPrompt,
                         darkMode, languageIsEnglish
                  FROM user_settings
                  WHERE user_id = ?
                  """, (user_id,))

      row = cur.fetchone()

      if row:
        db_settings = AppSettings(**dict(row))
        print(f"Using settings from DB: {db_settings}")
      else:
        db_settings = AppSettings(
          model="openai/gpt-4o",
          temperature=0.5,
          top_p=0.5,
          systemPrompt="You are a helpful assistant!",
          darkMode=0,
          languageIsEnglish=0
        )

    temperature = request_body.temperature if request_body.temperature is not None else db_settings.temperature
    top_p = request_body.top_p if request_body.top_p is not None else db_settings.top_p
    system_prompt = request_body.systemPrompt if request_body.systemPrompt is not None else db_settings.systemPrompt
    model = db_settings.model

    # Get conversation context for the LLM
    context = await get_conversation_context(request_body.conversationId)

    # Generate AI response
    ai_response_content = await generate_llm_response(
      context,
      temperature,
      top_p,
      system_prompt,
      model
    )

    message_id = int(time.time() * 1000)
    current_time = int(time.time())

    message_doc_data = {
      'id': message_id,
      'conversationId': request_body.conversationId,
      'roleName': request_body.roleName,
      'content': ai_response_content,
      'time': current_time,
      'version': 1,
      'lastModified': current_time
    }

    with get_db() as conn:
      cur = conn.cursor()
      cur.execute(
        """
        INSERT INTO messages (id, conversationId, roleName, content, time, type, version, lastModified)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (message_id, request_body.conversationId, request_body.roleName,
         message_doc_data['content'], current_time, 'text', 1, current_time)
      )
      conn.commit()

    return message_doc_data

  except Exception as e:
    print(f"Error: {str(e)}")
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return ErrorResponse(error=str(e))


@app.patch("/api/message/patch",
           status_code=status.HTTP_204_NO_CONTENT,
           responses={
             status.HTTP_400_BAD_REQUEST: {"description": "Message ID missing or invalid request"},
             status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Access denied"},
             status.HTTP_404_NOT_FOUND: {"description": "Message not found"},
             status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Internal server error"}
           },
           tags=["Message"])
async def patch_message(request_body: MessagePatch, response: Response,
                        current_user: dict = Depends(get_current_user)):
  """
  Endpoint to update the content of an existing message.
  """
  print("Patch message called")

  try:
    if not request_body.id:
      response.status_code = status.HTTP_400_BAD_REQUEST
      return Response(status_code=status.HTTP_400_BAD_REQUEST, content="Message ID missing")

    # Verify ownership
    if not verify_conversation_ownership(request_body.conversationId, current_user['user_id'], current_user.get("is_guest", False)):
      response.status_code = status.HTTP_403_FORBIDDEN
      return ErrorResponse(error="Access denied to this conversation")

    with get_db() as conn:
      cur = conn.cursor()
      
      # First check current version
      cur.execute(
        """
        SELECT version FROM messages
        WHERE id = ? AND conversationId = ?
        """,
        (request_body.id, request_body.conversationId)
      )
      result = cur.fetchone()
      
      if not result:
        response.status_code = status.HTTP_404_NOT_FOUND
        return Response(status_code=status.HTTP_404_NOT_FOUND, content="Message not found")
      
      current_version = result[0] or 1
      
      # Check for version conflict
      if current_version != request_body.version:
        response.status_code = status.HTTP_409_CONFLICT
        return ErrorResponse(error=f"Version conflict: current version is {current_version}, provided version is {request_body.version}")
      
      # Update with version increment
      new_version = current_version + 1
      cur.execute(
        """
        UPDATE messages
        SET content = ?, version = ?, lastModified = ?
        WHERE id = ? AND conversationId = ? AND version = ?
        """,
        (request_body.content, new_version, int(time.time()), 
         request_body.id, request_body.conversationId, request_body.version)
      )
      conn.commit()

      if cur.rowcount == 0:
        response.status_code = status.HTTP_409_CONFLICT
        return ErrorResponse(error="Version conflict during update")

    return None

  except Exception as e:
    print(f"Error: {str(e)}")
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return ErrorResponse(error=str(e))


@app.delete("/api/message/delete/{conversation_id}/{message_id}",
            status_code=status.HTTP_204_NO_CONTENT,
            responses={
              status.HTTP_400_BAD_REQUEST: {"description": "Conversation ID or Message ID missing"},
              status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Access denied"},
              status.HTTP_404_NOT_FOUND: {"description": "Message not found"},
              status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Internal server error"}
            },
            tags=["Message"])
async def delete_message(conversation_id: str, message_id: int, response: Response,
                         current_user: dict = Depends(get_current_user)):
  """
  Endpoint to delete a specific message.
  """
  print("Delete message called")

  try:
    if not conversation_id or not message_id:
      response.status_code = status.HTTP_400_BAD_REQUEST
      return Response(status_code=status.HTTP_400_BAD_REQUEST,
                      content="Conversation ID or Message ID missing")

    # Verify ownership
    if not verify_conversation_ownership(conversation_id, current_user['user_id'], current_user.get("is_guest", False)):
      response.status_code = status.HTTP_403_FORBIDDEN
      return ErrorResponse(error="Access denied to this conversation")

    with get_db() as conn:
      cur = conn.cursor()
      cur.execute(
        "DELETE FROM messages WHERE conversationId = ? AND id = ?",
        (conversation_id, message_id)
      )
      conn.commit()

      if cur.rowcount == 0:
        response.status_code = status.HTTP_404_NOT_FOUND
        return Response(status_code=status.HTTP_404_NOT_FOUND, content="Message not found")

    return None

  except Exception as e:
    print(f"Error: {str(e)}")
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return ErrorResponse(error=str(e))


@app.post("/api/message/send-and-generate",
          response_model=SendAndGenerateResponse,
          status_code=status.HTTP_201_CREATED,
          responses={
            status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "Invalid request"},
            status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Access denied"},
            status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Internal server error"}
          },
          tags=["Message"],
          dependencies=[Depends(rate_limit_guest)])
async def send_and_generate_message(
    request_body: ApiMessageSendAndGenerate, 
    response: Response,
    current_user: dict = Depends(get_current_user)
):
  """
  Combined endpoint to send a user message and optionally generate an AI response.
  This reduces the number of API calls and ensures atomic operations.
  """
  print("Send and generate message called")
  
  try:
    # Verify ownership
    if not verify_conversation_ownership(request_body.conversationId, current_user['user_id'], current_user.get("is_guest", False)):
      response.status_code = status.HTTP_403_FORBIDDEN
      return ErrorResponse(error="Access denied to this conversation")
    
    # Step 1: Save the user message
    user_message_id = int(time.time() * 1000)
    
    # Extract content based on message type
    content_str = ""
    message_type = request_body.type
    
    if message_type == 'text':
      if isinstance(request_body.content, str):
        content_str = request_body.content
      elif isinstance(request_body.content, dict):
        content_str = request_body.content.get('content', '')
        attachments = request_body.content.get('attachments', [])
        if attachments:
          content_obj = {
            'content': content_str,
            'attachments': attachments
          }
          content_str = json.dumps(content_obj)
    elif message_type == 'voice':
      if isinstance(request_body.content, dict):
        content_str = json.dumps(request_body.content)
      else:
        content_str = str(request_body.content)
    
    # Save user message
    with get_db() as conn:
      cur = conn.cursor()
      cur.execute(
        """
        INSERT INTO messages (id, conversationId, roleName, content, time, type, version, lastModified)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (user_message_id, request_body.conversationId, request_body.roleName,
         content_str, request_body.time, message_type,
         request_body.version or 1, request_body.lastModified or int(time.time()))
      )
      conn.commit()
    
    user_message_response = MessageResponse(
      id=user_message_id,
      conversationId=request_body.conversationId,
      roleName=request_body.roleName,
      content=content_str if message_type == 'text' and isinstance(request_body.content, str) else request_body.content.get('content', '') if isinstance(request_body.content, dict) else content_str,
      time=request_body.time,
      type=message_type,
      version=request_body.version or 1,
      lastModified=request_body.lastModified or int(time.time())
    )
    
    # Step 2: Generate AI response if requested
    ai_message_response = None
    
    if request_body.generateResponse:
      # Get user settings
      user_id = current_user["user_id"]
      with get_db() as db:
        cur = db.cursor()
        cur.execute("""
                    SELECT model, temperature, top_p, systemPrompt,
                           darkMode, languageIsEnglish
                    FROM user_settings
                    WHERE user_id = ?
                    """, (user_id,))
        
        row = cur.fetchone()
        
        if row:
          db_settings = AppSettings(**dict(row))
        else:
          db_settings = AppSettings(
            model="openai/gpt-4o",
            temperature=0.5,
            top_p=0.5,
            systemPrompt="You are a helpful assistant!",
            darkMode=0,
            languageIsEnglish=0
          )
      
      # Use provided values or fall back to settings
      temperature = request_body.temperature if request_body.temperature is not None else db_settings.temperature
      top_p = request_body.top_p if request_body.top_p is not None else db_settings.top_p
      system_prompt = request_body.systemPrompt if request_body.systemPrompt is not None else db_settings.systemPrompt
      model = db_settings.model
      
      # Get conversation context including the just-sent message
      context = await get_conversation_context(request_body.conversationId, limit=6)  # Get one more to include new message
      
      # Generate AI response
      ai_response_content = await generate_llm_response(
        context,
        temperature,
        top_p,
        system_prompt,
        model
      )
      
      ai_message_id = int(time.time() * 1000) + 1  # Ensure different ID
      current_time = int(time.time())
      
      # Save AI message
      with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
          """
          INSERT INTO messages (id, conversationId, roleName, content, time, type, version, lastModified)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?)
          """,
          (ai_message_id, request_body.conversationId, request_body.aiParticipant,
           ai_response_content, current_time, 'text', 1, current_time)
        )
        conn.commit()
      
      ai_message_response = MessageResponse(
        id=ai_message_id,
        conversationId=request_body.conversationId,
        roleName=request_body.aiParticipant,
        content=ai_response_content,
        time=current_time,
        type='text',
        version=1,
        lastModified=current_time
      )
    
    return SendAndGenerateResponse(
      userMessage=user_message_response,
      aiMessage=ai_message_response
    )
    
  except Exception as e:
    print(f"Error in send_and_generate: {str(e)}")
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return ErrorResponse(error=str(e))


@app.post("/api/files/upload",
          response_model=List[str],
          status_code=status.HTTP_201_CREATED,
          responses={
            status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "No files provided"},
            # status.HTTP_413_PAYLOAD_TOO_LARGE: {"model": ErrorResponse, "description": "File too large"},
            # Does not work with the current version of starlette, use ENTITY_TOO_LARGE instead
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: {"model": ErrorResponse, "description": "File too large"},
            status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Internal server error"}
          },
          tags=["Files"])
async def upload_files(
  files: List[UploadFile] = File(...),
  current_user: dict = Depends(get_current_user)
):
  """
  Upload multiple files and save them to the ./files directory.
  Returns their IDs for later reference.
  """
  print(f"File upload called with {len(files)} files")

  try:
    if not files:
      raise HTTPException(status_code=400, detail="No files provided")

    file_ids = []
    max_file_size = 10 * 1024 * 1024  # 10MB limit per file
    files_dir = Path("./files")
    
    # Ensure files directory exists
    files_dir.mkdir(exist_ok=True)

    for file in files:
      # Read file to check size and content
      contents = await file.read()
      if len(contents) > max_file_size:
        raise HTTPException(status_code=413, detail=f"File {file.filename} exceeds maximum size of 10MB")

      # Generate a unique file ID and preserve original extension
      timestamp = int(time.time() * 1000)
      random_suffix = secrets.token_hex(8)
      file_id = f"file_{timestamp}_{random_suffix}"
      
      # Preserve file extension if present
      if file.filename and "." in file.filename:
        original_ext = Path(file.filename).suffix
        stored_filename = f"{file_id}{original_ext}"
      else:
        stored_filename = file_id
      
      # Save file to disk
      file_path = files_dir / stored_filename
      with open(file_path, "wb") as f:
        f.write(contents)
      
      file_ids.append(file_id)
      print(f"Uploaded file: {file.filename} -> {file_id} (size: {len(contents)} bytes) saved to {file_path}")

      # Reset file position (not needed after saving, but good practice)
      await file.seek(0)

    return file_ids

  except HTTPException:
    raise
  except Exception as e:
    print(f"Error uploading files: {str(e)}")
    raise HTTPException(status_code=500, detail="Error uploading files")


# CORS configuration
origins = [
  "http://localhost:4200",  # Angular default
  "http://localhost:8080",  # Common dev port
  "https://localhost:4200",
  "https://localhost:8080",
]

app.add_middleware(
  CORSMiddleware,
  allow_origins=origins,
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
  expose_headers=["X-CSRF-Token", "X-Has-More-Messages", "Content-Type", "Authorization"]
)


@app.middleware("http")
async def csrf_protection_middleware(request: Request, call_next):
  """
  Middleware to enforce CSRF protection on state-changing requests.
  """
  # Skip CSRF for OPTIONS requests (CORS preflight)
  if request.method == "OPTIONS":
    response = await call_next(request)
    return response
  
  # Validate CSRF token
  if not await validate_csrf_token(request):
    response = JSONResponse(
      content={"error": "CSRF validation failed"},
      status_code=403
    )
    # Add CORS headers to error response
    origin = request.headers.get("origin")
    if origin in origins:
      response.headers["Access-Control-Allow-Origin"] = origin
      response.headers["Access-Control-Allow-Credentials"] = "true"
    return response
  
  response = await call_next(request)
  return response


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
  """
  Middleware to add security headers to all responses.
  """
  response = await call_next(request)
  
  # Prevent MIME type sniffing
  response.headers["X-Content-Type-Options"] = "nosniff"
  
  # Prevent clickjacking
  response.headers["X-Frame-Options"] = "DENY"
  
  # Enable XSS filter (legacy but still useful for older browsers)
  response.headers["X-XSS-Protection"] = "1; mode=block"
  
  # Force HTTPS (only in production - not when using dev certs)
  if not os.getenv("USE_DEV_CERTS", "False").lower() == "true":
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
  
  # Content Security Policy
  # Note: 'unsafe-inline' and 'unsafe-eval' are required for Angular to work properly
  csp_directives = [
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' 'unsafe-eval'",  # unsafe-eval needed for Angular
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: blob:",
    "connect-src 'self' wss: https:",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'"
  ]
  response.headers["Content-Security-Policy"] = "; ".join(csp_directives)
  
  # Referrer Policy
  response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
  
  # Permissions Policy (formerly Feature Policy)
  # Disable access to sensitive browser features
  response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
  
  return response


# Development certificate setup
ssl_config = {}
if os.getenv("USE_DEV_CERTS") == "True":
  print("Starting in development mode with auto-generated certificates...")
  cert_file, key_file = setup_development_certificates()

  print(f"""
    [SSL] Development HTTPS certificates generated!

    To trust these certificates in development:
    1. Certificate Authority (CA) file: devcerts/ca.pem (import this into your browser/system)
    2. Server certificate file: {cert_file}
    3. You might need to add an exception in your browser for localhost.
    4. For Angular development, you might need to set NODE_TLS_REJECT_UNAUTHORIZED='0' in your environment.

    [WARNING] These are self-signed certificates for development only! Do not use in production.
    """)

  ssl_config = {
    "ssl_keyfile": key_file,
    "ssl_certfile": cert_file,
  }

# Main entry point for running the Uvicorn server
if __name__ == "__main__":
  import uvicorn

  host = os.getenv("HOST", "127.0.0.1")
  port = int(os.getenv("PORT", "8000"))

  run_args = {"host": host, "port": port, "reload": True}
  if ssl_config:
    run_args.update(ssl_config)
    print(f"[SERVER] Starting server at https://{host}:{port}")
    print(f"[API] OpenAPI schema available at: https://{host}:{port}{app.openapi_url}")
    print(f"[DOCS] Swagger UI available at: https://{host}:{port}/api/docs")
  else:
    print(f"[SERVER] Starting server at http://{host}:{port}")
    print(f"[API] OpenAPI schema available at: http://{host}:{port}{app.openapi_url}")
    print(f"[DOCS] Swagger UI available at: http://{host}:{port}/api/docs")

  current_script_name = Path(__file__).stem
  uvicorn.run(f"{current_script_name}:app", **run_args)
