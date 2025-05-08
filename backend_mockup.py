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

# Pydantic models for responses (for OpenAPI documentation)
class MessageResponse(BaseModel):
    id: int
    conversationId: int
    roleName: str
    content: str
    time: int

class ConversationResponse(BaseModel):
    id: int
    hashsum: int


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
        # Use Meta's Llama model through Replicate
        output = replicate.run(
            "meta/meta-llama-3.1-405b-instruct", # Model identifier
            input={ # Input parameters for the model
                "prompt": prompt,
                "temperature": 0.6, # Controls randomness of output
                "top_p": 0.9, # Nucleus sampling parameter
                "max_tokens": 1024, # Maximum number of tokens in the response
                "system_prompt": "You are a helpful AI assistant engaged in a natural conversation." # System-level instructions
            }
        )

        # Replicate returns a generator, collect all parts of the streamed response
        return "".join(output)
    except Exception as e:
        print(f"Error generating response: {str(e)}")
        return "I apologize, but I encountered an error generating a response." # Fallback message


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

# Setup FastAPI app
# Initialize the FastAPI application.
# docs_url and redoc_url are set to None to disable default docs and use custom ones.
# openapi_url specifies the path for the OpenAPI schema.
app = FastAPI(
    title="Chat API",
    version="1.0.0",
    description="This is a backend server for a chat application.",
    docs_url=None,
    redoc_url=None,
    openapi_url="/api/openapi.json"
)

# Initialize the database on startup
init_db()


# Custom OpenAPI schema endpoint
@app.get(app.openapi_url, include_in_schema=False) # Use app.openapi_url here
async def custom_openapi():
    # Serves the OpenAPI schema in JSON format.
    # This is used by Swagger UI to understand the API structure.
    # The schema is generated based on the routes and Pydantic models.
    return get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

# Custom Swagger UI endpoint
@app.get("/api/docs", include_in_schema=False)
async def custom_swagger_ui_html(req: Request):
    # Serves the Swagger UI HTML page.
    # It fetches the OpenAPI schema from the `openapi_url` configured in the FastAPI app.
    root_path = req.scope.get("root_path", "").rstrip("/")
    openapi_url = root_path + app.openapi_url
    return get_swagger_ui_html(
        openapi_url=openapi_url, # URL to the OpenAPI schema
        title=app.title + " - Swagger UI" # Title for the Swagger UI page
    )


# API endpoints
@app.get("/api/conversation/byuserid/{user_id}",
         response_model=List[ConversationResponse], # Defines the expected response structure
         responses={ # Documents possible responses
             status.HTTP_204_NO_CONTENT: {"description": "No conversations found or no messages in conversation"},
             status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "User ID missing"},
             status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Internal server error"}
         },
         tags=["Conversation"]) # Groups this endpoint under "Conversation" in Swagger UI
async def get_conversations(user_id: int, response: Response):
    # Endpoint to get conversations for a user (currently hardcoded to conversation 1).
    print("Get conversations called")

    try:
        if not user_id: # Validate user_id
            response.status_code = status.HTTP_400_BAD_REQUEST
            return ErrorResponse(error="User id missing")

        with get_db() as conn:
            cur = conn.cursor()
            # Fetches messages for a hardcoded conversationId (1)
            # TODO: This should ideally fetch conversations based on user_id and return multiple conversations
            cur.execute(
                "SELECT * FROM messages WHERE conversationId = ?",
                (1,)
            )
            messages = cur.fetchall()

            print(f"Messages found: {len(messages)}")
            hashsum = generate_hash(messages) # Generate hash for the conversation

            # If hashsum is 0 (e.g. no messages, or messages that result in 0 hash)
            # and there are no messages, it means no content.
            if hashsum == 0 and not messages:
                response.status_code = status.HTTP_204_NO_CONTENT
                return None # FastAPI handles 204 correctly when None is returned and status_code is set

            # Returns a list containing a single conversation object (hardcoded ID 1)
            return [{'id': 1, 'hashsum': hashsum}] # This matches ConversationResponse

    except Exception as e:
        print(f"Error: {str(e)}")
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return ErrorResponse(error=str(e))


