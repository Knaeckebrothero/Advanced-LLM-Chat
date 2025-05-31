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
from fastapi import FastAPI, Response, status, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel
from typing import List, Dict, Optional
from dotenv import load_dotenv, find_dotenv
from pathlib import Path
from contextlib import contextmanager, asynccontextmanager
from datetime import datetime, timedelta, UTC


class ErrorResponse(BaseModel):
    """
    Represents an error response model for providing error details to clients.

    This class is used to define a structured format for handling and returning
    error information in the system. It typically includes details about the error
    that occurred, allowing for more informative client communication.

    :ivar error: Description of the error that occurred.
    :type error: str
    """
    error: str


class MockLoginRequest(BaseModel):
    email: str
    # In real implementation, this might include IDP tokens, SAML response, etc.


class LoginResponse(BaseModel):
    """
    Represents the response received upon a successful login attempt.

    This class is used to encapsulate the details of a login response,
    including information about the user and any additional message
    associated with the login process.

    :ivar user: Contains details relating to the logged-in user, such as
        their profile information or credentials.
    :type user: dict
    :ivar message: A message conveying additional information or feedback
        about the login process.
    :type message: str
    """
    user: dict
    message: str


class ConversationState(BaseModel):
    """
    Represents the state of a conversation.

    This class is designed to store the unique state of a conversation,
    identified by an ID and a corresponding hashsum. It can be used for
    tracking, validation, or processing conversation states in an application.

    :ivar id: Unique identifier for the conversation state.
    :type id: int
    :ivar hashsum: Hashsum of the conversation state, used for validation or
        other purposes.
    :type hashsum: int
    """
    id: int
    hashsum: int


class ApiConversationsCheck(BaseModel):
    """
    Represents a model for checking the list of conversation states.

    This class serves as a container for a collection of `ConversationState`
    objects, storing their states and providing a structured representation.
    It follows a schema validation and can be used to encapsulate conversation
    state information in various applications.

    :ivar conversations: A list of `ConversationState` objects representing the
        current states of various conversations.
    :type conversations: List[ConversationState]
    """
    conversations: List[ConversationState]


class ApiMessageSend(BaseModel):
    """
    Represents a message sent within a specific conversation.

    This class is used to encapsulate the details of a message sent in a
    conversation, including the conversation ID, the role of the sender,
    the content of the message, and the timestamp of when the message
    was sent.

    :ivar conversationId: Identifier of the conversation the message is associated with.
    :type conversationId: int
    :ivar roleName: Name or role of the sender of the message.
    :type roleName: str
    :ivar content: The textual content of the message.
    :type content: str
    :ivar time: Timestamp indicating when the message was sent, represented as an integer.
    :type time: int
    """
    conversationId: int
    roleName: str
    content: str
    time: int


class ApiMessageGenerate(BaseModel):
    """
    Represents a model for generating API messages.

    This class encapsulates the data and functionality required for handling
    the generation of API messages. It stores information about the message
    details, such as the associated conversation ID, the role name, and the
    time of the message.

    :ivar conversationId: Identifier for the conversation associated with
        this message.
    :type conversationId: int
    :ivar roleName: Name of the role associated with the message.
    :type roleName: str
    :ivar time: Timestamp of when the message is generated or occurred.
    :type time: int
    """
    conversationId: int
    roleName: str
    time: int


class MessagePatch(BaseModel):
    """
    Represents a model for updating message data within a conversation.

    This class is used as a data structure for holding updated message
    information such as the unique message identifier, the associated
    conversation identifier, and the updated content of the message.

    :ivar id: The unique identifier of the message.
    :type id: int
    :ivar conversationId: The unique identifier of the conversation to
        which the message belongs.
    :type conversationId: int
    :ivar content: The updated content of the message.
    :type content: str
    """
    id: int
    conversationId: int
    content: str


class MessageResponse(BaseModel):
    """
    Represents a response message within a conversation context.

    This class serves as a data model for handling details related to a response
    message in a conversation, including identifiers, role information, message
    content, and the timestamp of when the message was created or sent.

    :ivar id: Unique identifier of the message.
    :type id: int
    :ivar conversationId: Identifier of the conversation to which the message belongs.
    :type conversationId: int
    :ivar roleName: Role of the entity sending the message, such as 'user' or 'assistant'.
    :type roleName: str
    :ivar content: Text content of the response message.
    :type content: str
    :ivar time: Timestamp indicating when the message was created or sent, typically in epoch format.
    :type time: int
    """
    id: int
    conversationId: int
    roleName: str
    content: str
    time: int


