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
from fastapi import FastAPI, Response, status, Request, HTTPException, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
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
  id: int
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
  conversationId: int
  roleName: str
  type: Literal["text", "voice"]
  content: Union[str, TextContent, VoiceContent]  # Backwards compatible - str for legacy, objects for new types
  time: int


class ApiMessageGenerate(BaseModel):
  """
  Represents a model for generating API messages.
  """
  conversationId: int
  roleName: str
  time: int
  temperature: Optional[float] = None
  top_p: Optional[float] = None
  systemPrompt: Optional[str] = None


class MessagePatch(BaseModel):
  """
  Represents a model for updating message data within a conversation.
  """
  id: int
  conversationId: int
  content: str


class MessageResponse(BaseModel):
  """
  Represents a response message within a conversation context.
  """
  id: int
  conversationId: int
  roleName: str
  content: str
  time: int
  type: Optional[str] = "text"  # Default to "text" for backwards compatibility


class ConversationResponse(BaseModel):
  """
  Encapsulates the response details of a conversation.
  """
  id: int
  hashsum: int

class Conversation(BaseModel):
  id: int
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


def create_session(user_id: int, user_email: str, session_duration_hours=24, is_guest=False) -> str:
  """
  Creates a session for a given user with a specified duration in hours.
  """
  session_key = generate_session_key()
  expires_at = datetime.now(UTC) + timedelta(hours=session_duration_hours)

  # Save session to database
  with get_db() as db:
    db.execute(
      """
      INSERT INTO sessions (session_key, user_id, email, expires_at, is_guest)
      VALUES (?, ?, ?, ?, ?)
      """, (session_key, user_id, user_email, expires_at.isoformat(), is_guest))

    db.commit()

  return session_key


def validate_session(session_key: str) -> Optional[dict]:
  """
  Validates a provided session key by checking the database.
  """
  if not session_key:
    return None

  with get_db() as conn:
    cur = conn.cursor()
    cur.execute(
      """
      SELECT user_id, email, expires_at, last_activity, is_guest
      FROM sessions
      WHERE session_key = ?
      """, (session_key,))
    result = cur.fetchone()

    if not result:
      return None

    expires_at = datetime.fromisoformat(result["expires_at"])
    if datetime.now(UTC) > expires_at:
      # Session expired, clean up
      cur.execute("DELETE FROM sessions WHERE session_key = ?", (session_key,))
      conn.commit()
      return None

    # Update last activity timestamp
    current_time = datetime.now(UTC)
    cur.execute("""
                UPDATE sessions
                SET last_activity = ?
                WHERE session_key = ?
                """, (current_time.isoformat(), session_key))
    conn.commit()

    return {
      "user_id": result["user_id"],
      "email": result["email"],
      "is_guest": result["is_guest"]
    }


