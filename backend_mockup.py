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
import replicate  # type: ignore
import json  # For storing participants list
import secrets
import hashlib
from datetime import datetime, timedelta
from fastapi import FastAPI, Response, status, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel
from typing import List, Dict, Optional  # Added Optional
from dotenv import load_dotenv, find_dotenv
from pathlib import Path
from contextlib import contextmanager


# --- Hardcoded Credentials ---
HARDCODED_USERNAME = "admin"
HARDCODED_PASSWORD = "password123"  # In production, use environment variables
HARDCODED_USER_ID = 777
HARDCODED_USER_NAME = "Backend User"
HARDCODED_USER_EMAIL = "backend.user@example.com"

# --- Pydantic Models ---
class LoginRequest(BaseModel):
  username: str
  password: str


class ErrorResponse(BaseModel):
  error: str


class UserDetails(BaseModel):
  id: int
  name: str
  email: str


class SessionInfoResponse(BaseModel):
  user: UserDetails
  token: str


# Model for creating a new conversation, used if conversationId is null in ApiMessageSend
class ConversationCreateData(BaseModel):
  userId: int
  name: str = "New Conversation"
  participants: List[str] = ["user", "Assistant"]


class ApiMessageSend(BaseModel):
  conversationId: Optional[int] = None  # Can be null for new conversations
  roleName: str
  content: str
  time: int  # Timestamp in seconds
  # Optional: Include data to create a conversation if conversationId is null
  # These fields will be used by the backend if conversationId is None
  # The userId can also be derived from the authenticated session token in a real app
  newConversationData: Optional[ConversationCreateData] = None


class ApiMessageGenerate(BaseModel):
  conversationId: int
  roleName: str  # Typically 'Assistant' or the AI's name
  time: int  # Not strictly needed for generation, but kept for consistency if API requires it


class MessagePatch(BaseModel):
  id: int
  conversationId: int
  content: str


class MessageResponse(BaseModel):
  id: int
  conversationId: int
  roleName: str
  content: str
  time: int  # Timestamp in seconds


class ConversationResponse(BaseModel):
  id: int
  hashsum: int
  userId: int
  name: str
  participants: List[str]


# Response model for the send message endpoint
class SendMessageApiResponse(BaseModel):
  message: MessageResponse
  conversation: Optional[ConversationResponse] = None  # Populated if a new conversation was created


# --- Database Setup ---
@contextmanager
def get_db():
  conn = sqlite3.connect('chat.db')
  conn.row_factory = sqlite3.Row
  try:
    yield conn
  finally:
    conn.close()


def init_db():
  with get_db() as conn:
    cur = conn.cursor()
    # Conversations table
    cur.execute('''
                CREATE TABLE IF NOT EXISTS conversations
                (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  userId INTEGER NOT NULL,
                  name TEXT NOT NULL,
                  participants TEXT NOT NULL, -- Store as JSON string
                  hashsum INTEGER
                )
                ''')
    # Messages table
    cur.execute('''
                CREATE TABLE IF NOT EXISTS messages
                (
                  id INTEGER PRIMARY KEY,  -- Using client-generated timestamp for ID initially
                  conversationId INTEGER NOT NULL,
                  roleName TEXT NOT NULL,
                  content TEXT NOT NULL,
                  time INTEGER NOT NULL, -- Unix timestamp in seconds
                  FOREIGN KEY (conversationId) REFERENCES conversations (id)
                  )
                ''')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_conversation_time ON messages(conversationId, time)')

    # Sessions table
    cur.execute('''
                CREATE TABLE IF NOT EXISTS sessions
                (
                  token TEXT PRIMARY KEY,
                  user_id INTEGER NOT NULL,
                  expires_at TIMESTAMP NOT NULL,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                ''')
    conn.commit()


def generate_hash(messages: List[sqlite3.Row]) -> int:
  if not messages:
    return 0
  hash_value = 0
  for message in messages:
    content = message['content']
    if not content:
      continue
    hash_value += ord(content[0]) + ord(content[-1]) + len(content)
  return hash_value % (2 ** 32)