@app.get("/api/conversation/messages/{conversation_id}/{timestamp}/{messages_count}",
         response_model=List[MessageResponse], # Defines the expected list of messages
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
    # Removed status_code from parameters as it's handled dynamically or by response_model
):
    # Endpoint to get messages for a specific conversation, before a given timestamp.
    print("Get conversation messages called")

    try:
        # Validate required parameters
        if not conversation_id or timestamp is None: # Timestamp can be 0, so check for None
            response.status_code = status.HTTP_400_BAD_REQUEST
            return ErrorResponse(error="Conversation ID and latest timestamp are required")

        with get_db() as conn:
            cur = conn.cursor()
            # Fetch messages older than 'timestamp', limited by 'messages_count' (max 30)
            cur.execute(
                """
                SELECT id, conversationId, roleName, content, time
                FROM messages
                WHERE conversationId = ? AND time < ?
                ORDER BY time DESC LIMIT ?
                """,
                (conversation_id, timestamp, min(messages_count, 30)) # Limit to 30 messages max
            )
            messages_rows = cur.fetchall()

            if messages_rows:
                # Convert sqlite3.Row objects to dictionaries that match MessageResponse
                messages_data = [dict(msg) for msg in messages_rows]
                messages_data.reverse()  # Reverse to get chronological order (oldest first)

                # Set status to partial content if more messages were requested than returned (due to limit)
                if messages_count > 30 and len(messages_data) == 30:
                    response.status_code = status.HTTP_206_PARTIAL_CONTENT
                else:
                    response.status_code = status.HTTP_200_OK # Default success
                return messages_data # FastAPI will validate against List[MessageResponse]
            else:
                response.status_code = status.HTTP_204_NO_CONTENT
                return None

    except Exception as e:
        print(f"Error: {str(e)}")
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return ErrorResponse(error=str(e))


@app.post("/api/message/send",
          response_model=Dict[str, int], # Expected response: {"id": message_id}
          status_code=status.HTTP_201_CREATED, # Default success status for new resource
          responses={
              status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "Message content cannot be empty"},
              status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Internal server error"}
          },
          tags=["Message"])
async def user_send_message(request_body: ApiMessageSend, response: Response): # Renamed request to request_body for clarity
    # Endpoint for a user to send a message.
    print("Message send called")

    try:
        if not request_body.content: # Validate message content
            response.status_code = status.HTTP_400_BAD_REQUEST # Explicitly set for this error path
            return ErrorResponse(error="Message content cannot be empty")

        message_id = int(time.time() * 1000) # Generate a unique message ID based on current time

        with get_db() as conn:
            cur = conn.cursor()
            # Insert the new message into the database
            cur.execute(
                """
                INSERT INTO messages (id, conversationId, roleName, content, time)
                VALUES (?, ?, ?, ?, ?)
                """,
                (message_id, request_body.conversationId, request_body.roleName, request_body.content, request_body.time)
            )
            conn.commit() # Commit the transaction

        # No need to set response.status_code here, as decorator handles 201
        return {"id": message_id} # Return the ID of the newly created message

    except Exception as e:
        print(f"Error: {str(e)}")
        # For unexpected errors, ensure the response status reflects it
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return ErrorResponse(error=str(e))


@app.post("/api/message/generate",
          response_model=MessageResponse, # The generated message will be returned
          status_code=status.HTTP_201_CREATED,
          responses={
              status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "Conversation ID missing"},
              status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Internal server error"}
          },
          tags=["Message"])
