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
from fastapi import FastAPI, Response, status, Request # Added Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html # Added for Swagger UI
from fastapi.openapi.utils import get_openapi # Added for OpenAPI schema
from pydantic import BaseModel
from typing import List, Dict # Added Dict
from dotenv import load_dotenv, find_dotenv
from pathlib import Path
from contextlib import contextmanager


# Error response model
class ErrorResponse(BaseModel):
  error: str


# Pydantic models for request validation (combining both versions)
class ConversationState(BaseModel): # From your version, kept for potential future use
  id: int
  hashsum: int

class ApiConversationsCheck(BaseModel): # From your version, kept for potential future use
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
  id: int # Matches your version (and develop's for the model itself)
  conversationId: int
  content: str

# --- Start: Added for hardcoded session (from your version) ---
class UserDetails(BaseModel):
  id: int
  name: str
  email: str


class SessionInfoResponse(BaseModel):
  user: UserDetails
  token: str


# Hardcoded user and session token (from your version)
HARDCODED_USER_ID = 777
HARDCODED_USER_NAME = "Backend User"
HARDCODED_USER_EMAIL = "backend.user@example.com"
HARDCODED_SESSION_TOKEN = "hardcoded-backend-session-token-12345"
# --- End: Added for hardcoded session ---

# Pydantic models for responses (for OpenAPI documentation - from develop, adapted)
class MessageResponse(BaseModel): # From develop
  id: int
  conversationId: int
  roleName: str
  content: str
  time: int

# Adapted ConversationResponse to include more details like in your version
class ConversationResponse(BaseModel): # From develop, adapted
  id: int
  hashsum: int
  userId: int  # Added from your version's logic
  name: str    # Added from your version's logic
  participants: List[str] # Added from your version's logic


# Database connection management
@contextmanager
def get_db():
  # Establishes a connection to the SQLite database.
  # It uses a context manager to ensure the connection is closed automatically.
  conn = sqlite3.connect('chat.db')
  conn.row_factory = sqlite3.Row  # This enables dictionary-like access to rows
  try:
    yield conn
  finally:
    conn.close()