# --- Session Management ---
def generate_session_token() -> str:
  """Generate a secure random session token."""
  return secrets.token_urlsafe(32)


def create_session(user_id: int) -> str:
  """Create a new session for the user."""
  token = generate_session_token()
  expires_at = datetime.now() + timedelta(hours=1)  # 1 hour validity

  with get_db() as conn:
    cur = conn.cursor()
    # Remove any existing sessions for this user
    cur.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    # Create new session
    cur.execute(
      "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
      (token, user_id, expires_at.isoformat())
    )
    conn.commit()

  return token


def validate_session_token(token: str) -> Optional[int]:
  """Validate session token and return user_id if valid."""
  if not token:
    return None

  with get_db() as conn:
    cur = conn.cursor()
    cur.execute(
      "SELECT user_id, expires_at FROM sessions WHERE token = ?",
      (token,)
    )
    result = cur.fetchone()

    if not result:
      return None

    user_id = result['user_id']
    expires_at = datetime.fromisoformat(result['expires_at'])

    # Check if expired
    if expires_at < datetime.now():
      # Clean up expired session
      cur.execute("DELETE FROM sessions WHERE token = ?", (token,))
      conn.commit()
      return None

    # Update expiry time (sliding window - resets to 1 hour on each valid request)
    new_expires_at = datetime.now() + timedelta(hours=1)
    cur.execute(
      "UPDATE sessions SET expires_at = ? WHERE token = ?",
      (new_expires_at.isoformat(), token)
    )
    conn.commit()

    return user_id


async def get_current_user(request: Request) -> int:
  """Dependency to get current user from session token."""
  auth_header = request.headers.get("Authorization")
  if not auth_header or not auth_header.startswith("Bearer "):
    raise HTTPException(status_code=401, detail="Not authenticated")

  token = auth_header.split(" ")[1]
  user_id = validate_session_token(token)

  if not user_id:
    raise HTTPException(status_code=401, detail="Invalid or expired session")

  return user_id


# --- LLM Interaction (Replicate) ---
async def generate_llm_response(prompt: str) -> str:
  try:
    output_generator = replicate.run(
      "meta/meta-llama-3-8b-instruct",
      input={
        "prompt": prompt,
        "temperature": 0.6,
        "top_p": 0.9,
        "max_tokens": 1024,  # Reduced for faster mockup responses
        "system_prompt": "You are a helpful AI assistant. Keep your responses concise for this chat application."
      }
    )
    # The output from replicate.run for streaming models is a generator
    response_parts = []
    for item in output_generator:
      response_parts.append(item)
    return "".join(response_parts)

  except Exception as e:
    print(f"Error generating LLM response: {str(e)}")
    return "I apologize, but I encountered an error generating a response."


async def get_conversation_context(conversation_id: int, limit: int = 5) -> str:
  try:
    with get_db() as conn:
      cur = conn.cursor()
      cur.execute(
        "SELECT roleName, content FROM messages WHERE conversationId = ? ORDER BY time DESC LIMIT ?",
        (conversation_id, limit)
      )
      messages = cur.fetchall()
      context_parts = [f"{msg['roleName']}: {msg['content']}" for msg in reversed(messages)]
      return "\n".join(context_parts)
  except Exception as e:
    print(f"Error getting conversation context: {str(e)}")
    return ""


# --- FastAPI App Setup ---
load_dotenv(find_dotenv())
app = FastAPI(
  title="Chat API Mockup",
  version="1.2.0",
  description="Mockup backend for a chat application with session authentication.",
  docs_url=None,
  redoc_url=None,
  openapi_url="/api/openapi.json"
)
init_db()  # Initialize DB on startup


@app.get(app.openapi_url, include_in_schema=False)
async def custom_openapi():
  return get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)