async def generate_message(request_body: ApiMessageGenerate, response: Response): # Renamed request
    # Endpoint to generate an AI response for a conversation.
    print("Generate message called")

    try:
        # The original code checked `if not request:`, which would always be false for a Pydantic model.
        # Assuming the intent was to check if conversationId is present, Pydantic handles this.
        # If request_body itself is None (e.g. invalid JSON), FastAPI returns a 422.
        # Here, we ensure conversationId is part of the request model.
        if not request_body.conversationId: # This check is redundant if conversationId is mandatory in ApiMessageGenerate
            response.status_code = status.HTTP_400_BAD_REQUEST
            return ErrorResponse(error="Conversation ID missing or invalid in request")

        # Get conversation context for the LLM
        context = await get_conversation_context(request_body.conversationId)

        # Augment prompt for AI if needed (e.g., add the current role trying to speak)
        # For instance: context_for_llm = context + f"\n{request_body.roleName}:"
        # The original code passed `context` directly.
        ai_response_content = await generate_llm_response(context)

        message_id = int(time.time() * 1000) # Generate unique message ID
        current_time = int(time.time()) # Current timestamp

        # Prepare the message document to be saved and returned
        message_doc_data = {
            'id': message_id,
            'conversationId': request_body.conversationId,
            'roleName': request_body.roleName, # This is the role for the AI message
            'content': ai_response_content,
            'time': current_time
        }

        with get_db() as conn:
            cur = conn.cursor()
            # Insert the AI-generated message into the database
            cur.execute(
                """
                INSERT INTO messages (id, conversationId, roleName, content, time)
                VALUES (?, ?, ?, ?, ?)
                """,
                (message_id, request_body.conversationId, request_body.roleName,
                 message_doc_data['content'], current_time)
            )
            conn.commit() # Commit the transaction

        return message_doc_data # FastAPI validates against MessageResponse

    except Exception as e:
        print(f"Error: {str(e)}")
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return ErrorResponse(error=str(e))


@app.patch("/api/message/patch",
           status_code=status.HTTP_204_NO_CONTENT, # Success means no content returned
           responses={
               # 204 is the default success, no model needed for body
               status.HTTP_400_BAD_REQUEST: {"description": "Message ID missing or invalid request"},
               status.HTTP_404_NOT_FOUND: {"description": "Message not found"},
               status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Internal server error"}
           },
           tags=["Message"])
async def patch_message(request_body: MessagePatch, response: Response): # Renamed request
    # Endpoint to update the content of an existing message.
    print("Patch message called")

    try:
        if not request_body.id: # Validate message ID
            response.status_code = status.HTTP_400_BAD_REQUEST
            # For 400, it's better to return a plain Response or an ErrorResponse if defined in `responses`
            return Response(status_code=status.HTTP_400_BAD_REQUEST, content="Message ID missing")

        with get_db() as conn:
            cur = conn.cursor()
            # Update the message content in the database
            cur.execute(
                """
                UPDATE messages
                SET content = ?
                WHERE id = ? AND conversationId = ?
                """,
                (request_body.content, request_body.id, request_body.conversationId)
            )
            conn.commit() # Commit the transaction

            if cur.rowcount == 0: # Check if any row was updated
                response.status_code = status.HTTP_404_NOT_FOUND
                return Response(status_code=status.HTTP_404_NOT_FOUND, content="Message not found")

        return None # For 204 No Content, FastAPI expects no body. Returning None is correct.

    except Exception as e:
        print(f"Error: {str(e)}")
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return ErrorResponse(error=str(e))


@app.delete("/api/message/delete/{conversation_id}/{message_id}",
            status_code=status.HTTP_204_NO_CONTENT, # Success means no content returned
            responses={
               # 204 is default success
               status.HTTP_400_BAD_REQUEST: {"description": "Conversation ID or Message ID missing"},
               status.HTTP_404_NOT_FOUND: {"description": "Message not found"},
               status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Internal server error"}
            },
            tags=["Message"])