class ConversationResponse(BaseModel):
    """
    Encapsulates the response details of a conversation.

    This class represents the information related to a conversation's
    response, such as its unique identifier and hash sum. It inherits
    from `BaseModel` to utilize its functionality for data validation
    and management.

    :ivar id: Unique identifier for the conversation response.
    :type id: int
    :ivar hashsum: Hash sum representing the conversation response.
    :type hashsum: int
    """
    id: int
    hashsum: int


@contextmanager
def get_db():
    """
    Establishes and manages a connection to the SQLite database.

    This function acts as a context manager for database interactions.
    It ensures that the database connection is properly opened and
    closed, even in cases of exceptions. The database connection is
    configured to allow dictionary-like access to rows using the
    `sqlite3.Row` factory.

    :param None: This function does not accept any parameters.
    :yield: sqlite3.Connection
        A connection object for interacting with the SQLite database.
    :return: None
    """
    # It uses a context manager to ensure the connection is closed automatically.
    conn = sqlite3.connect('chat.db')
    conn.row_factory = sqlite3.Row  # This enables dictionary-like access to rows
    try:
        yield conn
    finally:
        conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
  """
  Manages the lifespan of the FastAPI application.

  This function is an asynchronous context manager that performs actions during
  the startup and shutdown of a FastAPI application. On startup, it launches a
  background task to clean up expired sessions. On shutdown, it ensures proper
  cleanup before the application terminates.

  :param app: The FastAPI application instance whose lifespan is being managed.
  :type app: FastAPI
  :return: An asynchronous generator managing the application lifecycle.
  :rtype: AsyncGenerator[None, None]
  """
  asyncio.create_task(cleanup_expired_sessions())
  yield


def generate_session_key(length=32) -> str:
    """
    Generate a secure, random session key.

    This function generates a session key using a cryptographically secure
    method. It ensures the generated string is URL-safe and suitable for
    use in contexts such as session identifiers or API keys.

    :param length: Length of the session key to be generated. Defaults to 32.
    :type length: int
    :return: A URL-safe, random session key string of the specified length.
    :rtype: str
    """
    return secrets.token_urlsafe(length)


def create_session(user_id: int, user_email: str, session_duration_hours=24) -> str:
    """
    Creates a session for a given user with a specified duration in hours. The session includes a unique
    session key and an expiration timestamp. The session details are persisted to the database for
    later verification.

    :param user_id: Unique identifier of the user for whom the session is being created.
    :param user_email: Email address of the user related to the session.
    :param session_duration_hours: Optional; Number of hours the session is valid. Default value is 24.
    :return: A unique session key as a string that identifies the created session.
    :rtype: str
    """
    session_key = generate_session_key()
    expires_at = datetime.now(UTC) + timedelta(hours=session_duration_hours)

    # Save session to database
    with get_db() as db:
        db.execute(
            """
            INSERT INTO sessions (session_key, user_id, email, expires_at)
            VALUES (?, ?, ?, ?)
            """, (session_key, user_id, user_email, expires_at.isoformat()))

        db.commit()

    return session_key


def validate_session(session_key: str) -> Optional[dict]:
    """
    Validates a provided session key by checking active in-memory sessions first,
    and falling back to database validation if necessary. It ensures that the session is not
    expired, removes expired sessions, and updates session activity timestamp when valid.
    The function returns session user-related data if the session is valid,
    or None if the session key is invalid or expired.

    :param session_key: The session key to be validated.
    :type session_key: str

    :return: A dictionary containing user-related data (user_id and email) if the session
             is valid or None if invalid/expired.
    :rtype: Optional[dict]
    """
    if not session_key:
        return None

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT user_id, email, expires_at, last_activity
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
            "email": result["email"]
        }


def delete_session(session_key: str):
    """
    Deletes a session from the memory and the database. This function first checks
    if the session key exists in the in-memory sessions storage and deletes it
    if present. Subsequently, it deletes the session with the given session key
    from the database to maintain consistency.

    :param session_key: The key identifying the session to be deleted
    :type session_key: str
    :return: None
    """
    if session_key in sessions:
      del sessions[session_key]

    with get_db() as conn:
      cur = conn.cursor()
      cur.execute("DELETE FROM sessions WHERE session_key = ?", (session_key,))
      conn.commit()