@app.get("/api/docs", include_in_schema=False)
async def custom_swagger_ui_html(req: Request):
  root_path = req.scope.get("root_path", "").rstrip("/")
  return get_swagger_ui_html(openapi_url=root_path + app.openapi_url, title=app.title + " - Swagger UI")


# --- API Endpoints ---
@app.post("/api/auth/login", response_model=SessionInfoResponse, tags=["Authentication"])
async def login(request_body: LoginRequest, response: Response):
  """Login endpoint with hardcoded credentials."""
  print(f"Login attempt for user: {request_body.username}")

  # Check hardcoded credentials
  if request_body.username != HARDCODED_USERNAME or request_body.password != HARDCODED_PASSWORD:
    response.status_code = status.HTTP_401_UNAUTHORIZED
    return ErrorResponse(error="Invalid username or password")

  # Create session
  token = create_session(HARDCODED_USER_ID)

  user_details = UserDetails(
    id=HARDCODED_USER_ID,
    name=HARDCODED_USER_NAME,
    email=HARDCODED_USER_EMAIL
  )

  return SessionInfoResponse(user=user_details, token=token)


@app.post("/api/auth/logout", tags=["Authentication"])
async def logout(user_id: int = Depends(get_current_user)):
  """Logout endpoint - invalidates the session."""
  print(f"Logout request for user: {user_id}")

  with get_db() as conn:
    cur = conn.cursor()
    cur.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.commit()

  return {"message": "Logged out successfully"}


@app.get("/api/auth/session-info", response_model=SessionInfoResponse, tags=["Authentication"])
async def get_session_info(user_id: int = Depends(get_current_user)):
  """Get current session info - requires valid session token."""
  print("Auth session-info called for user:", user_id)

  user_details = UserDetails(
    id=HARDCODED_USER_ID,
    name=HARDCODED_USER_NAME,
    email=HARDCODED_USER_EMAIL
  )

  # Get the current token from request (for response consistency)
  # In a real app, you might not want to return the token here
  return SessionInfoResponse(user=user_details, token="[REDACTED]")


@app.get("/api/conversation/byuserid/{user_id}", response_model=List[ConversationResponse], tags=["Conversation"])
async def get_conversations_by_user_id(
  user_id: int,
  response: Response,
  current_user_id: int = Depends(get_current_user)
):
  print(f"Get conversations called for user_id: {user_id}")

  # Check if user is requesting their own conversations
  if user_id != current_user_id:
    response.status_code = status.HTTP_403_FORBIDDEN
    return ErrorResponse(error="Cannot access other user's conversations")

  try:
    with get_db() as conn:
      cur = conn.cursor()
      cur.execute("SELECT id, userId, name, participants FROM conversations WHERE userId = ?", (user_id,))
      db_conversations = cur.fetchall()

      if not db_conversations:
        response.status_code = status.HTTP_204_NO_CONTENT
        return []

      result_conversations = []
      for conv_row in db_conversations:
        cur.execute("SELECT content FROM messages WHERE conversationId = ? ORDER BY time", (conv_row["id"],))
        messages_for_hash = cur.fetchall()
        hashsum = generate_hash(messages_for_hash)

        result_conversations.append(
          ConversationResponse(
            id=conv_row["id"],
            userId=conv_row["userId"],
            name=conv_row["name"],
            participants=json.loads(conv_row["participants"]),
            hashsum=hashsum
          )
        )
    return result_conversations
  except Exception as e:
    print(f"Error in get_conversations_by_user_id: {str(e)}")
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return ErrorResponse(error=f"Internal server error: {str(e)}")


@app.get("/api/conversation/messages/{conversation_id}/{timestamp}/{messages_count}",
         response_model=List[MessageResponse], tags=["Conversation"])
