"""
This is a mockup of a backend server for a chat application.
It provides a simple API for sending and receiving messages in a conversation.
The server uses SQLite as a database to store messages and conversation data.
The server also uses Replicate to generate AI responses to messages in a conversation.
"""
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import List  # Added Dict

import replicate
import trustme
from dotenv import load_dotenv, find_dotenv
from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


# Error response model
class ErrorResponse(BaseModel):
  error: str


# Pydantic models for request validation
class ConversationState(BaseModel):
  id: int
  hashsum: int


class ApiConversationsCheck(BaseModel):
  conversations: List[ConversationState]


class ApiMessageSend(BaseModel):
  conversationId: int
  roleName: str
  content: str
  time: int


class ApiMessageGenerate(BaseModel):
  conversationId: int
  roleName: str
  time: int


class MessagePatch(BaseModel):
  id: int
  conversationId: int
  content: str


# --- Start: Added for hardcoded session ---
class UserDetails(BaseModel):
  id: int
  name: str
  email: str


class SessionInfoResponse(BaseModel):
  user: UserDetails
  token: str


# Hardcoded user and session token
HARDCODED_USER_ID = 777
HARDCODED_USER_NAME = "Backend User"
HARDCODED_USER_EMAIL = "backend.user@example.com"
HARDCODED_SESSION_TOKEN = "hardcoded-backend-session-token-12345"


# --- End: Added for hardcoded session ---


# Database connection management
@contextmanager
def get_db():
  conn = sqlite3.connect('chat.db')
  conn.row_factory = sqlite3.Row  # This enables dictionary-like access to rows
  try:
    yield conn
  finally:
    conn.close()