def delete_session(session_key: str):
  """
  Deletes a session from the database.
  """
  with get_db() as conn:
    cur = conn.cursor()
    cur.execute("DELETE FROM sessions WHERE session_key = ?", (session_key,))
    conn.commit()


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

    # Create conversations table
    cur.execute('''
                CREATE TABLE IF NOT EXISTS conversations (
                                                           id INTEGER PRIMARY KEY,
                                                           userId INTEGER NOT NULL,
                                                           name TEXT NOT NULL,
                                                           participants TEXT,
                                                           createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                                           updatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                                           FOREIGN KEY(userId) REFERENCES users(id)
                )
                ''')

    # Create messages table to store chat messages
    cur.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                                                      id INTEGER PRIMARY KEY,
                                                      conversationId INTEGER NOT NULL,
                                                      roleName TEXT NOT NULL,
                                                      content TEXT NOT NULL,
                                                      time INTEGER NOT NULL,
                                                      type TEXT DEFAULT 'text',
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

    # Check if type column exists in messages table, if not add it
    cur.execute("PRAGMA table_info(messages)")
    columns = [column[1] for column in cur.fetchall()]
    if 'type' not in columns:
      print("Adding type column to messages table...")
      cur.execute("ALTER TABLE messages ADD COLUMN type TEXT DEFAULT 'text'")

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
                                                           languageIsEnglish INTEGER NOT NULL
                )
                ''')

    conn.commit()



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


async def get_conversation_context(conversation_id: int, limit: int = 5) -> str:
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


def verify_conversation_ownership(conversation_id: int, user_id: int, is_guest: bool = False) -> bool:
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
async def guest_login(request: GuestLoginRequest, response: Response):
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

  guest_email = f"guest_{secrets.token_hex(4)}@guest.com"
  guest_user = {"id": 0, "email": guest_email, "name": "Guest"}

  session_key = create_session(0, guest_email, is_guest=True)

  response.set_cookie(
    key="session",
    value=session_key,
    max_age=86400,  # 24 hours
    httponly=True,
    secure=True,
    samesite="lax",
    path="/"
  )

  return LoginResponse(
    user=guest_user,
    message="Guest login successful",
    token=session_key
  )

@app.post("/api/auth/mock-login", response_model=LoginResponse)
async def mock_login(request: MockLoginRequest, response: Response):
  """
  Handles a mock login process for a user with provided request data.
  """
  print(f"Login attempt for: {request.email}")

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

  # Create session with is_guest=False for regular users
  session_key = create_session(user_id, request.email, is_guest=False)

  # Set session cookie
  response.set_cookie(
    key="session",
    value=session_key,
    max_age=86400,  # 24 hours
    httponly=True,  # Prevents JS access
    secure=True,  # HTTPS only
    samesite="lax",
    path="/"
  )

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
  """
  session_key = request.cookies.get("session")
  if session_key:
    delete_session(session_key)

  # Delete cookie
  response.delete_cookie("session")
  return {"message": "Logged out successfully"}


@app.get("/api/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
  """
  Retrieves the details of the currently authenticated user.
  """
  return {"user": current_user}


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
        "SELECT id FROM conversations WHERE userId = ?",
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
        conversation_responses.append({'id': conversation_id, 'hashsum': hashsum})

      return conversation_responses

  except Exception as e:
    print(f"Error: {str(e)}")
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return ErrorResponse(error=str(e))


@app.get("/api/settings", response_model=AppSettings)
async def get_settings(current_user: dict = Depends(get_current_user)):
  user_id = current_user["user_id"]

  if current_user.get("is_guest"):
    return AppSettings(
      model="openai/gpt-4o",
      temperature=0.5,
      top_p=0.5,
      systemPrompt="You are a helpful assistant!",
      darkMode=0,
      languageIsEnglish=0
    )

  with get_db() as db:
    cur = db.cursor()
    cur.execute("""
                SELECT model, temperature, top_p, systemPrompt, darkMode, languageIsEnglish
                FROM user_settings
                WHERE user_id = ?
                """, (user_id,))
    row = cur.fetchone()

    if row:
      return AppSettings(**dict(row))
    else:
      # Fallback defaults if user has no settings yet
      return AppSettings(
        model="openai/gpt-4o",
        temperature=0.5,
        top_p=0.5,
        systemPrompt="You are a helpful assistant!",
        darkMode=0,
        languageIsEnglish=0
      )


@app.put("/api/settings")
async def update_settings(new_settings: AppSettings, current_user: dict = Depends(get_current_user)):
  user_id = current_user["user_id"]
  if current_user.get("is_guest"):
    raise HTTPException(status_code=403, detail="Guests cannot save settings.")

  with get_db() as db:
    cur = db.cursor()
    cur.execute("""
                INSERT INTO user_settings (user_id, model, temperature, top_p, systemPrompt, darkMode, languageIsEnglish)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                                                 model = excluded.model,
                                                 temperature = excluded.temperature,
                                                 top_p = excluded.top_p,
                                                 systemPrompt = excluded.systemPrompt,
                                                 darkMode = excluded.darkMode,
                                                 languageIsEnglish = excluded.languageIsEnglish
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
  return {"message": "Settings saved"}


@app.post("/api/conversation/create", response_model=Conversation, status_code=status.HTTP_201_CREATED, tags=["Conversation"])
async def create_conversation(req: ConversationCreateRequest, current_user: dict = Depends(get_current_user)):
  """
  Creates a new conversation for the authenticated user.
  """
  user_id = current_user['user_id']
  with get_db() as conn:
    cur = conn.cursor()
    participants_json = json.dumps(req.participants)
    cur.execute(
      "INSERT INTO conversations (userId, name, participants) VALUES (?, ?, ?)",
      (user_id, req.name, participants_json)
    )
    new_id = cur.lastrowid
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
  conversation_id: int,
  timestamp: int,
  messages_count: int,
  response: Response,
  current_user: dict = Depends(get_current_user)
):
  """
  Get messages for a specific conversation, before a given timestamp.
  """
  print("Get conversation messages called")

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
      cur.execute(
        """
        SELECT id, conversationId, roleName, content, time, type
        FROM messages
        WHERE conversationId = ? AND time < ?
        ORDER BY time DESC LIMIT ?
        """,
        (conversation_id, timestamp, min(messages_count, 30))
      )
      messages_rows = cur.fetchall()

      if messages_rows:
        messages_data = [dict(msg) for msg in messages_rows]
        messages_data.reverse()  # Reverse to get chronological order

        if messages_count > 30 and len(messages_data) == 30:
          response.status_code = status.HTTP_206_PARTIAL_CONTENT
        else:
          response.status_code = status.HTTP_200_OK
        return messages_data
      else:
        response.status_code = status.HTTP_204_NO_CONTENT
        return None

  except Exception as e:
    print(f"Error: {str(e)}")
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return ErrorResponse(error=str(e))


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
        INSERT INTO messages (id, conversationId, roleName, content, time, type)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (message_id, request_body.conversationId, request_body.roleName,
         content_str, request_body.time, message_type)
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
      'time': current_time
    }

    with get_db() as conn:
      cur = conn.cursor()
      cur.execute(
        """
        INSERT INTO messages (id, conversationId, roleName, content, time, type)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (message_id, request_body.conversationId, request_body.roleName,
         message_doc_data['content'], current_time, 'text')
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
      cur.execute(
        """
        UPDATE messages
        SET content = ?
        WHERE id = ? AND conversationId = ?
        """,
        (request_body.content, request_body.id, request_body.conversationId)
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


@app.delete("/api/message/delete/{conversation_id}/{message_id}",
            status_code=status.HTTP_204_NO_CONTENT,
            responses={
              status.HTTP_400_BAD_REQUEST: {"description": "Conversation ID or Message ID missing"},
              status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Access denied"},
              status.HTTP_404_NOT_FOUND: {"description": "Message not found"},
              status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Internal server error"}
            },
            tags=["Message"])
async def delete_message(conversation_id: int, message_id: int, response: Response,
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
  Upload multiple files and return their IDs.
  For now, this is a mock implementation that returns generated IDs.
  In a real implementation, files would be stored in object storage (S3, etc.)
  """
  print(f"File upload called with {len(files)} files")

  try:
    if not files:
      raise HTTPException(status_code=400, detail="No files provided")

    file_ids = []
    max_file_size = 10 * 1024 * 1024  # 10MB limit per file

    for file in files:
      # Read file to check size (in real implementation, would stream to storage)
      contents = await file.read()
      if len(contents) > max_file_size:
        raise HTTPException(status_code=413, detail=f"File {file.filename} exceeds maximum size of 10MB")

      # Generate a unique file ID
      # In real implementation, this would be the ID from object storage
      file_id = f"file_{int(time.time() * 1000)}_{secrets.token_hex(8)}"
      file_ids.append(file_id)

      print(f"Mock uploaded file: {file.filename} -> {file_id} (size: {len(contents)} bytes)")

      # Reset file position
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
  expose_headers=["*"]
)

# Development certificate setup
ssl_config = {}
if os.getenv("USE_DEV_CERTS") == "True":
  print("Starting in development mode with auto-generated certificates...")
  cert_file, key_file = setup_development_certificates()

  print(f"""
    🔐 Development HTTPS certificates generated!

    To trust these certificates in development:
    1. Certificate Authority (CA) file: devcerts/ca.pem (import this into your browser/system)
    2. Server certificate file: {cert_file}
    3. You might need to add an exception in your browser for localhost.
    4. For Angular development, you might need to set NODE_TLS_REJECT_UNAUTHORIZED='0' in your environment.

    ⚠️  These are self-signed certificates for development only! Do not use in production.
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
    print(f"🚀 Starting server at https://{host}:{port}")
    print(f"📄 OpenAPI schema available at: https://{host}:{port}{app.openapi_url}")
    print(f"📚 Swagger UI available at: https://{host}:{port}/api/docs")
  else:
    print(f"🚀 Starting server at http://{host}:{port}")
    print(f"📄 OpenAPI schema available at: http://{host}:{port}{app.openapi_url}")
    print(f"📚 Swagger UI available at: http://{host}:{port}/api/docs")

  current_script_name = Path(__file__).stem
  uvicorn.run(f"{current_script_name}:app", **run_args)