async def get_conversation_messages(
  conversation_id: int,
  timestamp: int,
  messages_count: int,
  response: Response,
  current_user_id: int = Depends(get_current_user)
):
  print(f"Get messages for conv_id: {conversation_id}, before_time: {timestamp}, count: {messages_count}")

  # Verify user owns this conversation
  try:
    with get_db() as conn:
      cur = conn.cursor()
      cur.execute("SELECT userId FROM conversations WHERE id = ?", (conversation_id,))
      conv_row = cur.fetchone()

      if not conv_row:
        response.status_code = status.HTTP_404_NOT_FOUND
        return ErrorResponse(error="Conversation not found")

      if conv_row['userId'] != current_user_id:
        response.status_code = status.HTTP_403_FORBIDDEN
        return ErrorResponse(error="Cannot access this conversation")

      cur.execute(
        "SELECT id, conversationId, roleName, content, time FROM messages WHERE conversationId = ? AND time < ? ORDER BY time DESC LIMIT ?",
        (conversation_id, timestamp, min(messages_count, 50))
      )
      messages_rows = cur.fetchall()
      if messages_rows:
        return [dict(msg) for msg in reversed(messages_rows)]
      else:
        response.status_code = status.HTTP_204_NO_CONTENT
        return []
  except Exception as e:
    print(f"Error in get_conversation_messages: {str(e)}")
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return ErrorResponse(error=str(e))


@app.post("/api/message/send", response_model=SendMessageApiResponse, status_code=status.HTTP_201_CREATED,
          tags=["Message"])
async def user_send_message(
  request_body: ApiMessageSend,
  response: Response,
  current_user_id: int = Depends(get_current_user)
):
  print(f"Message send called with: {request_body.model_dump_json(indent=2)}")
  try:
    if not request_body.content:
      response.status_code = status.HTTP_400_BAD_REQUEST
      return ErrorResponse(error="Message content cannot be empty")

    message_id = int(time.time() * 1000)
    actual_conversation_id = request_body.conversationId
    created_conversation_response: Optional[ConversationResponse] = None

    with get_db() as conn:
      cur = conn.cursor()

      # If conversationId is None, create a new conversation
      if actual_conversation_id is None:
        if not request_body.newConversationData:
          # Use current user's ID for new conversation
          conv_data = ConversationCreateData(
            userId=current_user_id,
            name=f"Chat with {HARDCODED_USER_NAME}",
            participants=["user", "Assistant"]
          )
        else:
          conv_data = request_body.newConversationData
          # Override userId with authenticated user's ID for security
          conv_data.userId = current_user_id

        cur.execute(
          "INSERT INTO conversations (userId, name, participants) VALUES (?, ?, ?)",
          (conv_data.userId, conv_data.name, json.dumps(conv_data.participants))
        )
        actual_conversation_id = cur.lastrowid
        conn.commit()
        print(f"New conversation created with ID: {actual_conversation_id} for user {conv_data.userId}")

        cur.execute("SELECT id, userId, name, participants FROM conversations WHERE id = ?", (actual_conversation_id,))
        new_conv_row = cur.fetchone()
        if new_conv_row:
          created_conversation_response = ConversationResponse(
            id=new_conv_row["id"],
            userId=new_conv_row["userId"],
            name=new_conv_row["name"],
            participants=json.loads(new_conv_row["participants"]),
            hashsum=0
          )
      else:
        # Verify user owns this conversation
        cur.execute("SELECT userId FROM conversations WHERE id = ?", (actual_conversation_id,))
        conv_row = cur.fetchone()
        if not conv_row or conv_row['userId'] != current_user_id:
          response.status_code = status.HTTP_403_FORBIDDEN
          return ErrorResponse(error="Cannot send message to this conversation")

      # Insert the message
      cur.execute(
        "INSERT INTO messages (id, conversationId, roleName, content, time) VALUES (?, ?, ?, ?, ?)",
        (message_id, actual_conversation_id, request_body.roleName, request_body.content, request_body.time)
      )
      conn.commit()

      if created_conversation_response and actual_conversation_id:
        cur.execute("SELECT content FROM messages WHERE conversationId = ? ORDER BY time", (actual_conversation_id,))
        messages_for_hash = cur.fetchall()
        new_hash = generate_hash(messages_for_hash)
        created_conversation_response.hashsum = new_hash

    message_response = MessageResponse(
      id=message_id,
      conversationId=actual_conversation_id,
      roleName=request_body.roleName,
      content=request_body.content,
      time=request_body.time
    )

    return SendMessageApiResponse(message=message_response, conversation=created_conversation_response)

  except sqlite3.IntegrityError as e:
    print(f"Database integrity error: {str(e)}")
    response.status_code = status.HTTP_400_BAD_REQUEST
    return ErrorResponse(error=f"Invalid request leading to database error: {str(e)}")
  except Exception as e:
    print(f"Error in user_send_message: {str(e)}")
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return ErrorResponse(error=f"Internal server error: {str(e)}")