# Initialize database and create tables
def init_db():
  # Initializes the database by creating necessary tables if they don't exist.
  with get_db() as conn:
    cur = conn.cursor()

    # Create messages table to store chat messages
    cur.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                                                      id INTEGER PRIMARY KEY,
                                                      conversationId INTEGER NOT NULL,
                                                      roleName TEXT NOT NULL,
                                                      content TEXT NOT NULL,
                                                      time INTEGER NOT NULL
                )
                ''')

    # Create index for faster querying by conversationId and time
    cur.execute('''
                CREATE INDEX IF NOT EXISTS idx_conversation_time
                  ON messages(conversationId, time)
                ''')

    conn.commit() # Commit changes to the database


# Generate and save development certificates using trustme
def setup_development_certificates():
  # Sets up SSL certificates for local development using trustme.
  # This allows running the server over HTTPS.
  ca = trustme.CA()
  server_cert = ca.issue_cert("localhost") # Generate certificate for localhost
  cert_dir = Path("devcerts") # Define directory to store certificates
  cert_dir.mkdir(exist_ok=True) # Create directory if it doesn't exist

  # Write server certificate and private key to files
  server_cert.private_key_and_cert_chain_pem.write_to_path(cert_dir / "server.pem")
  server_cert.private_key_pem.write_to_path(cert_dir / "server.key")
  # Write CA certificate to file
  ca.cert_pem.write_to_path(cert_dir / "ca.pem")

  return str(cert_dir / "server.pem"), str(cert_dir / "server.key")


# Generate a hashsum from the conversation messages
def generate_hash(messages: List[sqlite3.Row]) -> int:
  """
  Custom hashsum generator for checking the integrity of a conversation.
  This function creates a numerical hash based on the content of messages.
  """
  if not messages:
    return 0 # Return 0 if there are no messages

  hash_value = 0
  hash_chars = "" # String representation for debugging

  for message in messages:
    content = message['content']
    if not content: # Skip if content is empty
      hash_value += 0
      continue

    # Simple hash algorithm based on first/last char and length
    hash_value += ord(content[0])
    hash_value += ord(content[-1])
    hash_value *= len(content)
    hash_chars += content[0] + content[-1] + str(len(content))

  hash_value %= (2**32) # Ensure hash_value fits within a 32-bit integer
  print(f"Generated hashsum: {hash_value} string rep: {hash_chars}")
  return hash_value


# Generate a response using Replicate's API
async def generate_llm_response(prompt: str) -> str:
  # Generates a text response using a Large Language Model (LLM) via Replicate API.
  try:
    # Use Meta's Llama model through Replicate (using 8B model from your version)
    output = replicate.run(
      "meta/meta-llama-3-8b-instruct", # Using 8B model from your version
      input={ # Input parameters for the model
        "prompt": prompt,
        "temperature": 0.6, # Controls randomness of output
        "top_p": 0.9, # Nucleus sampling parameter
        "max_tokens": 1024, # Maximum number of tokens in the response
        "system_prompt": "You are a helpful AI assistant engaged in a natural conversation."
      }
    )

    # Replicate returns a generator, collect all parts of the streamed response
    return "".join(output)
  except Exception as e:
    print(f"Error generating response: {str(e)}")
    return "I apologize, but I encountered an error generating a response."


# Get conversation context
async def get_conversation_context(conversation_id: int, limit: int = 5) -> str:
  # Retrieves the recent message history for a given conversation to provide context for the LLM.
  try:
    with get_db() as conn:
      cur = conn.cursor()
      # Fetch the last 'limit' messages for the conversation, ordered by time
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
      for msg in reversed(messages): # Reverse to maintain chronological order for the prompt
        context.append(f"{msg['roleName']}: {msg['content']}")

      return "\n".join(context)
  except Exception as e:
    print(f"Error getting conversation context: {str(e)}")
    return "" # Return empty string on error


# Load environment variables from .env file
load_dotenv(find_dotenv())

# Setup FastAPI app (from develop, with adaptations)
app = FastAPI(
  title="Chat API",
  version="1.0.0",
  description="This is a backend server for a chat application.",
  docs_url=None, # Using custom docs
  redoc_url=None, # Using custom docs
  openapi_url="/api/openapi.json" # Standardized OpenAPI schema URL
)

# Initialize the database on startup
init_db()


# Custom OpenAPI schema endpoint (from develop)
@app.get(app.openapi_url, include_in_schema=False)
async def custom_openapi():
  return get_openapi(
    title=app.title,
    version=app.version,
    description=app.description,
    routes=app.routes,
  )


# Custom Swagger UI endpoint (from develop)
@app.get("/api/docs", include_in_schema=False)
async def custom_swagger_ui_html(req: Request):
  root_path = req.scope.get("root_path", "").rstrip("/")
  openapi_url = root_path + app.openapi_url
  return get_swagger_ui_html(
    openapi_url=openapi_url,
    title=app.title + " - Swagger UI"
  )

# --- Start: Added for hardcoded session (from your version) ---
@app.get("/api/auth/session-info",
         response_model=SessionInfoResponse,
         tags=["Authentication"])
async def get_session_info():
  print("Auth session-info called")
  user_details = UserDetails(
    id=HARDCODED_USER_ID,
    name=HARDCODED_USER_NAME,
    email=HARDCODED_USER_EMAIL
  )
  return SessionInfoResponse(user=user_details, token=HARDCODED_SESSION_TOKEN)
# --- End: Added for hardcoded session ---


# API endpoints
@app.get("/api/conversation/byuserid/{user_id}",
         response_model=List[ConversationResponse], # Adapted ConversationResponse
         responses={
           status.HTTP_204_NO_CONTENT: {"description": "No conversations found or no messages in conversation"},
           status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "User ID missing"},
           status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Internal server error"}
         },
         tags=["Conversation"])
async def get_conversations(user_id: int, response: Response): # status_code removed from params, handled by decorator/logic
  print(f"Get conversations called for user_id: {user_id}")
  try:
    if not user_id and user_id != 0: # Allow user_id 0
      response.status_code = status.HTTP_400_BAD_REQUEST
      return ErrorResponse(error="User id missing or invalid")

    with get_db() as conn:
      cur = conn.cursor()
      # Still uses hardcoded conversationId = 1 as per original logic of your version
      cur.execute(
        "SELECT * FROM messages WHERE conversationId = ?",
        (1,)
      )
      messages = cur.fetchall()
      print(f"Messages found for conversationId=1: {len(messages)}")
      hashsum = generate_hash(messages)

      if not messages: # If no messages, implies no content for this hardcoded conversation
        print(f"No messages found for conversationId=1, hashsum: {hashsum}. Returning 204.")
        response.status_code = status.HTTP_204_NO_CONTENT
        return None

      # Return richer conversation data as per your version's logic
      return [{
        'id': 1, # Hardcoded conversation ID
        'hashsum': hashsum,
        'userId': user_id, # Echoing back the user_id for consistency
        'name': f'Chat for User {user_id} (Conv 1)',
        'participants': ['user', 'Assistant']
      }]

  except Exception as e:
    print(f"Error in get_conversations: {str(e)}")
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return ErrorResponse(error=str(e))


@app.get("/api/conversation/messages/{conversation_id}/{timestamp}/{messages_count}",
         response_model=List[MessageResponse],
         responses={
           status.HTTP_204_NO_CONTENT: {"description": "No messages found"},
           status.HTTP_206_PARTIAL_CONTENT: {"description": "Partial content, more messages available"},
           status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "Conversation ID or timestamp missing"},
           status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Internal server error"}
         },
         tags=["Conversation"])
async def get_conversation_messages(
  conversation_id: int,
  timestamp: int,
  messages_count: int,
  response: Response
):
  print(f"Get conversation messages called for conv_id: {conversation_id}, timestamp: {timestamp}, count: {messages_count}")
  try:
    if not conversation_id or timestamp is None:
      response.status_code = status.HTTP_400_BAD_REQUEST
      return ErrorResponse(error="Conversation ID and latest timestamp are required")

    with get_db() as conn:
      cur = conn.cursor()
      # Selecting specific columns as in develop branch, good practice
      cur.execute(
        """
        SELECT id, conversationId, roleName, content, time
        FROM messages
        WHERE conversationId = ? AND time < ?
        ORDER BY time DESC LIMIT ?
        """,
        (conversation_id, timestamp, min(messages_count, 30))
      )
      messages_rows = cur.fetchall()

      if messages_rows:
        messages_data = [dict(msg) for msg in messages_rows]
        messages_data.reverse()

        if messages_count > 30 and len(messages_data) == 30:
          response.status_code = status.HTTP_206_PARTIAL_CONTENT
        else:
          response.status_code = status.HTTP_200_OK
        return messages_data
      else:
        response.status_code = status.HTTP_204_NO_CONTENT
        return None

  except Exception as e:
    print(f"Error in get_conversation_messages: {str(e)}")
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return ErrorResponse(error=str(e))

# Using request_body naming from develop branch for clarity
@app.post("/api/message/send",
          response_model=MessageResponse, # Changed to return full message, good for frontend
          status_code=status.HTTP_201_CREATED,
          responses={
            status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "Message content cannot be empty"},
            status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Internal server error"}
          },
          tags=["Message"])
async def user_send_message(request_body: ApiMessageSend, response: Response):
  print(f"Message send called with: {request_body}")
  try:
    if not request_body.content:
      response.status_code = status.HTTP_400_BAD_REQUEST
      return ErrorResponse(error="Message content cannot be empty")

    message_id = int(time.time() * 1000)

    with get_db() as conn:
      cur = conn.cursor()
      cur.execute(
        """
        INSERT INTO messages (id, conversationId, roleName, content, time)
        VALUES (?, ?, ?, ?, ?)
        """,
        (message_id, request_body.conversationId, request_body.roleName, request_body.content, request_body.time)
      )
      conn.commit()

    # Return the full message object, consistent with MessageResponse
    return {
      "id": message_id,
      "conversationId": request_body.conversationId,
      "roleName": request_body.roleName,
      "content": request_body.content,
      "time": request_body.time
    }

  except Exception as e:
    print(f"Error in user_send_message: {str(e)}")
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return ErrorResponse(error=str(e))


@app.post("/api/message/generate",
          response_model=MessageResponse,
          status_code=status.HTTP_201_CREATED,
          responses={
            status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "Conversation ID missing"},
            status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Internal server error"}
          },
          tags=["Message"])
async def generate_message(request_body: ApiMessageGenerate, response: Response):
  print(f"Generate message called with: {request_body}")
  try:
    if not request_body.conversationId and request_body.conversationId !=0: # Allow convId 0
      response.status_code = status.HTTP_400_BAD_REQUEST
      return ErrorResponse(error="Conversation ID missing or invalid in request")

    context = await get_conversation_context(request_body.conversationId)
    if not context:
      print(f"No context found for conversationId {request_body.conversationId}, using default prompt for generation.")
      context = "Hello!"

    ai_response_content = await generate_llm_response(context)
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
        INSERT INTO messages (id, conversationId, roleName, content, time)
        VALUES (?, ?, ?, ?, ?)
        """,
        (message_doc_data['id'], message_doc_data['conversationId'], message_doc_data['roleName'],
         message_doc_data['content'], message_doc_data['time'])
      )
      conn.commit()
    return message_doc_data

  except Exception as e:
    print(f"Error in generate_message: {str(e)}")
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return ErrorResponse(error=str(e))

# Changed to return MessageResponse with 200 OK as frontend expects updated object
@app.patch("/api/message/patch",
           response_model=MessageResponse,
           status_code=status.HTTP_200_OK,
           responses={
             status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "Message ID or Conversation ID missing"},
             status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Message not found"},
             status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Internal server error"}
           },
           tags=["Message"])
async def patch_message(request_body: MessagePatch, response: Response):
  print(f"Patch message called with: {request_body}")
  try:
    if not request_body.id or request_body.conversationId is None: # Check both
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
        (request_body.content, request_body.id, request_body.conversationId)
      )
      conn.commit()

      if cur.rowcount == 0:
        response.status_code = status.HTTP_404_NOT_FOUND
        return ErrorResponse(error="Message not found or not updated.")

    # Fetch the updated message to return it (or construct it)
    # For simplicity, returning the request_body as it now contains the new content
    # and matches MessageResponse if we assume time/roleName don't change on patch.
    # A more robust way would be to SELECT the message after UPDATE.
    # For now, this aligns with frontend expecting the updated content.
    # The frontend might primarily care about the content and ID.
    # We'll construct a full response. The original roleName and time would persist.
    # This requires fetching the original message to get roleName and time if they are not in MessagePatch.
    # Simplified: return the patch payload, assuming frontend can handle partial update info or already has it.
    # Best: fetch full updated row.
    # Compromise: return what we have that matches MessageResponse.

    # To return a full MessageResponse, we would need to fetch the message.
    # For now, let's assume the frontend can work with the information in MessagePatch for the update.
    # Or, if MessageResponse is strictly required:
    cur.execute("SELECT * FROM messages WHERE id = ?", (request_body.id,))
    updated_message_row = cur.fetchone()
    if updated_message_row:
      return dict(updated_message_row)
    else: # Should not happen if rowcount > 0
      response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
      return ErrorResponse(error="Failed to retrieve updated message after patch.")


  except Exception as e:
    print(f"Error in patch_message: {str(e)}")
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return ErrorResponse(error=str(e))


@app.delete("/api/message/delete/{conversation_id}/{message_id}",
            status_code=status.HTTP_204_NO_CONTENT,
            responses={
              status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "Conversation ID or Message ID missing"},
              status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Message not found"},
              status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Internal server error"}
            },
            tags=["Message"])
async def delete_message(conversation_id: int, message_id: int, response: Response):
  print(f"Delete message called for conv_id: {conversation_id}, msg_id: {message_id}")
  try:
    # Path parameters are validated by FastAPI for type.
    # Explicit check might be redundant unless checking for specific values.
    with get_db() as conn:
      cur = conn.cursor()
      cur.execute(
        "DELETE FROM messages WHERE conversationId = ? AND id = ?",
        (conversation_id, message_id)
      )
      conn.commit()

      if cur.rowcount == 0:
        response.status_code = status.HTTP_404_NOT_FOUND
        # Return ErrorResponse for consistency in documented error responses
        return ErrorResponse(error="Message not found.")
    return None # For 204 No Content

  except Exception as e:
    print(f"Error in delete_message: {str(e)}")
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return ErrorResponse(error=str(e))


# CORS configuration (from develop)
origins = [
  "http://localhost:4200",
  "http://localhost:8080",
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

# Development certificate setup (from develop)
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

# Main entry point for running the Uvicorn server (from develop)
if __name__ == "__main__":
  import uvicorn
  host = os.getenv("HOST", "127.0.0.1") # Default to 127.0.0.1 for broader compatibility
  port = int(os.getenv("PORT", "8443")) # Default to 8443 as used in uvicorn commands

  run_args = {"host": host, "port": port, "reload": True}
  if ssl_config:
    run_args.update(ssl_config)
    proto = "https"
  else:
    proto = "http"

  print(f"🚀 Starting Uvicorn server at {proto}://{host}:{port}")
  print(f"📄 OpenAPI schema available at: {proto}://{host}:{port}{app.openapi_url}")
  print(f"📚 Swagger UI available at: {proto}://{host}:{port}/api/docs")

  current_script_name = Path(__file__).stem # e.g., "backend_mockup"
  uvicorn.run(f"{current_script_name}:app", **run_args)