async def get_current_user(request: Request) -> dict:
    """
    Retrieves the current user based on the session information provided
    in the request cookies. The function validates the session key and
    returns user information if the session is valid. If the session is
    invalid or missing, raises an HTTP exception.

    :param request: The HTTP request object containing cookies with the
        session information
    :type request: Request
    :return: A dictionary containing the details of the authenticated user
    :rtype: dict
    :raises HTTPException: If the session key is missing or invalid
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
    Attempts to retrieve the current user based on the provided request. If the
    user is not authenticated or an HTTPException occurs during the process, it
    returns None instead of raising the exception.

    :param request: Request instance containing the context for the current
        HTTP request.
    :type request: Request
    :return: A dictionary containing user information if authentication is
        successful, or None if no user is authenticated or an exception occurs.
    :rtype: Optional[dict]
    """
    try:
      return await get_current_user(request)
    except HTTPException:
      return None


async def cleanup_expired_sessions():
    """
    Periodically cleans up expired sessions from both in-memory storage and the database.
    This method runs indefinitely, removing sessions that have expired from the in-memory
    storage and the database at regular intervals. It ensures proper cleanup to prevent
    storage bloat and maintain system performance.

    :raises Exception: if any uncaught error occurs during in-memory or database cleanup operations.

    :return: None
    """
    while True:
      try:
        # Clean in-memory sessions
        expired_keys = [
          key for key, session in sessions.items()
          if datetime.now(UTC) > session["expires_at"]
        ]
        for key in expired_keys:
          del sessions[key]

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
    Initializes the database and sets up the required tables if they are not already created. This includes
    the creation of tables to store chat messages, sessions, and users, along with an index for efficient
    querying in the `messages` table. This function ensures that the database structure is ready for usage.

    :return: None
    """
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

        # Create sessions table to manage user sessions
        cur.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                session_key TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                email TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # In init_db()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')


        # Create index for faster querying by conversationId and time
        cur.execute('''
            CREATE INDEX IF NOT EXISTS idx_conversation_time
            ON messages(conversationId, time)
        ''')

        conn.commit() # Commit changes to the database


def setup_development_certificates():
    """
    Sets up self-signed SSL certificates for local development using the `trustme` library. These certificates
    enable running the server over HTTPS in a secure manner during development. The function generates a
    Certificate Authority (CA) and server certificates, saves them in a directory, and returns the paths to
    the certificate and private key.

    :return: A tuple containing the file paths to the server certificate and private key.
    :rtype: Tuple[str, str]
    """
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


def generate_hash(messages: List[sqlite3.Row]) -> int:
    """
    Generates a hash value based on the content of the provided messages. This method applies
    a basic hashing logic using the first and last character of each message content and the
    string length. If the list of messages is empty, the hash value defaults to 0. The result
    is constrained to a 32-bit integer format.

    :param messages: A list of sqlite3.Row objects. Each row should contain a 'content' field
        with a string value that will be used for generating the hash.
    :type messages: List[sqlite3.Row]
    :return: An integer representing the computed hash value. If the provided list is empty,
        the returned value is 0.
    :rtype: int
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


async def generate_llm_response(prompt: str) -> str:
    """
    Generates a text response using a Large Language Model (LLM) via Replicate API.

    This function utilizes Meta's Llama model to generate a text response based on
    the input prompt. The model parameters such as temperature, top_p, and max tokens
    are configurable within the function. The response is returned as a concatenated
    string.

    :param prompt: The input prompt to generate a response.
    :type prompt: str
    :return: Text response generated by the LLM.
    :rtype: str
    """
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


async def get_conversation_context(conversation_id: int, limit: int = 5) -> str:
    """
    Retrieves the recent message history for a specific conversation, providing
    a textual context that can be used as input for a language model or other
    processes. The context consists of the last `limit` messages, ordered
    chronologically.

    :param conversation_id: The unique identifier for the conversation.
    :type conversation_id: int
    :param limit: The maximum number of recent messages to retrieve
        from the conversation. Default is 5.
    :type limit: int
    :return: A string containing the conversation context, where each
        message is prefaced by the role of its sender.
    :rtype: str
    """
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

# Session storage (use Redis or database in production)
sessions: Dict[str, dict] = {}