async def delete_message(conversation_id: int, message_id: int, response: Response):
    # Endpoint to delete a specific message.
    print("Delete message called")

    try:
        # Validate conversation_id and message_id (FastAPI does basic type validation from path)
        if not conversation_id or not message_id: # Redundant if path params are always present
            response.status_code = status.HTTP_400_BAD_REQUEST
            return Response(status_code=status.HTTP_400_BAD_REQUEST, content="Conversation ID or Message ID missing")

        with get_db() as conn:
            cur = conn.cursor()
            # Delete the message from the database
            cur.execute(
                "DELETE FROM messages WHERE conversationId = ? AND id = ?",
                (conversation_id, message_id)
            )
            conn.commit() # Commit the transaction

            if cur.rowcount == 0: # Check if any row was deleted
                response.status_code = status.HTTP_404_NOT_FOUND
                return Response(status_code=status.HTTP_404_NOT_FOUND, content="Message not found")

        return None # For 204 No Content

    except Exception as e:
        print(f"Error: {str(e)}")
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return ErrorResponse(error=str(e))


# CORS configuration
# Defines a list of allowed origins for Cross-Origin Resource Sharing (CORS).
origins = [
    "http://localhost:4200", # Angular default
    "http://localhost:8080", # Common dev port
    "https://localhost:4200",
    "https://localhost:8080",
    # Add other origins as needed
]

# Add CORS middleware to the FastAPI application.
# This allows requests from the specified origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins, # List of allowed origins
    allow_credentials=True, # Allow cookies to be included in requests
    allow_methods=["*"], # Allow all HTTP methods
    allow_headers=["*"], # Allow all headers
    expose_headers=["*"] # Allow all headers to be exposed
)

# Development certificate setup
# Checks an environment variable to determine if development SSL certificates should be used.
ssl_config = {} # Initialize ssl_config
if os.getenv("USE_DEV_CERTS") == "True":
    print("Starting in development mode with auto-generated certificates...")
    cert_file, key_file = setup_development_certificates() # Generate/load dev certs

    print(f"""
    🔐 Development HTTPS certificates generated!

    To trust these certificates in development:
    1. Certificate Authority (CA) file: devcerts/ca.pem (import this into your browser/system)
    2. Server certificate file: {cert_file}
    3. You might need to add an exception in your browser for localhost.
    4. For Angular development, you might need to set NODE_TLS_REJECT_UNAUTHORIZED='0' in your environment.

    ⚠️  These are self-signed certificates for development only! Do not use in production.
    """)

    # Configuration for Uvicorn to use SSL
    ssl_config = {
        "ssl_keyfile": key_file,
        "ssl_certfile": cert_file,
    }


# Main entry point for running the Uvicorn server (if the script is executed directly)
if __name__ == "__main__":
    import uvicorn
    # Determine host and port, default to localhost:8000
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))

    # Prepare Uvicorn run arguments
    # Enable auto-reload for development, which is helpful for seeing changes quickly.
    run_args = {"host": host, "port": port, "reload": True}
    if ssl_config: # Add SSL context if configured
        run_args.update(ssl_config)
        print(f"🚀 Starting server at https://{host}:{port}")
        print(f"📄 OpenAPI schema available at: https://{host}:{port}{app.openapi_url}")
        print(f"📚 Swagger UI available at: https://{host}:{port}/api/docs")
    else:
        print(f"🚀 Starting server at http://{host}:{port}")
        print(f"📄 OpenAPI schema available at: http://{host}:{port}{app.openapi_url}")
        print(f"📚 Swagger UI available at: http://{host}:{port}/api/docs")

    # Get the filename of the current script to pass to uvicorn.run
    # This makes the run command more robust if the file is renamed.
    current_script_name = Path(__file__).stem
    uvicorn.run(f"{current_script_name}:app", **run_args)
    # If your script is named e.g. 'server.py', uvicorn will look for 'server:app'.
    # Ensure 'app' is the instance of your FastAPI application.