# Initialize database and create tables
def init_db():
  with get_db() as conn:
    cur = conn.cursor()

    # Create messages table
    cur.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                                                      id INTEGER PRIMARY KEY,
                                                      conversationId INTEGER NOT NULL,
                                                      roleName TEXT NOT NULL,
                                                      content TEXT NOT NULL,
                                                      time INTEGER NOT NULL
                )
                ''')

    # Create index for faster querying
    cur.execute('''
                CREATE INDEX IF NOT EXISTS idx_conversation_time
                  ON messages(conversationId, time)
                ''')

    conn.commit()


# Generate and save development certificates using trustme
def setup_development_certificates():
  ca = trustme.CA()
  server_cert = ca.issue_cert("localhost")
  cert_dir = Path("devcerts")
  cert_dir.mkdir(exist_ok=True)

  server_cert.private_key_and_cert_chain_pem.write_to_path(cert_dir / "server.pem")
  server_cert.private_key_pem.write_to_path(cert_dir / "server.key")
  ca.cert_pem.write_to_path(cert_dir / "ca.pem")

  return str(cert_dir / "server.pem"), str(cert_dir / "server.key")


# Generate a hashsum from the conversation messages
def generate_hash(messages: List[sqlite3.Row]) -> int:
  """
  Custom hashsum generator for checking the integrity of a conversation.
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


# Generate a response using Replicate's API
async def generate_llm_response(prompt: str) -> str:
  try:
    # Use Meta's Llama model through Replicate
    output = replicate.run(
      "meta/meta-llama-3-8b-instruct",
      input={
        "prompt": prompt,
        "temperature": 0.6,
        "top_p": 0.9,
        "max_tokens": 1024,
        "system_prompt": "You are a helpful AI assistant engaged in a natural conversation."
      }
    )

    # Replicate returns a generator, collect all tokens
    return "".join(output)
  except Exception as e:
    print(f"Error generating response: {str(e)}")
    return "I apologize, but I encountered an error generating a response."


# Get conversation context
async def get_conversation_context(conversation_id: int, limit: int = 5) -> str:
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

      # Build context string
      context = []
      for msg in reversed(messages):
        context.append(f"{msg['roleName']}: {msg['content']}")

      return "\n".join(context)
  except Exception as e:
    print(f"Error getting conversation context: {str(e)}")
    return ""


# Load environment variables
load_dotenv(find_dotenv())

# Setup FastAPI app
app = FastAPI()

# Initialize the database on startup
init_db()


# API endpoints

# --- Start: Added for hardcoded session ---
@app.get("/api/auth/session-info", response_model=SessionInfoResponse)
async def get_session_info():
  print("Auth session-info called")
  user_details = UserDetails(
    id=HARDCODED_USER_ID,
    name=HARDCODED_USER_NAME,
    email=HARDCODED_USER_EMAIL
  )
  return SessionInfoResponse(user=user_details, token=HARDCODED_SESSION_TOKEN)


# --- End: Added for hardcoded session ---


@app.get("/api/conversation/byuserid/{user_id}")
async def get_conversations(user_id: int, response: Response, status_code=status.HTTP_200_OK):
  print("Get conversations called for user_id:", user_id)

  try:
    with get_db() as conn:
      cur = conn.cursor()
      # This still fetches messages for a hardcoded conversationId = 1.
      # For a real multi-user system, you'd query a 'conversations' table by user_id.
      # And then perhaps iterate or join to get messages for those conversations.
      # The current logic is just for conversationId = 1 as per original.
      cur.execute(
        "SELECT * FROM messages WHERE conversationId = ?",
        (1,)  # Hardcoded to conversation 1.
      )
      messages = cur.fetchall()

      print(f"Messages found for conversationId=1: {len(messages)}")
      hashsum = generate_hash(messages)

      if not messages:
        print(f"No messages found for conversationId=1, hashsum: {hashsum}. Returning 204.")
        response.status_code = status.HTTP_204_NO_CONTENT
        return None  # Important: Return None for 204, not an empty list or dict if no content.

      # This simulates returning a list of conversations, but only contains one entry for conversationId=1.
      # In a real scenario, you would query a 'conversations' table for user_id
      # and then for each conversation, calculate its hashsum.
      return [{'id': 1, 'hashsum': hashsum, 'userId': user_id, 'name': f'Chat for User {user_id}',
               'participants': ['user', 'Assistant']}]


  except Exception as e:
    print(f"Error in get_conversations: {str(e)}")
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return ErrorResponse(error=str(e))


@app.get("/api/conversation/messages/{conversation_id}/{timestamp}/{messages_count}")
async def get_conversation_messages(
  conversation_id: int,
  timestamp: int,
  messages_count: int,
  response: Response,
  status_code=status.HTTP_200_OK  # Default status code
):
  print(
    f"Get conversation messages called for conv_id: {conversation_id}, timestamp: {timestamp}, count: {messages_count}")

  try:
    if not conversation_id or timestamp is None:  # timestamp can be 0, so check explicitly for None
      response.status_code = status.HTTP_400_BAD_REQUEST
      return ErrorResponse(error="Conversation ID and latest timestamp are required")

    with get_db() as conn:
      cur = conn.cursor()
      cur.execute(
        """
        SELECT * FROM messages
        WHERE conversationId = ? AND time < ?
        ORDER BY time DESC LIMIT ?
        """,
        (conversation_id, timestamp, min(messages_count, 30))
      )
      messages_rows = cur.fetchall()  # Renamed to avoid conflict

      if messages_rows:
        messages_data = [dict(msg) for msg in messages_rows]  # Renamed to avoid conflict
        messages_data.reverse()  # Reverse to get chronological order

        if messages_count > 30 and len(messages_data) == 30:
          response.status_code = status.HTTP_206_PARTIAL_CONTENT
        else:
          response.status_code = status.HTTP_200_OK
        return messages_data  # Return the list of dicts
      else:
        response.status_code = status.HTTP_204_NO_CONTENT
        return None  # Return None for 204

  except Exception as e:
    print(f"Error in get_conversation_messages: {str(e)}")  # Enhanced logging
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return ErrorResponse(error=str(e))


@app.post("/api/message/send")
async def user_send_message(request: ApiMessageSend, response: Response):  # Removed default status_code
  print(f"Message send called with: {request}")

  try:
    if not request.content:
      response.status_code = status.HTTP_400_BAD_REQUEST
      return ErrorResponse(error="Message content cannot be empty")

    message_id = int(time.time() * 1000)  # Consider a more robust ID generation for production

    with get_db() as conn:
      cur = conn.cursor()
      cur.execute(
        """
        INSERT INTO messages (id, conversationId, roleName, content, time)
        VALUES (?, ?, ?, ?, ?)
        """,
        (message_id, request.conversationId, request.roleName, request.content, request.time)
      )
      conn.commit()

    response.status_code = status.HTTP_201_CREATED
    # Return the message ID as per existing frontend expectation, not the full message object
    return {"id": message_id, "conversationId": request.conversationId, "roleName": request.roleName,
            "content": request.content, "time": request.time}


  except Exception as e:
    print(f"Error in user_send_message: {str(e)}")  # Enhanced logging
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return ErrorResponse(error=str(e))


@app.post("/api/message/generate")
async def generate_message(request: ApiMessageGenerate, response: Response):  # Removed default status_code
  print(f"Generate message called with: {request}")

  try:
    if not request.conversationId:  # Basic check, could add more
      response.status_code = status.HTTP_400_BAD_REQUEST
      return ErrorResponse(error="Conversation ID missing or invalid")

    context = await get_conversation_context(request.conversationId)
    if not context:  # Handle case where context might be empty if no prior messages
      # Decide how to handle this: maybe a default prompt or error
      print(f"No context found for conversationId {request.conversationId}, using default prompt for generation.")
      context = "Hello!"  # Fallback or specific instruction

    ai_response_content = await generate_llm_response(context)

    message_id = int(time.time() * 1000)  # Again, consider robust ID
    current_time = int(time.time())

    message_doc = {
      'id': message_id,
      'conversationId': request.conversationId,
      'roleName': request.roleName,  # This is the AI's role name
      'content': ai_response_content,
      'time': current_time
    }

    with get_db() as conn:
      cur = conn.cursor()
      cur.execute(
        """
        INSERT INTO messages (id, conversationId, roleName, content, time)
        VALUES (?, ?, ?, ?, ?)
        """,
        (message_id, request.conversationId, request.roleName,
         message_doc['content'], current_time)
      )
      conn.commit()

    response.status_code = status.HTTP_201_CREATED
    return message_doc  # Return the full message document as per original code

  except Exception as e:
    print(f"Error in generate_message: {str(e)}")  # Enhanced logging
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return ErrorResponse(error=str(e))


@app.patch("/api/message/patch")
async def patch_message(request: MessagePatch, response: Response):  # Added response parameter
  print(f"Patch message called with: {request}")
  try:
    if not request.id or not request.conversationId:  # Check both
      response.status_code = status.HTTP_400_BAD_REQUEST
      return ErrorResponse(error="Message ID and Conversation ID are required.")

    with get_db() as conn:
      cur = conn.cursor()
      cur.execute(
        """
        UPDATE messages
        SET content = ?
        WHERE id = ? AND conversationId = ?
        """,
        (request.content, request.id, request.conversationId)
      )
      conn.commit()

      if cur.rowcount == 0:
        response.status_code = status.HTTP_404_NOT_FOUND
        return ErrorResponse(error="Message not found or not updated.")

    response.status_code = status.HTTP_200_OK
    # As per FastAPI docs, a 200 OK for PATCH can return the updated resource or an empty body.
    # The original code returned None (which becomes HTTP 204 if no content is set).
    # To be more explicit for 200, let's return a success message or the patched object if needed.
    # For now, returning the request data as an example of what could be returned.
    # However, current frontend expects no body for successful patch (just 200 OK).
    # So, returning None is fine if status is set correctly.
    return {"id": request.id, "conversationId": request.conversationId, "content": request.content}


  except Exception as e:
    print(f"Error in patch_message: {str(e)}")  # Enhanced logging
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return ErrorResponse(error=str(e))


@app.delete("/api/message/delete/{conversation_id}/{message_id}")
async def delete_message(conversation_id: int, message_id: int, response: Response):  # Added response parameter
  print(f"Delete message called for conv_id: {conversation_id}, msg_id: {message_id}")

  try:
    if not conversation_id or not message_id:
      response.status_code = status.HTTP_400_BAD_REQUEST
      return ErrorResponse(error="Conversation ID and Message ID are required.")

    with get_db() as conn:
      cur = conn.cursor()
      cur.execute(
        "DELETE FROM messages WHERE conversationId = ? AND id = ?",
        (conversation_id, message_id)
      )
      conn.commit()

      if cur.rowcount == 0:
        response.status_code = status.HTTP_404_NOT_FOUND
        return ErrorResponse(error="Message not found.")

    response.status_code = status.HTTP_204_NO_CONTENT  # Correct status for successful deletion with no content
    return None  # Explicitly return None for 204


  except Exception as e:
    print(f"Error in delete_message: {str(e)}")  # Enhanced logging
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return ErrorResponse(error=str(e))


# CORS configuration
origins = [
  "http://localhost:4200",
  "http://localhost:8080",
  "https://localhost:4200",  # Assuming your Angular app might also run on HTTPS
  "https://localhost:8080",
]

app.add_middleware(
  CORSMiddleware,
  allow_origins=origins,
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
  expose_headers=["*"]  # Keep this if frontend needs to read custom headers from backend
)

# Development certificate setup
if os.getenv("USE_DEV_CERTS") == "True":
  print("Starting in development mode with auto-generated certificates...")
  cert_file, key_file = setup_development_certificates()

  print(f"""
    🔐 Development HTTPS certificates generated!

    To trust these certificates in development:
    1. Certificate file location: {cert_file}
    2. You might need to add an exception in your browser
    3. For Angular development, you might need to set NODE_TLS_REJECT_UNAUTHORIZED='0'

    ⚠️  These are self-signed certificates for development only!
    """)

  ssl_config = {
    "ssl_keyfile": key_file,
    "ssl_certfile": cert_file,
  }
else:
  ssl_config = {}

# To run with uvicorn and SSL, if ssl_config is populated:
# uvicorn backend_mockup:app --reload --ssl-keyfile devcerts/server.key --ssl-certfile devcerts/server.pem