# Setup FastAPI app
# Initialize the FastAPI application.
# docs_url and redoc_url are set to None to disable default docs and use custom ones.
# openapi_url specifies the path for the OpenAPI schema.
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


@app.get(app.openapi_url, include_in_schema=False) # Use app.openapi_url here
async def custom_openapi():
    """
    Simulates the functionality of various API endpoints for handling authentication, user information,
    conversation retrieval, message retrieval, and message creation in a backend application. The endpoints
    are implemented using FastAPI and cover actions such as login, logout, fetching user information,
    retrieving conversations/messages, and sending messages.

    The endpoints either serve custom HTML pages (e.g., Swagger UI), or perform database queries to interact
    with messages and conversations. Authentication-related routes also manage session cookies for user sessions.

    :param app: The FastAPI application instance used to define API routes.
    :param include_in_schema: Whether to include this endpoint in the OpenAPI schema.
    :return: A dictionary containing the OpenAPI schema for the API.
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

    :param req: The request object containing the root path and other request scope information.
    :type req: Request
    :return: An HTML response for the Swagger UI page.
    :rtype: HTMLResponse
    """
    root_path = req.scope.get("root_path", "").rstrip("/")
    openapi_url = root_path + app.openapi_url
    return get_swagger_ui_html(
        openapi_url=openapi_url, # URL to the OpenAPI schema
        title=app.title + " - Swagger UI" # Title for the Swagger UI page
    )


@app.post("/api/auth/mock-login", response_model=LoginResponse)
async def mock_login(request: MockLoginRequest, response: Response):
    """
    Handles a mock login process for a user with provided request data. Generates a mock
    user ID based on the email, creates a session, sets the session cookie in the
    response, and returns a successful login response. This is a mocked implementation
    and should be replaced with proper validation and user creation/lookup in production.

    :param request: The login request data containing email information.
    :type request: MockLoginRequest
    :param response: The HTTP response object to which a session cookie is added.
    :type response: Response
    :return: A response model containing user details and a success message.
    :rtype: LoginResponse
    """
    # For now, we'll create a mock user based on the email
    # In production, you'd validate IDP response and get user info
    print(f"Login attempt for: {request.email}")

    # Mock user creation/lookup
    mock_user_id = abs(hash(request.email)) % 10000  # Generate consistent ID from email

    # Create session
    session_key = create_session(mock_user_id, request.email)

    # Set session cookie
    response.set_cookie(
      key="session",
      value=session_key,
      max_age=86400,  # 24 hours
      httponly=True,  # Prevents JS access
      secure=True,    # HTTPS only
      samesite= "lax", # samesite="strict",  # CSRF protection
      path="/"
    )

    print(f"Active sessions: {list(sessions.keys())}")

    return LoginResponse(
      user={
        "id": mock_user_id,
        "email": request.email,
        "name": request.email.split("@")[0].title()  # Mock name from email
      },
      message="Mock login successful"
    )


@app.post("/api/auth/logout")
async def logout(request: Request, response: Response):
    """
    Handles user logout by deleting the session and clearing the session cookie.

    :param request: An instance of ``Request`` containing the HTTP request with
        cookies to retrieve the session ID.
    :param response: An instance of ``Response`` used to delete the session cookie
        and send the response back to the client.
    :return: A dictionary message with a confirmation of successful logout.
    :rtype: dict
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

    This function is an endpoint for retrieving the authenticated user's
    information. It depends on the `get_current_user` function to obtain
    the user's data and returns it as part of the response. The user data
    is expected to include all the relevant details of the currently
    authenticated user in dictionary format.

    :param current_user: A dictionary object that contains data about
        the currently authenticated user. This is automatically retrieved
        via dependency injection using `Depends(get_current_user)`.
    :return: A dictionary containing the "user" key, holding the details
        of the currently authenticated user.
    """
    return {"user": current_user}


# API endpoints
@app.get("/api/conversation/byuserid/{user_id}",
         response_model=List[ConversationResponse], # Defines the expected response structure
         responses={ # Documents possible responses
             status.HTTP_204_NO_CONTENT: {"description": "No conversations found or no messages in conversation"},
             status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "User ID missing"},
             status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Internal server error"}
         },
         tags=["Conversation"]) # Groups this endpoint under "Conversation" in Swagger UI
async def get_conversations(user_id: int, response: Response, current_user: dict = Depends(get_current_user)):
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