@app.post("/api/message/generate", response_model=MessageResponse, status_code=status.HTTP_201_CREATED,
          tags=["Message"])
async def generate_ai_message(
  request_body: ApiMessageGenerate,
  response: Response,
  current_user_id: int = Depends(get_current_user)
):
  print(f"Generate AI message called for conv_id: {request_body.conversationId}")
  try:
    if request_body.conversationId is None:
      response.status_code = status.HTTP_400_BAD_REQUEST
      return ErrorResponse(error="Conversation ID is required for generating a message.")

    # Verify user owns this conversation
    with get_db() as conn:
      cur = conn.cursor()
      cur.execute("SELECT userId FROM conversations WHERE id = ?", (request_body.conversationId,))
      conv_row = cur.fetchone()
      if not conv_row or conv_row['userId'] != current_user_id:
        response.status_code = status.HTTP_403_FORBIDDEN
        return ErrorResponse(error="Cannot generate message for this conversation")

    context = await get_conversation_context(request_body.conversationId)
    if not context:
      context = "Hello, let's start a new conversation."
      print(f"No context for conv {request_body.conversationId}, using default prompt.")

    ai_response_content = await generate_llm_response(context)
    message_id = int(time.time() * 1000)
    current_time_seconds = int(time.time())

    with get_db() as conn:
      cur = conn.cursor()
      cur.execute(
        "INSERT INTO messages (id, conversationId, roleName, content, time) VALUES (?, ?, ?, ?, ?)",
        (message_id, request_body.conversationId, request_body.roleName, ai_response_content, current_time_seconds)
      )
      conn.commit()

    return MessageResponse(
      id=message_id,
      conversationId=request_body.conversationId,
      roleName=request_body.roleName,
      content=ai_response_content,
      time=current_time_seconds
    )
  except Exception as e:
    print(f"Error in generate_ai_message: {str(e)}")
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return ErrorResponse(error=str(e))


@app.patch("/api/message/patch", response_model=MessageResponse, tags=["Message"])
async def patch_message(
  request_body: MessagePatch,
  response: Response,
  current_user_id: int = Depends(get_current_user)
):
  print(f"Patch message called: {request_body}")
  try:
    with get_db() as conn:
      cur = conn.cursor()

      # Verify user owns the conversation containing this message
      cur.execute("""
                  SELECT c.userId FROM messages m
                                         JOIN conversations c ON m.conversationId = c.id
                  WHERE m.id = ? AND m.conversationId = ?
                  """, (request_body.id, request_body.conversationId))
      result = cur.fetchone()

      if not result or result['userId'] != current_user_id:
        response.status_code = status.HTTP_403_FORBIDDEN
        return ErrorResponse(error="Cannot modify this message")

      cur.execute(
        "UPDATE messages SET content = ? WHERE id = ? AND conversationId = ?",
        (request_body.content, request_body.id, request_body.conversationId)
      )
      conn.commit()

      if cur.rowcount == 0:
        response.status_code = status.HTTP_404_NOT_FOUND
        return ErrorResponse(error="Message not found or not updated.")

      cur.execute("SELECT id, conversationId, roleName, content, time FROM messages WHERE id = ?", (request_body.id,))
      updated_msg_row = cur.fetchone()
      if updated_msg_row:
        return dict(updated_msg_row)
      else:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return ErrorResponse(error="Failed to retrieve updated message after patch.")

  except Exception as e:
    print(f"Error in patch_message: {str(e)}")
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return ErrorResponse(error=str(e))


@app.delete("/api/message/delete/{conversation_id}/{message_id}", status_code=status.HTTP_204_NO_CONTENT,
            tags=["Message"])
async def delete_message(
  conversation_id: int,
  message_id: int,
  response: Response,
  current_user_id: int = Depends(get_current_user)
):
  print(f"Delete message called for conv_id: {conversation_id}, msg_id: {message_id}")
  try:
    with get_db() as conn:
      cur = conn.cursor()

      # Verify user owns this conversation
      cur.execute("SELECT userId FROM conversations WHERE id = ?", (conversation_id,))
      conv_row = cur.fetchone()
      if not conv_row or conv_row['userId'] != current_user_id:
        response.status_code = status.HTTP_403_FORBIDDEN
        return ErrorResponse(error="Cannot delete message from this conversation")

      cur.execute("DELETE FROM messages WHERE conversationId = ? AND id = ?", (conversation_id, message_id))
      conn.commit()
      if cur.rowcount == 0:
        response.status_code = status.HTTP_404_NOT_FOUND
        return ErrorResponse(error="Message not found.")
    return None
  except Exception as e:
    print(f"Error in delete_message: {str(e)}")
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return ErrorResponse(error=str(e))


# --- Certificate Setup ---
def setup_development_certificates():
  """Generate self-signed certificates for HTTPS in development."""
  cert_dir = Path("devcerts")
  cert_dir.mkdir(exist_ok=True)

  cert_file = cert_dir / "server.pem"
  key_file = cert_dir / "server.key"

  # Check if certificates already exist
  if cert_file.exists() and key_file.exists():
    print("Using existing development certificates...")
    return str(cert_file), str(key_file)

  print("Generating new self-signed certificates for development...")

  # Create a certificate authority
  ca = trustme.CA()

  # Issue a certificate for localhost and common variations
  server_cert = ca.issue_cert(
    "localhost",
    "127.0.0.1",
    "::1",
    "localhost.localdomain",
  )

  # Save the certificate and private key
  with open(cert_file, "w") as f:
    f.write(server_cert.cert_chain_pems[0].bytes().decode())

  with open(key_file, "w") as f:
    f.write(server_cert.private_key_pem.bytes().decode())

  print(f"Certificates generated in {cert_dir}/")
  print("You'll need to accept the security warning in your browser when accessing https://localhost:8443")

  return str(cert_file), str(key_file)


# --- CORS and Server Run ---
origins = ["http://localhost:4200", "http://localhost:8080", "https://localhost:4200", "https://localhost:8080"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"],
                   allow_headers=["*"])

ssl_config_dict = {}
if os.getenv("USE_DEV_CERTS") == "True":
  print("Starting in development mode with auto-generated certificates...")
  cert_file, key_file = setup_development_certificates()
  ssl_config_dict = {"ssl_keyfile": key_file, "ssl_certfile": cert_file}

if __name__ == "__main__":
  import uvicorn

  host = os.getenv("HOST", "127.0.0.1")
  port = int(os.getenv("PORT", "8443"))
  run_args = {"host": host, "port": port, "reload": True}
  if ssl_config_dict:
    run_args.update(ssl_config_dict)  # type: ignore

  current_script_name = Path(__file__).stem
  print(f"🚀 Starting Uvicorn server: {current_script_name}:app at http{'s' if ssl_config_dict else ''}://{host}:{port}")
  uvicorn.run(f"{current_script_name}:app", **run_args)  # type: ignore
