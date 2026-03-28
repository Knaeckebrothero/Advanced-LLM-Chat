"""
This is a mockup of a backend server for a chat application.
It provides a simple API for sending and receiving messages in a conversation.
The server uses SQLite as a database to store messages and conversation data.
The server also uses Replicate to generate AI responses to messages in a conversation.
"""

import asyncio
import hashlib
import json
import logging
import os
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager, asynccontextmanager
from datetime import datetime, timedelta, UTC
from pathlib import Path
from typing import List, Dict, Optional, Union, Literal

import replicate
import trustme
from dotenv import load_dotenv, find_dotenv
from fastapi import (
  FastAPI,
  Response,
  status,
  Request,
  HTTPException,
  Depends,
  UploadFile,
  File,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Default settings for LLM generation
DEFAULT_MODEL = "openai/gpt-4o"
DEFAULT_TEMPERATURE = 0.5
DEFAULT_TOP_P = 0.5
DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant!"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Main application logger
logger = logging.getLogger(__name__)

# Security logger with separate handler
security_logger = logging.getLogger("security")
security_logger.setLevel(logging.WARNING)

# CRUD operations logger
crud_logger = logging.getLogger("crud")
crud_logger.setLevel(logging.INFO)

# Create a file handler for security events
security_log_path = os.path.join(os.getenv("DB_DIR", "."), "security.log")
security_handler = logging.FileHandler(security_log_path)
security_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
security_logger.addHandler(security_handler)

# Create a file handler for CRUD operations
crud_log_path = os.path.join(os.getenv("DB_DIR", "."), "crud_operations.log")
crud_handler = logging.FileHandler(crud_log_path)
crud_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s")
)
crud_logger.addHandler(crud_handler)


def log_security_event(event_type: str, details: dict, request: Request = None):
    """
    Logs a security event with details and optional request information. This
    function creates a structured log entry containing the type of event, the
    event details, and timestamp. If a request object is provided, it includes
    information about the request such as HTTP method, URL path, client host,
    and specific headers. All log entries are serialized to JSON format and
    logged with a warning level.

    :param event_type: Type of the security event.
    :type event_type: str
    :param details: A dictionary containing the details of the event.
    :type details: dict
    :param request: Optional HTTP request data associated with the event.
    :type request: Request or None
    :return: None
    """
    log_entry = {
        "event_type": event_type,
        "timestamp": datetime.now(UTC).isoformat(),
        "details": details,
    }

    if request:
        log_entry["request_info"] = {
            "method": request.method,
            "path": str(request.url.path),
            "client_host": request.client.host if request.client else "unknown",
            "headers": {
                "user-agent": request.headers.get("user-agent", "unknown"),
                "origin": request.headers.get("origin", "unknown"),
            },
        }

    security_logger.warning(json.dumps(log_entry))


class ErrorResponse(BaseModel):
    """
    Represents an error response model for handling error details.

    This class is used to encapsulate error information, typically to be
    used in API responses to provide a standard error structure.

    :ivar error: The error description message that provides details
                 about the nature of the error.
    :type error: str
    """

    error: str


class MockLoginRequest(BaseModel):
    """
    Represents a mock login request.

    This class is utilized for creating a mock representation of a login
    request. It can be extended or used in testing environments to simulate
    user login with essential credentials or tokenized data.

    :ivar email: The email address of the user attempting to login.
    :type email: str
    """

    email: str
    # In real implementation, this might include IDP tokens, SAML response, etc.


class GuestLoginRequest(BaseModel):
    """
    Represents a request for guest login.

    This class is used to encapsulate the data required for a guest login request,
    including any relevant details necessary for processing the request. Guests
    are typically users who do not have registered accounts but need limited access
    to the system or application.

    :ivar ip_address: IP address of the guest initiating the login request.
    :type ip_address: str
    """

    ip_address: str


class LoginResponse(BaseModel):
    """
    Represents the response after a successful login attempt.

    This class models the structure of a typical login response, providing
    details about the user, an accompanying message, and an optional token
    for authentication. It serves as the return type for login operations
    and ensures standardized output.

    :ivar user: A dictionary containing the authenticated user's details.
    :type user: dict
    :ivar message: A message conveying information about the login operation.
    :type message: str
    :ivar token: An optional token for authenticating subsequent requests.
    :type token: Optional[str]
    """

    user: dict
    message: str
    token: Optional[str] = None


class ConversationState(BaseModel):
    """
    Represents the state of a conversation.

    This class is used to store and manage the state of a conversation,
    including its unique identifier and a hash sum for state validation
    or integrity purposes. This serves as a foundational structure
    within a conversational application.

    :ivar id: Unique identifier for the conversation.
    :type id: str
    :ivar hashsum: Hash value used for validation or state integrity checks.
    :type hashsum: int
    """

    id: str  # Now using UUID
    hashsum: int


class ApiConversationsCheck(BaseModel):
    """
    Represents the API response for checking the state of multiple conversations.

    This class is used to encapsulate the details related to the state of
    conversations fetched from the API. It extends from BaseModel and ensures
    that conversations are managed in a structured and clear format.

    :ivar conversations: A list containing the state of multiple conversations.
    :type conversations: List[ConversationState]
    """

    conversations: List[ConversationState]


class FileReference(BaseModel):
    """
    Represents a reference to a file with its metadata.

    The FileReference class acts as a model for storing and managing metadata
    related to a file, such as its identifier, name, size, and MIME type.
    This class is used to simplify the organization and retrieval of file
    information in applications interacting with file systems or APIs.

    :ivar id: Unique identifier for the file.
    :type id: str
    :ivar name: Name of the file.
    :type name: str
    :ivar size: Size of the file in bytes.
    :type size: int
    :ivar mimeType: MIME type of the file.
    :type mimeType: str
    """

    id: str
    name: str
    size: int
    mimeType: str


class TextContent(BaseModel):
    """
    Represents a text content model containing text and optional attachments.

    This class is designed to encapsulate textual content and its associated
    attachments, allowing for structured storage and processing.

    :ivar content: Textual content to be stored or processed.
    :type content: str
    :ivar attachments: List of file references associated with the content.
    :type attachments: Optional[List[FileReference]]
    """

    content: str
    attachments: Optional[List[FileReference]] = []


class VoiceContent(BaseModel):
    """
    Represents the content of a voice message including its audio data,
    metadata, and optional details such as transcript or waveform.

    This class serves as a data model for encapsulating audio-related
    information. It contains attributes like the base64-encoded audio data,
    the duration of the audio, and its MIME type. Additional optional
    attributes allow storage of the audio's transcript and waveform data.

    :ivar audioData: Base64 encoded audio data representing the voice content.
    :type audioData: str
    :ivar duration: Duration of the audio in seconds.
    :type duration: float
    :ivar mimeType: MIME type of the audio file (e.g., "audio/wav").
    :type mimeType: str
    :ivar transcript: Optional text transcript of the audio content.
    :type transcript: Optional[str]
    :ivar waveform: Optional list representing the audio waveform data.
    :type waveform: Optional[List[float]]
    """

    audioData: str  # Base64 encoded audio
    duration: float
    mimeType: str
    transcript: Optional[str] = None
    waveform: Optional[List[float]] = None


class ApiMessageSend(BaseModel):
    """
    Represents a message being sent via the API.

    This class is used to encapsulate all required and optional data for sending
    a message. It supports different message types such as text and voice, allowing
    for flexibility in content representation. Additional metadata includes
    timestamps and versioning for better traceability and compatibility.

    :ivar conversationId: Unique identifier for the conversation, implemented as a UUID.
    :type conversationId: str
    :ivar roleName: The role name of the sender in the conversation (e.g., user,
        assistant).
    :type roleName: str
    :ivar type: The type of message being sent, restricted to "text" or "voice".
    :type type: Literal["text", "voice"]
    :ivar content: The content of the message. For legacy purposes, this can be a
        string, while for enhanced functionality, it can be an object of TextContent
        or VoiceContent.
    :type content: Union[str, TextContent, VoiceContent]
    :ivar time: The timestamp of when the message was created, expressed as an
        integer.
    :type time: int
    :ivar version: Optional integer indicating the version of the message format
        being used. Defaults to 1.
    :type version: Optional[int]
    :ivar lastModified: Optional integer indicating the timestamp of the last
        modification to the message. If not specified, it defaults to None.
    :type lastModified: Optional[int]
    """

    conversationId: str  # Now using UUID
    roleName: str
    type: Literal["text", "voice"]
    content: Union[
        str, TextContent, VoiceContent
    ]  # Backwards compatible - str for legacy, objects for new types
    time: int
    version: Optional[int] = 1
    lastModified: Optional[int] = None


class ApiMessageGenerate(BaseModel):
    """
    Represents a message to be generated in an API context.

    This model is used to encapsulate all the necessary information needed
    to generate a message within the API. It includes details about the
    conversation, the participant's role, and other optional configuration
    settings for message generation.

    :ivar conversationId: Unique identifier for the conversation.
                           Formerly using UUID for representation.
    :type conversationId: str
    :ivar roleName: Name of the role for the entity involved in the
                    conversation (e.g., "user" or "assistant").
    :type roleName: str
    :ivar time: Specifies the timestamp associated with the conversation.
    :type time: int
    :ivar temperature: Optional parameter for controlling randomness in
                       message generation.
    :type temperature: float, optional
    :ivar top_p: Optional parameter for nucleus sampling, determining
                 the probability mass of tokens considered.
    :type top_p: float, optional
    :ivar systemPrompt: Optional system-provided prompt that guides the
                        conversation context.
    :type systemPrompt: str, optional
    """

    conversationId: str  # Now using UUID
    roleName: str
    time: int
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    systemPrompt: Optional[str] = None


class ApiMessageSendAndGenerate(BaseModel):
    """
    Represents a message to be sent in a conversation, along with specific parameters
    for generating a response.

    This class is used to format and validate data for sending messages within a
    conversation. It provides attributes to define the conversation details,
    message type, and content, as well as options for response generation. The
    provided data will be used by the system to manage, process, and optionally
    generate responses within a dialogue environment.

    :ivar conversationId: Unique identifier of the conversation.
    :type conversationId: str
    :ivar roleName: Role name for the sender of the message.
    :type roleName: str
    :ivar type: Type of the message (either "text" or "voice").
    :type type: Literal["text", "voice"]
    :ivar content: The content of the message, which may be a string, text content,
        or voice content.
    :type content: Union[str, TextContent, VoiceContent]
    :ivar time: The timestamp of the message in seconds since the epoch.
    :type time: int
    :ivar version: (Optional) Version of the message format. Defaults to 1 if not
        provided.
    :type version: Optional[int]
    :ivar lastModified: (Optional) Timestamp when the message was last modified, in
        seconds since the epoch.
    :type lastModified: Optional[int]
    :ivar generateResponse: Boolean flag indicating whether to generate a response
        for the sent message. Defaults to True if not provided.
    :type generateResponse: bool
    :ivar aiParticipant: Name of the AI participant associated with the message.
        Defaults to "Assistant".
    :type aiParticipant: str
    """

    conversationId: str
    roleName: str
    type: Literal["text", "voice"]
    content: Union[str, TextContent, VoiceContent]
    time: int
    version: Optional[int] = 1
    lastModified: Optional[int] = None
    generateResponse: bool = True
    aiParticipant: str = "Assistant"


class MessagePatch(BaseModel):
    """
    Represents a patch or update to a specific message within a conversation.

    This class is designed to apply changes to existing messages. Each instance
    represents a modification that can be identified, tracked, and validated.
    It also includes support for optimistic locking to handle simultaneous
    updates and ensure data consistency.

    :ivar id: The unique identifier of the message.
    :type id: int
    :ivar conversationId: The identifier of the conversation to which the
        message belongs. It uses a UUID format for unique identification.
    :type conversationId: str
    :ivar content: The updated content of the message.
    :type content: str
    :ivar version: The version number of the update used for optimistic
        locking. Ensures that concurrent updates do not overwrite changes.
    :type version: int
    """

    id: int
    conversationId: str  # Now using UUID
    content: str
    version: int  # Required for optimistic locking


class MessageResponse(BaseModel):
    """
    Represents a structured response message within a conversation.

    This class models a message with associated metadata, including
    conversation context, role assignment, content, timestamps, and
    optional attributes like type, version, lastModified time, and rating.

    :ivar id: Unique identifier for the message.
    :type id: int
    :ivar conversationId: Identifier of the associated conversation, typically
        a UUID formatted string.
    :type conversationId: str
    :ivar roleName: Role indicating the sender's identity or purpose in the
        conversation (e.g., "user", "assistant").
    :type roleName: str
    :ivar content: Actual message content or body.
    :type content: str
    :ivar time: UNIX epoch timestamp of when the message was created.
    :type time: int
    :ivar type: Optional type of the message for categorization, such as "text".
        Defaults to "text" for backwards compatibility.
    :type type: Optional[str]
    :ivar version: Version of the message structure. Defaults to 1.
    :type version: int
    :ivar lastModified: Optional UNIX epoch timestamp of the last modification
        made to the message.
    :type lastModified: Optional[int]
    :ivar rating: Optional user-provided rating of the message. 1 indicates
        thumbs up, 0 indicates thumbs down, and None indicates unrated.
    :type rating: Optional[int]
    """

    id: int
    conversationId: str  # Now using UUID
    roleName: str
    content: str
    time: int
    type: Optional[str] = "text"  # Default to "text" for backwards compatibility
    version: int = 1
    lastModified: Optional[int] = None
    rating: Optional[int] = None  # 1 for thumbs up, 0 for thumbs down, None for unrated


class SendAndGenerateResponse(BaseModel):
    """
    Represents a model for sending and generating responses, combining both user and AI messages.

    This class encapsulates a user message along with an optional AI message, providing a structure
    to process and store conversations. It is primarily designed to handle and manage the interaction
    between users and an AI system.

    :ivar userMessage: The message sent by the user.
    :type userMessage: MessageResponse
    :ivar aiMessage: The message generated by the AI, if available.
    :type aiMessage: Optional[MessageResponse]
    """

    userMessage: MessageResponse
    aiMessage: Optional[MessageResponse] = None


class ConversationResponse(BaseModel):
    """
    Represents the response of a conversation with its associated details.

    This model encapsulates the details of a conversation including its unique
    identifier, associated user ID, participants, timestamps, and versioning
    information. It is designed to manage and model conversation-related data
    within the system.

    :ivar id: A unique identifier for the conversation.
    :type id: str
    :ivar userId: The ID of the user associated with this conversation.
    :type userId: int
    :ivar name: The name of the conversation.
    :type name: str
    :ivar participants: A list of participants involved in the conversation.
    :type participants: List[str]
    :ivar createdAt: The timestamp when the conversation was created.
    :type createdAt: datetime
    :ivar updatedAt: The timestamp when the conversation was last updated.
    :type updatedAt: datetime
    :ivar hashsum: A computed hash value representing the conversation data.
    :type hashsum: int
    :ivar version: The version number of the conversation data model.
    :type version: int
    :ivar lastModified: An optional timestamp when the conversation was last
        modified.
    :type lastModified: Optional[int]
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
    """
    Represents a conversation entity.

    This class models a conversation instance, storing data such as its identifier,
    the associated user who initiated or owns the conversation, the name of the
    conversation, optional participants, and timestamps for when it was created
    and last updated.

    :ivar id: Unique identifier for the conversation.
    :type id: str
    :ivar userId: Identifier of the user associated with the conversation.
    :type userId: int
    :ivar name: Display name for the conversation.
    :type name: str
    :ivar participants: Optional string representing additional participants in
        the conversation.
    :type participants: Optional[str]
    :ivar createdAt: Timestamp indicating when the conversation was created.
    :type createdAt: datetime
    :ivar updatedAt: Timestamp indicating the last time the conversation was
        updated.
    :type updatedAt: datetime
    """

    id: str
    userId: int
    name: str
    participants: Optional[str] = None
    createdAt: datetime
    updatedAt: datetime


class ConversationCreateRequest(BaseModel):
    """
    Represents a request to create a new conversation.

    This class is used to encapsulate the necessary data for creating a new
    conversation, including the name of the conversation and the list of participants.

    :ivar name: The name of the conversation to be created.
    :type name: str
    :ivar participants: A list of participants to be included in the conversation.
    :type participants: List[str]
    """

    name: str
    participants: List[str]


class RateMessageRequest(BaseModel):
    """
    Represents a request to rate a message in a conversation.

    This request model is used to capture user feedback on a specific message within a
    conversation. The feedback is stored as a rating value representing a "thumbs up,"
    "thumbs down," or the removal of a rating. The purpose of this model is to provide a
    standardized structure for transmitting rating data.

    1 for thumbs up, 0 for thumbs down, None to remove rating

    :ivar id: Unique identifier for the rate message request.
    :type id: int
    :ivar conversationId: Unique identifier for the conversation, typically in UUID format.
    :type conversationId: str
    :ivar rating: Feedback rating for the message, where 1 represents a thumbs up, 0 represents
        a thumbs down, and None indicates the removal of the rating.
    :type rating: Optional[int]
    """

    id: int
    conversationId: str  # UUID
    rating: Optional[int] = Field(None, ge=0, le=1)


class RegenerateMessageRequest(BaseModel):
    """
    Represents a request to regenerate a message within a specific conversation.

    This class is a model that encapsulates the data required to request the
    regeneration of a message. It contains the unique identifiers for the
    message and the associated conversation.

    :ivar id: Unique identifier for the message to be regenerated.
    :type id: int
    :ivar conversationId: Unique identifier for the conversation associated
                          with the request.
    :type conversationId: str
    """

    id: int
    conversationId: str  # UUID


class AppSettings(BaseModel):
    """
    Manages application settings such as theme and language preferences.

    Provides storage for user-specified application configurations, enabling
    customization of the application behavior and appearance.

    :ivar theme: The theme preference of the user.
    :type theme: str
    :ivar language: The language preference of the user.
    :type language: str
    """

    theme: str
    language: str


class AppSettingsResponse(AppSettings):
    """
    Represents the response format for application settings, extending the
    base application settings functionality.

    This class incorporates additional metadata regarding the last update time
    of the settings, stored as a Unix timestamp.

    :ivar lastUpdated: Indicates the Unix timestamp of the last update to the
        application settings.
    :type lastUpdated: int
    """

    lastUpdated: int  # Unix timestamp


class ConversationWithDetails(Conversation):
    """
    Represents a conversation with additional details about its state or metadata.

    This class extends the base `Conversation` class, adding optional attributes
    that provide more detailed information about the conversation, such as the
    last modification timestamp, the count of messages within the conversation,
    and a synchronization hash value typically used for data consistency.

    :ivar lastModified: The timestamp indicating when the conversation was last modified.
    :type lastModified: Optional[datetime]
    :ivar messageCount: The number of messages included in the conversation.
    :type messageCount: Optional[int]
    :ivar syncHash: A hash value used for synchronization or data integrity checking.
    :type syncHash: Optional[str]
    """

    lastModified: Optional[datetime] = None
    messageCount: Optional[int] = None
    syncHash: Optional[str] = None


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
    conn = sqlite3.connect(DB_PATH)  # Changed from 'chat.db' to DB_PATH
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages the lifespan of the application by performing necessary asynchronous
    tasks such as cleanup of expired sessions.

    This function ensures that the application lifecycle includes running specific
    background tasks that are necessary for maintaining the application's state or
    resources.

    :param app: FastAPI application instance to attach the lifespan context to.
    :type app: FastAPI
    :return: Async generator for managing application lifespan.
    :rtype: AsyncGenerator
    """
    asyncio.create_task(cleanup_expired_sessions())
    yield


def generate_session_key(length=32) -> str:
    """
    Generates a securely random session key.

    This function creates a session key using a cryptographic random
    number generator. The key is returned in a URL-safe format and is
    suitable for use in session management and other scenarios where a
    secure, non-guessable token is required.

    :param length: The desired length of the generated session key, where
                   the length refers to the number of characters in the
                   resulting string. Defaults to 32.
    :type length: int

    :return: A URL-safe, randomly generated session key.
    :rtype: str
    """
    return secrets.token_urlsafe(length)


def generate_conversation_id() -> str:
    """
    Generates a unique conversation identifier.

    This function creates a unique identifier for a conversation using a UUID
    (Universally Unique Identifier). It ensures the generated ID is globally
    unique.

    :returns: A unique string identifier for a conversation.
    :rtype: str
    """
    return str(uuid.uuid4())


def generate_csrf_token() -> str:
    """
    Generates a secure random CSRF token.

    This function leverages the `secrets` module to generate a cryptographically
    secure, URL-safe token that can be used as a CSRF (Cross-Site Request Forgery)
    token in web applications. The generated token has high entropy and is suitable
    for security-sensitive contexts to protect against CSRF attacks.

    :return: A cryptographically secure, URL-safe token for CSRF protection
    :rtype: str
    """
    return secrets.token_urlsafe(32)


def create_session(
    user_id: int,
    user_email: str,
    session_duration_hours=24,
    is_guest=False,
    regenerate_from=None,
) -> tuple[str, str]:
    """
    Creates and stores a new user session in the database. Optionally regenerates a session
    from an existing one by deleting the old session before creation.

    :param user_id: The unique identifier of the user for whom the session is being created.
    :type user_id: int
    :param user_email: The email address associated with the user's account.
    :type user_email: str
    :param session_duration_hours: The duration in hours for which the session remains valid.
        Defaults to 24 hours.
    :type session_duration_hours: int
    :param is_guest: Flag indicating whether the session is for a guest user. Defaults to False.
    :type is_guest: bool
    :param regenerate_from: The session key of an existing session to be regenerated. If provided,
        the existing session will be deleted.
    :type regenerate_from: str or None
    :return: A tuple containing the new session key and the CSRF token associated with the session.
    :rtype: tuple[str, str]
    """
    if regenerate_from:
        delete_session(regenerate_from)

    session_key = generate_session_key()
    csrf_token = generate_csrf_token()

    # Use environment variable for session timeout if available
    session_timeout = int(
        os.getenv("SESSION_TIMEOUT_HOURS", str(session_duration_hours))
    )
    expires_at = datetime.now(UTC) + timedelta(hours=session_timeout)

    # Save session to database
    with get_db() as db:
        db.execute(
            """
      INSERT INTO sessions (session_key, user_id, email, expires_at, is_guest, csrf_token)
      VALUES (?, ?, ?, ?, ?, ?)
      """,
            (
                session_key,
                user_id,
                user_email,
                expires_at.isoformat(),
                is_guest,
                csrf_token,
            ),
        )

        db.commit()

    return session_key, csrf_token


def validate_session(session_key: str) -> Optional[dict]:
    """
    Validates the session using the provided session key by checking its existence and expiration status
    in the database. If validation succeeds, updates the last activity timestamp and calculates the
    remaining time until expiry.

    :param session_key: The session key used to identify the session in the database.
    :type session_key: str

    :return: A dictionary with session details if the session is valid, or None if the session does
             not exist or is expired.
    :rtype: Optional[dict]
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
      """,
            (session_key,),
        )
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
        cur.execute(
            """
                UPDATE sessions
                SET last_activity = ?
                WHERE session_key = ?
                """,
            (current_time.isoformat(), session_key),
        )
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
            "expires_in": expires_in_seconds,
        }


def delete_session(session_key: str):
    """
    Deletes a session from the database matching the supplied session key.

    This function is used to remove a specific session record from the sessions table
    in the database. It performs a deletion query using the provided session key and
    commits the changes to ensure the session is successfully removed.

    :param session_key: The key identifying the session to be deleted from the database.
    :type session_key: str
    :return: None
    """
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM sessions WHERE session_key = ?", (session_key,))
        conn.commit()


async def validate_csrf_token(request: Request) -> bool:
    """
    Validates the CSRF token submitted via the HTTP request. This function
    implements CSRF protection using the double-submit pattern, ensuring requests
    are authorized and preventing cross-site request forgery attacks. Specifically,
    it checks if the CSRF token provided in the request header matches the CSRF
    token stored in the cookie. Additionally, it bypasses CSRF validation for
    certain safe HTTP methods and specific authentication endpoints.

    :param request: The incoming HTTP request object containing data related to
        headers, method, URL, and cookies.
    :type request: Request
    :return: A boolean value indicating whether the CSRF token validation passed
        or failed. Returns True if validation bypass conditions are met or if
        tokens match; otherwise, returns False.
    :rtype: bool
    """
    # Skip CSRF validation for safe methods
    if request.method in ["GET", "HEAD", "OPTIONS"]:
        return True

    # Skip CSRF validation for authentication endpoints
    if request.url.path in [
        "/api/auth/mock-login",
        "/api/auth/guest-login",
        "/api/auth/logout",
        "/api/auth/refresh-session",
    ]:
        return True

    # Get CSRF token from cookie
    csrf_token_cookie = request.cookies.get("csrf_token")
    if not csrf_token_cookie:
        log_security_event(
            "csrf_validation_failed",
            {
                "reason": "missing_csrf_cookie",
                "session_cookie_present": "session" in request.cookies,
            },
            request,
        )
        return False

    # Get CSRF token from header
    csrf_token_header = request.headers.get("X-CSRF-Token")
    if not csrf_token_header:
        log_security_event(
            "csrf_validation_failed",
            {
                "reason": "missing_csrf_header",
                "session_cookie_present": "session" in request.cookies,
            },
            request,
        )
        return False

    # Compare tokens (double-submit pattern)
    is_valid = csrf_token_cookie == csrf_token_header
    if not is_valid:
        log_security_event(
            "csrf_validation_failed",
            {
                "reason": "token_mismatch",
                "cookie_token_length": len(csrf_token_cookie),
                "header_token_length": len(csrf_token_header),
                "session_cookie_present": "session" in request.cookies,
            },
            request,
        )

    return is_valid


async def get_current_user(request: Request) -> dict:
    """
    Retrieves the current user's information based on the session cookie in the supplied request.
    If the session cookie is missing or invalid, an HTTP 401 error is raised. This is typically
    used for authentication purposes.

    :param request: An instance of `Request` containing the client's HTTP request. This includes
        necessary information like cookies for identifying the user's session.
    :return: A dictionary containing user information retrieved from the validated session.
    :rtype: dict
    :raises HTTPException: If the session cookie is missing or the session is invalid/expired,
        the function raises an HTTP error with status code 401 (Unauthorized).
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
    Asynchronously retrieves the currently authenticated user from the provided request object.
    In case the user is not authenticated or an HTTP exception occurs, it returns None.

    :param request: The request object used to fetch the current authenticated user.
    :type request: Request
    :return: A dictionary containing the current user's information if available, otherwise None.
    :rtype: Optional[dict]
    """
    try:
        return await get_current_user(request)
    except HTTPException:
        return None


async def cleanup_expired_sessions():
    """
    Periodically cleans up expired sessions from the database. This function runs in
    an infinite loop, purging sessions with expiration dates earlier than the
    current time. It executes this cleanup process every hour.

    :return: None
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
    Initializes the database by creating necessary tables, indices, and triggers, as well as modifying
    tables to add new columns if they are missing. Existing data migrations and structural changes are
    also handled to enhance database schema integrity and functionality.

    :raises Exception: If the database connection or operations fail.
    :returns: None
    """
    with get_db() as conn:
        cur = conn.cursor()

        # Create users table
        cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                                                   id INTEGER PRIMARY KEY,
                                                   email TEXT UNIQUE NOT NULL,
                                                   name TEXT,
                                                   created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """)

        # Create conversations table with UUID support
        cur.execute("""
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
                """)

        # Create messages table to store chat messages
        cur.execute("""
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
                """)

        # Create sessions table to manage user sessions
        cur.execute("""
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
                """)

        # Check if is_guest column exists, if not add it (for existing databases)
        cur.execute("PRAGMA table_info(sessions)")
        columns = [column[1] for column in cur.fetchall()]
        if "is_guest" not in columns:
            print("Adding is_guest column to sessions table...")
            cur.execute(
                "ALTER TABLE sessions ADD COLUMN is_guest BOOLEAN DEFAULT FALSE"
            )

        # Check if csrf_token column exists, if not add it
        if "csrf_token" not in columns:
            print("Adding csrf_token column to sessions table...")
            cur.execute("ALTER TABLE sessions ADD COLUMN csrf_token TEXT")

        # Check if type column exists in messages table, if not add it
        cur.execute("PRAGMA table_info(messages)")
        columns = [column[1] for column in cur.fetchall()]
        if "type" not in columns:
            print("Adding type column to messages table...")
            cur.execute("ALTER TABLE messages ADD COLUMN type TEXT DEFAULT 'text'")

        # Add version columns for optimistic locking
        if "version" not in columns:
            print("Adding version column to messages table...")
            cur.execute("ALTER TABLE messages ADD COLUMN version INTEGER DEFAULT 1")

        if "lastModified" not in columns:
            print("Adding lastModified column to messages table...")
            cur.execute("ALTER TABLE messages ADD COLUMN lastModified INTEGER")

        # Check conversations table for version columns
        cur.execute("PRAGMA table_info(conversations)")
        columns = [column[1] for column in cur.fetchall()]
        if "version" not in columns:
            print("Adding version column to conversations table...")
            cur.execute(
                "ALTER TABLE conversations ADD COLUMN version INTEGER DEFAULT 1"
            )

        if "lastModified" not in columns:
            print("Adding lastModified column to conversations table...")
            cur.execute("ALTER TABLE conversations ADD COLUMN lastModified INTEGER")

        # Create guest_usage table
        cur.execute("""
                CREATE TABLE IF NOT EXISTS guest_usage (
                                                         ip_address TEXT PRIMARY KEY,
                                                         request_count INTEGER NOT NULL,
                                                         last_request_at TIMESTAMP NOT NULL
                )
                """)

        # Create index for faster querying by conversationId and time
        cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversation_time
                  ON messages(conversationId, time)
                """)

        # Create index for faster querying by userId on conversations
        cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversations_user
                  ON conversations(userId)
                """)

        conn.commit()

        # Create Table for user-based settings
        cur.execute("""
                CREATE TABLE IF NOT EXISTS user_settings (
                                                           user_id INTEGER PRIMARY KEY,
                                                           theme TEXT NOT NULL,
                                                           language TEXT NOT NULL,
                                                           updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """)

        # Add updated_at column to messages table if it doesn't exist
        cur.execute("PRAGMA table_info(messages)")
        columns = [column[1] for column in cur.fetchall()]
        if "updated_at" not in columns:
            print("Adding updated_at column to messages table...")
            cur.execute(
                "ALTER TABLE messages ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            )

        # Add updated_at column to user_settings table if it doesn't exist
        cur.execute("PRAGMA table_info(user_settings)")
        columns = [column[1] for column in cur.fetchall()]
        if "updated_at" not in columns:
            print("Adding updated_at column to user_settings table...")
            cur.execute(
                "ALTER TABLE user_settings ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            )

        # Add rating column to messages table if it doesn't exist
        cur.execute("PRAGMA table_info(messages)")
        columns = [column[1] for column in cur.fetchall()]
        if "rating" not in columns:
            print("Adding rating column to messages table...")
            cur.execute("ALTER TABLE messages ADD COLUMN rating INTEGER")

        # Create trigger to update conversations timestamp
        cur.execute("""
                CREATE TRIGGER IF NOT EXISTS update_conversations_timestamp
                AFTER UPDATE ON conversations
                BEGIN
                UPDATE conversations SET updatedAt = CURRENT_TIMESTAMP WHERE id = NEW.id;
                END;
                """)

        # Create trigger to update messages timestamp
        cur.execute("""
                CREATE TRIGGER IF NOT EXISTS update_messages_timestamp
                AFTER UPDATE ON messages
                BEGIN
                UPDATE messages SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
                END;
                """)

        # Create trigger to update user_settings timestamp
        cur.execute("""
                CREATE TRIGGER IF NOT EXISTS update_user_settings_timestamp
                AFTER UPDATE ON user_settings
                BEGIN
                UPDATE user_settings SET updated_at = CURRENT_TIMESTAMP WHERE user_id = NEW.user_id;
                END;
                """)

        conn.commit()


def setup_development_certificates():
    """
    Sets up development SSL certificates for local use.

    This function generates a certificate authority (CA) using `trustme`, issues a
    server certificate for `localhost`, and saves the certificates and associated
    keys to a directory named `devcerts`. If the directory already exists, it will
    not be recreated.

    :return: A tuple containing the file paths of the generated server certificate
        (as `.pem` file) and private server key (as `.key` file).
    :rtype: tuple[str, str]
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
    Generate a hash value based on the content of given messages. The hash value is
    calculated using the first and last characters of each message's content, as well
    as its length. A string representation of these hash components is also created
    and logged.

    :param messages: List of SQLite rows, where each row represents a message and
                     contains a 'content' field.
    :type messages: List[sqlite3.Row]
    :return: An integer hash value computed from the messages' content.
    :rtype: int
    """
    if not messages:
        return 0

    hash_value = 0
    hash_chars = ""

    for message in messages:
        content = message["content"]
        if not content:
            hash_value += 0
            continue

        hash_value += ord(content[0])
        hash_value += ord(content[-1])
        hash_value *= len(content)
        hash_chars += content[0] + content[-1] + str(len(content))

    hash_value %= 2**32
    print(f"Generated hashsum: {hash_value} string rep: {hash_chars}")
    return hash_value


def generate_sha256_hash(content: str) -> str:
    """
    Generates a SHA-256 hash for the given content. The function encodes the
    provided string content using UTF-8 before calculating the hash and returns
    the hexdigest representation of the computed SHA-256 hash value.

    :param content: The input string to be hashed.
    :type content: str
    :return: The SHA-256 hash of the input string in hexadecimal format.
    :rtype: str
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


async def generate_llm_response(
    prompt: str, temperature: float, top_p: float, system_prompt: str, model: str
) -> str:
    """
    Generates a response from a Large Language Model (LLM) using the specified parameters. This
    function connects to and utilizes a specified LLM model through the Replicate API,
    allowing users to customize the response generation process with additional
    parameters like temperature, top_p, and a system-level prompt. The function
    supports generating responses up to the limit of 1024 tokens in a single call.

    Any errors during the response generation will result in a fallback message,
    informing the user about the failure.

    :param prompt: The main input text that the LLM will use to generate its response.
    :param temperature: A parameter affecting randomness in responses. Higher values
        translate to more creative and diverse outputs, while lower values produce
        more deterministic completions.
    :param top_p: Controls nucleus sampling for response generation. The LLM considers
        the smallest subset of words whose cumulative probability exceeds `top_p`.
    :param system_prompt: A system-wide prompt applied to the LLM setting additional
        context or constraints for response generation.
    :param model: The identifier of the LLM model to be used from the Replicate service.
    :return: A synthesized text response generated by the LLM model.
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
            },
        )
        print(
            "\n".join(
                [
                    "LLM Input:",
                    f"  model = {model}",
                    f"  temp = {temperature}",
                    f"  top_p = {top_p}",
                    f"  system_prompt = {system_prompt}",
                    "  prompt:",
                    prompt,
                ]
            )
        )

        # Replicate returns a generator, collect all parts of the streamed response
        return "".join(output)
    except Exception as e:
        print(f"Error generating response: {str(e)}")
        return "I apologize, but I encountered an error generating a response."


async def get_conversation_context(conversation_id: str, limit: int = 5) -> str:
    """
    Retrieve the context of a conversation based on a given conversation ID and
    optional limit on the number of messages. The messages are fetched in
    descending order of time and then reversed to construct the context in
    correct chronological order.

    The method builds a context string by iterating through the fetched messages
    and combining their role names and contents. The resulting string represents
    the ordered conversation history.

    :param conversation_id: Unique identifier for the conversation.
    :type conversation_id: str
    :param limit: Maximum number of messages to include in the context. Defaults to 5.
    :type limit: int
    :return: A formatted string containing conversation history with role names and contents in chronological order. If an error occurs, an empty string is returned.
    :rtype: str
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
                (conversation_id, limit),
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


def verify_conversation_ownership(
    conversation_id: str, user_id: int, is_guest: bool = False
) -> bool:
    """
    Verifies whether the given user ID owns the specified conversation. This function allows guest users
    to access any conversation, typically for offline mode functionality. For non-guest users, it checks
    in the database if the user ID corresponds to the conversation's owner.

    :param conversation_id: The unique identifier of the conversation
    :type conversation_id: str
    :param user_id: The unique identifier of the user
    :type user_id: int
    :param is_guest: Specifies if the user is a guest. Defaults to False.
    :type is_guest: bool, optional
    :return: True if the specified user owns the conversation or if user
        is a guest, otherwise False
    :rtype: bool
    """
    # Guest users can access any conversation (for offline mode)
    if is_guest:
        return True

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT userId FROM conversations WHERE id = ?", (conversation_id,))
        result = cur.fetchone()

        if not result:
            return False

        return result["userId"] == user_id


async def rate_limit_guest(
    request: Request, current_user: Optional[dict] = Depends(get_current_user_optional)
):
    """
    Apply a rate limit mechanism for guest users based on their IP addresses. The function allows a
    maximum number of requests for guest users within a specified time frame. If the limit is exceeded,
    a 429 HTTP status is returned with details about when the user can retry.

    :param request: The HTTP request object containing the request data and client information.
    :type request: Request
    :param current_user: An optional dictionary containing information about the current authenticated
        user. Defaults to None if the user is not authenticated.
    :type current_user: Optional[dict]
    :return: None if no rate limit is applied or the user is not a guest.

    :raises HTTPException: If the guest user exceeds the rate limit, a 429 Too Many Requests error is
        raised, including a Retry-After header with the recommended wait time.
    """
    if current_user and not current_user.get("is_guest"):
        return  # Not a guest, no rate limit

    ip_address = request.client.host
    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            "SELECT request_count, last_request_at FROM guest_usage WHERE ip_address = ?",
            (ip_address,),
        )
        usage = cur.fetchone()

        now = datetime.now(UTC)
        limit_duration = timedelta(hours=3)
        max_requests = 5

        if usage:
            last_request_at = datetime.fromisoformat(usage["last_request_at"])
            if now - last_request_at > limit_duration:
                # Reset counter
                cur.execute(
                    "UPDATE guest_usage SET request_count = 1, last_request_at = ? WHERE ip_address = ?",
                    (now.isoformat(), ip_address),
                )
            elif usage["request_count"] >= max_requests:
                reset_time = last_request_at + limit_duration
                retry_after_seconds = (reset_time - now).total_seconds()
                headers = {"Retry-After": str(int(retry_after_seconds))}
                raise HTTPException(
                    status_code=429,
                    detail=f"Too many requests. Please try again after {reset_time.isoformat()}",
                    headers=headers,
                )
            else:
                cur.execute(
                    "UPDATE guest_usage SET request_count = request_count + 1, last_request_at = ? WHERE ip_address = ?",
                    (now.isoformat(), ip_address),
                )
        else:
            cur.execute(
                "INSERT INTO guest_usage (ip_address, request_count, last_request_at) VALUES (?, 1, ?)",
                (ip_address, now.isoformat()),
            )
        db.commit()


# Load environment variables from .env file
load_dotenv(find_dotenv())

# Database configuration
DB_DIR = os.getenv("DB_DIR", "./data")
Path(DB_DIR).mkdir(exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "chat.db")

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
    lifespan=lifespan,
)

# Initialize the database on startup
init_db()


@app.get(app.openapi_url, include_in_schema=False)
async def custom_openapi():
    """
    Generates a custom OpenAPI schema for the FastAPI app.

    This function overrides the existing OpenAPI schema generation for the FastAPI
    application. It utilizes the `get_openapi` utility to create a custom schema
    using the app's metadata such as title, version, description, and registered
    routes.

    :return: The custom-generated OpenAPI schema as a dictionary.
    :rtype: dict
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
    Generates and serves a custom Swagger UI HTML interface for the API.

    Provides a user interface to explore the API endpoints and their
    documentation using the Swagger UI. This view is accessible at '/api/docs'
    but is excluded from the schema.

    :param req: The HTTP request object containing metadata about the
        incoming request and connection-specific data.
    :type req: Request
    :return: The HTML response content for the Swagger UI.
    :rtype: HTMLResponse
    """
    root_path = req.scope.get("root_path", "").rstrip("/")
    openapi_url = root_path + app.openapi_url
    return get_swagger_ui_html(
        openapi_url=openapi_url, title=app.title + " - Swagger UI"
    )


@app.post(
    "/api/auth/guest-login",
    response_model=LoginResponse,
    tags=["Auth"],
    summary="Guest Login",
    description="Creates a guest session for anonymous users with rate limiting based on IP address",
    operation_id="guestLogin",
)
async def guest_login(request: GuestLoginRequest, req: Request, response: Response):
    """
    Handles guest login by verifying IP address rate limits, creating a guest session,
    and managing cookies and headers for client authentication and CSRF protection.

    :param request: The request object containing the guest's login details.
    :type request: GuestLoginRequest
    :param req: The incoming HTTP request object used to access request-related data.
    :type req: Request
    :param response: The HTTP response object for setting cookies and headers.
    :type response: Response
    :return: An object containing guest user information, a success message, and the session token.
    :rtype: LoginResponse
    :raises HTTPException: If the rate limit is exceeded based on the guest's IP address.
    """
    ip_address = request.ip_address

    # If IP address is 'unknown', use a fallback
    if ip_address == "unknown":
        ip_address = f"guest_{secrets.token_hex(4)}"

    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            "SELECT request_count, last_request_at FROM guest_usage WHERE ip_address = ?",
            (ip_address,),
        )
        usage = cur.fetchone()

        now = datetime.now(UTC)
        limit_duration = timedelta(hours=3)
        max_requests = 5

        if usage:
            last_request_at = datetime.fromisoformat(usage["last_request_at"])
            if now - last_request_at > limit_duration:
                cur.execute(
                    "UPDATE guest_usage SET request_count = 1, last_request_at = ? WHERE ip_address = ?",
                    (now.isoformat(), ip_address),
                )
            elif usage["request_count"] >= max_requests:
                reset_time = last_request_at + limit_duration
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Please try again after {reset_time.isoformat()}.",
                )
        else:
            cur.execute(
                "INSERT INTO guest_usage (ip_address, request_count, last_request_at) VALUES (?, 1, ?)",
                (ip_address, now.isoformat()),
            )

        db.commit()

    # Get existing session to regenerate from
    old_session_key = req.cookies.get("session")

    guest_email = f"guest_{secrets.token_hex(4)}@guest.com"
    guest_user = {"id": 0, "email": guest_email, "name": "Guest"}

    # Use shorter timeout for guest sessions
    guest_timeout_hours = int(os.getenv("GUEST_SESSION_TIMEOUT_HOURS", "6"))

    # Create new guest session with custom timeout, regenerating old session
    session_key, csrf_token = create_session(
        0,
        guest_email,
        session_duration_hours=guest_timeout_hours,
        is_guest=True,
        regenerate_from=old_session_key,
    )

    max_age = guest_timeout_hours * 3600

    response.set_cookie(
        key="session",
        value=session_key,
        max_age=max_age,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )

    # Set CSRF token as cookie for double-submit pattern
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        max_age=max_age,
        httponly=False,  # JS needs to read this
        secure=True,
        samesite="lax",  # Lax allows cross-site requests from different ports
        path="/",
    )

    # Also set CSRF token in response header for backward compatibility
    response.headers["X-CSRF-Token"] = csrf_token

    # Log successful guest login
    log_security_event(
        "guest_login_success",
        {
            "user_id": guest_user["id"],
            "ip_address": ip_address,
            "guest_timeout_hours": guest_timeout_hours,
        },
        req,
    )

    return LoginResponse(
        user=guest_user, message="Guest login successful", token=session_key
    )


@app.post(
    "/api/auth/mock-login",
    response_model=LoginResponse,
    tags=["Auth"],
    summary="Mock Login",
    description="Mock authentication for testing purposes - creates or retrieves a test user",
    operation_id="mockLogin",
)
async def mock_login(request: MockLoginRequest, req: Request, response: Response):
    """
    Handles the mock login process for a user by creating or retrieving a user in the database,
    generating a session, and setting appropriate cookies and headers for the client. This
    endpoint is typically used for testing authentication workflows.

    :param request: A validated request object containing mock login details, including the
        user's email.
    :type request: MockLoginRequest
    :param req: The incoming HTTP request object that includes session cookies, if any.
    :type req: Request
    :param response: The outgoing response object to set cookies and headers for the client.
    :type response: Response
    :return: A response object containing user data and a success message.
    :rtype: LoginResponse
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
            user_name = request.email.split("@")[0].title()
            cur.execute(
                "INSERT INTO users (email, name) VALUES (?, ?)",
                (request.email, user_name),
            )
            user_id = cur.lastrowid
            db.commit()
        else:
            user_id = user["id"]
            user_name = user["name"]

    # Create session with is_guest=False for regular users, regenerating old session
    session_key, csrf_token = create_session(
        user_id, request.email, is_guest=False, regenerate_from=old_session_key
    )

    # Calculate max_age based on session timeout
    session_timeout_hours = int(os.getenv("SESSION_TIMEOUT_HOURS", "24"))
    max_age = session_timeout_hours * 3600

    # Set session cookie
    response.set_cookie(
        key="session",
        value=session_key,
        max_age=max_age,
        httponly=True,  # Prevents JS access
        secure=True,  # HTTPS only
        samesite="lax",
        path="/",
    )

    # Set CSRF token as cookie for double-submit pattern
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        max_age=max_age,
        httponly=False,  # JS needs to read this
        secure=True,
        samesite="lax",  # Lax allows cross-site requests from different ports
        path="/",
    )

    # Also set CSRF token in response header for backward compatibility
    response.headers["X-CSRF-Token"] = csrf_token

    # Log successful login
    log_security_event(
        "user_login_success",
        {"user_id": user_id, "email": request.email, "new_user": user is None},
        req,
    )

    return LoginResponse(
        user={"id": user_id, "email": request.email, "name": user_name},
        message="Mock login successful",
    )


@app.post(
    "/api/auth/logout",
    tags=["Auth"],
    summary="Logout",
    description="Invalidates the current session and clears authentication cookies",
    operation_id="logout",
)
async def logout(request: Request, response: Response):
    """
    Logs out a user by invalidating the current session key, deleting associated
    cookies, and logging a security event if a valid session exists.

    The function retrieves the session key from the `request` cookies. If a valid
    session is found, it logs the logout event before deleting the session. After
    that, it deletes the `session` and `csrf_token` cookies from the response.

    :param request: The incoming HTTP request containing user session cookies
    :type request: Request
    :param response: The HTTP response object to modify and send back to the client
    :type response: Response
    :return: A confirmation message indicating the successful logout
    :rtype: dict
    """
    session_key = request.cookies.get("session")
    if session_key:
        # Log logout event before deleting session
        session_data = validate_session(session_key)
        if session_data:
            log_security_event(
                "user_logout",
                {"user_id": session_data["user_id"], "email": session_data["email"]},
                request,
            )

        delete_session(session_key)

    # Delete cookies
    response.delete_cookie(
        key="session", path="/", secure=True, httponly=True, samesite="lax"
    )
    response.delete_cookie(
        key="csrf_token", path="/", secure=True, httponly=False, samesite="lax"
    )
    return {"message": "Logged out successfully"}


@app.post(
    "/api/auth/refresh-session",
    tags=["Auth"],
    summary="Refresh Session",
    description="Refreshes the user session if it's close to expiry (within 1 hour)",
    operation_id="refreshSession",
)
async def refresh_session(
    request: Request, response: Response, current_user: dict = Depends(get_current_user)
):
    """
    Refreshes the user session and updates session cookies and CSRF tokens. If the
    session is far from expiry (greater than 1 hour), it does not create a new
    session but instead provides a message indicating no refresh is required. If the
    session is close to expiring or expired, a new session is created with a duration
    that depends on the user's type (guest or regular user), and updated session
    details are returned.

    :param request: FastAPI Request object used to retrieve cookies from the client.
    :type request: Request
    :param response: FastAPI Response object used to set cookies and response headers.
    :type response: Response
    :param current_user: Dictionary containing information about the currently
                         authenticated user, such as user ID, email, and session expiration.
                         Passed as a dependency.
    :type current_user: dict
    :return: A dictionary containing a message about whether the session was refreshed and
             the new session expiration time in seconds.
    :rtype: dict
    """
    session_key = request.cookies.get("session")
    if not session_key:
        raise HTTPException(status_code=401, detail="No session to refresh")

    # Check if session is close to expiring (less than 1 hour)
    expires_in = current_user.get("expires_in", 0)
    if expires_in > 3600:  # More than 1 hour remaining
        return {
            "message": "Session does not need refresh yet",
            "expires_in": expires_in,
        }

    # Create new session with same user info
    user_id = current_user["user_id"]
    email = current_user["email"]
    is_guest = current_user.get("is_guest", False)

    # Determine session duration based on user type
    if is_guest:
        session_hours = int(os.getenv("GUEST_SESSION_TIMEOUT_HOURS", "6"))
    else:
        session_hours = int(os.getenv("SESSION_TIMEOUT_HOURS", "24"))

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
        path="/",
    )

    # Set CSRF token as cookie for double-submit pattern
    response.set_cookie(
        key="csrf_token",
        value=new_csrf_token,
        max_age=max_age,
        httponly=False,  # JS needs to read this
        secure=True,
        samesite="lax",  # Lax allows cross-site requests from different ports
        path="/",
    )

    # Also set new CSRF token in response header for backward compatibility
    response.headers["X-CSRF-Token"] = new_csrf_token

    return {"message": "Session refreshed successfully", "expires_in": max_age}


@app.get(
    "/api/auth/me",
    tags=["Auth"],
    summary="Get Current User",
    description="Returns information about the currently authenticated user",
    operation_id="getCurrentUser",
)
async def get_me(
    request: Request, response: Response, current_user: dict = Depends(get_current_user)
):
    """
    Handles the retrieval of the current authenticated user information along with session
    and CSRF token management. Ensures that a proper csrf_token cookie is set and includes
    the CSRF token as a custom header in the response. The endpoint returns user-specific
    information such as user ID, email, and session expiry details.

    :param request: FastAPI Request object; used to gather request-related data such as cookies.
    :type request: Request
    :param response: FastAPI Response object; used to customize HTTP response attributes like
                     headers and cookies.
    :type response: Response
    :param current_user: Dictionary containing information about the currently authenticated user;
                         includes user details and session attributes.
    :type current_user: dict, retrieved via dependency injection
    :return: JSON response with user information, including user ID, email, guest session
             status, and session expiry details.
    :rtype: dict
    """
    # Check if CSRF cookie exists
    csrf_cookie = request.cookies.get("csrf_token")
    csrf_token = current_user.get("csrf_token")

    # If we have a CSRF token in session but no cookie, set the cookie
    if csrf_token and not csrf_cookie:
        # Calculate max age based on remaining session time
        expires_in = current_user.get("expires_in", 86400)  # Default to 24 hours
        response.set_cookie(
            key="csrf_token",
            value=csrf_token,
            max_age=expires_in,
            httponly=False,  # JS needs to read this
            secure=True,
            samesite="lax",  # Lax allows cross-site requests from different ports
            path="/",
        )

    # Include CSRF token in response header
    if csrf_token:
        response.headers["X-CSRF-Token"] = csrf_token

    # Prepare user data with session info
    user_data = {
        "user_id": current_user["user_id"],
        "email": current_user["email"],
        "is_guest": current_user.get("is_guest", False),
        "session_expires_at": current_user.get("expires_at"),
        "session_expires_in": current_user.get("expires_in"),
    }

    return {"user": user_data}


# Handle OPTIONS requests for all endpoints (CORS preflight)
@app.options("/{rest_of_path:path}")
async def preflight_handler(rest_of_path: str):
    """
    Handles HTTP OPTIONS requests to support CORS preflight actions.

    This function is used to respond to preflight requests with an HTTP status
    code of 200 to indicate that the request is allowed. CORS (Cross-Origin
    Resource Sharing) preflight requests are triggered by clients (browsers)
    to verify permissions between the requesting domain and the resource's
    domain.

    :param rest_of_path: The variable path segment of the request route.
    :type rest_of_path: str
    :return: A response with HTTP status code 200 indicating successful preflight handling.
    :rtype: Response
    """
    return Response(status_code=status.HTTP_200_OK)


# API endpoints with authentication
@app.get(
    "/api/conversations",
    response_model=List[ConversationResponse],
    responses={
        status.HTTP_204_NO_CONTENT: {"description": "No conversations found"},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Internal server error",
        },
    },
    tags=["Conversation"],
)
async def get_conversations(
    response: Response, current_user: dict = Depends(get_current_user)
):
    """
    Retrieve a list of conversations for the authenticated user. Only authenticated
    users who are not guests will have server-side conversations accessible. The
    conversations are fetched, ordered by the updated timestamp, and corresponding
    details such as participants and messages are processed before constructing
    a response.

    :param response: FastAPI Response object used to set custom HTTP response statuses.
    :type response: Response
    :param current_user: Information about the currently authenticated user, retrieved
        using Depends on get_current_user. Contains keys like `user_id` and
        `is_guest`.
    :type current_user: dict
    :return: A list of `ConversationResponse` objects representing the user's conversations,
        or an empty list if no conversations are found. In case of an error, an
        instance of `ErrorResponse` with the error details.
    :rtype: List[ConversationResponse] or ErrorResponse
    """
    print("Get conversations for user called")
    user_id = current_user["user_id"]

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
                (user_id,),
            )
            conversation_rows = cur.fetchall()

            if not conversation_rows:
                response.status_code = status.HTTP_204_NO_CONTENT
                return []

            conversation_responses = []
            for conv_row in conversation_rows:
                conversation_id = conv_row["id"]
                # Fetch messages for each conversation to calculate hash
                cur.execute(
                    "SELECT content FROM messages WHERE conversationId = ?",
                    (conversation_id,),
                )
                messages = cur.fetchall()
                hashsum = generate_hash(messages)

                # Parse participants (stored as JSON string)
                participants = (
                    json.loads(conv_row["participants"])
                    if conv_row["participants"]
                    else []
                )

                conversation_responses.append(
                    ConversationResponse(
                        id=conversation_id,
                        userId=conv_row["userId"],
                        name=conv_row["name"],
                        participants=participants,
                        createdAt=conv_row["createdAt"],
                        updatedAt=conv_row["updatedAt"],
                        hashsum=hashsum,
                        version=conv_row["version"] or 1,
                        lastModified=conv_row["lastModified"] or int(time.time()),
                    )
                )

            return conversation_responses

    except Exception as e:
        print(f"Error: {str(e)}")
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return ErrorResponse(error=str(e))


@app.get(
    "/api/conversation/{conversation_id}",
    response_model=ConversationWithDetails,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Conversation not found",
        },
        status.HTTP_403_FORBIDDEN: {
            "model": ErrorResponse,
            "description": "Access denied",
        },
    },
    tags=["Conversation"],
)
async def get_conversation(
    conversation_id: str,
    response: Response,
    current_user: dict = Depends(get_current_user),
):
    """
    Fetches the details of a specific conversation for the authenticated user.

    The function retrieves a conversation using the provided conversation ID, ensuring
    that it belongs to the current authenticated user. It fetches associated attributes of
    the conversation, such as the participant details, creation and last modification
    timestamps, the number of messages, and optionally computes a SHA-256 hash of the
    content of messages in the conversation. The function responds with the full
    conversation details if successful.

    :param conversation_id: The unique identifier of the conversation to fetch.
    :type conversation_id: str
    :param response: An instance to manipulate the HTTP response properties such as the status code.
    :type response: Response
    :param current_user: The dictionary containing the current authenticated user's information,
        retrieved through dependency injection.
    :type current_user: dict
    :return: A detailed representation of the requested conversation, including metadata
        such as message count and sync hash, if the conversation exists and belongs to the
        current user.
    :rtype: ConversationWithDetails

    :raises status.HTTP_404_NOT_FOUND: If the conversation is not found or does not belong
        to the authenticated user.
    :raises status.HTTP_403_FORBIDDEN: If the user is unauthorized to access the resource.
    :raises status.HTTP_500_INTERNAL_SERVER_ERROR: If unexpected errors occur during database
        operations or processing.
    """
    user_id = current_user["user_id"]

    try:
        with get_db() as conn:
            cur = conn.cursor()

            # Fetch conversation details
            cur.execute(
                """
                  SELECT id, userId, name, participants, createdAt, updatedAt
                  FROM conversations
                  WHERE id = ? AND userId = ?
                  """,
                (conversation_id, user_id),
            )

            conv_row = cur.fetchone()

            if not conv_row:
                response.status_code = status.HTTP_404_NOT_FOUND
                return ErrorResponse(error="Conversation not found")

            # Get message count
            cur.execute(
                "SELECT COUNT(*) as count FROM messages WHERE conversationId = ?",
                (conversation_id,),
            )
            message_count = cur.fetchone()["count"]

            # Get all messages to compute hash
            cur.execute(
                "SELECT content FROM messages WHERE conversationId = ? ORDER BY time",
                (conversation_id,),
            )
            messages = cur.fetchall()

            # Compute SHA-256 hash of conversation content
            content_str = "".join(
                [msg["content"] for msg in messages if msg["content"]]
            )
            sync_hash = generate_sha256_hash(content_str) if content_str else None

            # Return conversation with details
            return ConversationWithDetails(
                id=conv_row["id"],
                userId=conv_row["userId"],
                name=conv_row["name"],
                participants=conv_row["participants"],
                createdAt=conv_row["createdAt"],
                lastModified=conv_row["updatedAt"],
                messageCount=message_count,
                syncHash=sync_hash,
            )

    except Exception as e:
        print(f"Error fetching conversation: {str(e)}")
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return ErrorResponse(error=str(e))


# **MODIFIED:** Updated settings endpoint to match new frontend logic
@app.get(
    "/api/settings",
    response_model=AppSettingsResponse,
    tags=["Settings"],
    summary="Get User Settings",
    description="Retrieve application settings for the current user",
    operation_id="getUserSettings",
)
async def get_settings(current_user: dict = Depends(get_current_user)):
    """
    Retrieve application settings for the current user.

    This endpoint handles retrieving user-specific application settings such as theme
    and language preferences. If the user is a guest, default settings along with the
    current timestamp are returned. If a regular user does not have any saved settings
    in the database, the system falls back to default configuration. For users with
    custom settings saved in the database, those settings are retrieved and returned,
    with the updated_at field converted to a Unix timestamp.

    :param current_user: Dictionary containing user authentication and role details
                        (e.g., user_id, is_guest). Provided through dependency injection.
    :type current_user: dict
    :return: An object containing the user's theme, language, and the last updated timestamp.
    :rtype: AppSettingsResponse
    """
    user_id = current_user["user_id"]

    if current_user.get("is_guest"):
        # Return default settings for guest users with current timestamp
        return AppSettingsResponse(
            theme="auto", language="en", lastUpdated=int(time.time())
        )

    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            """
                SELECT theme, language, updated_at
                FROM user_settings
                WHERE user_id = ?
                """,
            (user_id,),
        )
        row = cur.fetchone()

        if row:
            # Convert datetime string to datetime object, then to Unix timestamp
            updated_at_dt = datetime.fromisoformat(row["updated_at"])
            last_updated_ts = int(updated_at_dt.timestamp())

            return AppSettingsResponse(
                theme=row["theme"],
                language=row["language"],
                lastUpdated=last_updated_ts,
            )
        else:
            # Fallback defaults if user has no settings yet
            return AppSettingsResponse(
                theme="auto", language="en", lastUpdated=int(time.time())
            )


@app.put(
    "/api/settings",
    response_model=AppSettingsResponse,
    tags=["Settings"],
    summary="Update User Settings",
    description="Update application settings for the current user",
    operation_id="updateUserSettings",
)
async def update_settings(
    new_settings: AppSettings, current_user: dict = Depends(get_current_user)
):
    """
    Updates user settings in the database with new preferences and returns the updated settings.

    This endpoint is responsible for updating user-specific settings such as theme and language.
    It checks if the user is a guest and, if so, restricts access to saving settings. The database
    handles timestamp updates automatically. After updating or inserting the new settings, the
    function retrieves the updated settings along with the last modified timestamp, which is
    returned to the caller.

    :param new_settings: New settings to be saved for the user.
    :type new_settings: AppSettings
    :param current_user: Dictionary containing current user details, including their ID and permissions.
    :type current_user: dict
    :return: An object containing the updated theme, language, and the timestamp of the last modification.
    :rtype: AppSettingsResponse
    """
    user_id = current_user["user_id"]
    if current_user.get("is_guest"):
        raise HTTPException(status_code=403, detail="Guests cannot save settings.")

    with get_db() as db:
        cur = db.cursor()
        # Use CURRENT_TIMESTAMP to let the database handle the update time
        cur.execute(
            """
                INSERT INTO user_settings (user_id, theme, language, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                  theme = excluded.theme,
                  language = excluded.language,
                  updated_at = CURRENT_TIMESTAMP
                """,
            (user_id, new_settings.theme, new_settings.language),
        )
        db.commit()

        # Fetch the updated settings to get the new timestamp
        cur.execute(
            """
                SELECT theme, language, updated_at
                FROM user_settings
                WHERE user_id = ?
                """,
            (user_id,),
        )
        row = cur.fetchone()

        try:
            updated_at_dt = datetime.fromisoformat(row["updated_at"])
            last_updated_ts = int(updated_at_dt.timestamp())
        except (ValueError, TypeError):
            # Fallback to current time if parsing fails
            last_updated_ts = int(time.time())

    return AppSettingsResponse(
        theme=row["theme"], language=row["language"], lastUpdated=last_updated_ts
    )


@app.post(
    "/api/conversation/create",
    response_model=Conversation,
    status_code=status.HTTP_201_CREATED,
    tags=["Conversation"],
)
async def create_conversation(
    req: ConversationCreateRequest, current_user: dict = Depends(get_current_user)
):
    """
    Creates a new conversation and saves it into the database. The user must be authenticated
    to create a new conversation. The conversation will include the specified participants and
    other provided details. The function generates a unique conversation ID, saves the conversation
    into the database, and then retrieves and returns the saved conversation details.

    :param req: An object containing details required to create a conversation, including
        name and participants.
    :type req: ConversationCreateRequest
    :param current_user: A dictionary holding authentication details of the current user,
        injected via dependency.
    :type current_user: dict
    :return: The newly created conversation.
    :rtype: Conversation
    """
    user_id = current_user["user_id"]
    with get_db() as conn:
        cur = conn.cursor()
        participants_json = json.dumps(req.participants)
        new_id = generate_conversation_id()  # Generate UUID

        cur.execute(
            "INSERT INTO conversations (id, userId, name, participants) VALUES (?, ?, ?, ?)",
            (new_id, user_id, req.name, participants_json),
        )
        conn.commit()

        cur.execute(
            "SELECT id, userId, name, participants, createdAt, updatedAt FROM conversations WHERE id = ?",
            (new_id,),
        )
        new_conv_row = cur.fetchone()

        return Conversation(**dict(new_conv_row))


class ConversationUpdateRequest(BaseModel):
    name: str


@app.patch(
    "/api/conversation/{conversation_id}",
    response_model=Conversation,
    tags=["Conversation"],
)
async def update_conversation(
    conversation_id: str,
    req: ConversationUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Handles the updating of a specific conversation for the currently authorized user.

    This endpoint allows the user to update the name of a conversation if the
    specified conversation belongs to the user. The request validates the
    existence of the conversation and updates the record in the database.
    Returns the updated conversation details on success.

    :param conversation_id: Identifier of the conversation to be updated.
    :type conversation_id: str
    :param req: Data required for updating the conversation.
    :type req: ConversationUpdateRequest
    :param current_user: Dictionary containing details of the currently authorized user.
    :type current_user: dict
    :return: An instance of the updated conversation.
    :rtype: Conversation
    :raises HTTPException: If the conversation does not exist for the user.
    """
    user_id = current_user["user_id"]

    with get_db() as conn:
        cur = conn.cursor()

        # Check if conversation exists and belongs to user
        cur.execute(
            "SELECT id FROM conversations WHERE id = ? AND userId = ?",
            (conversation_id, user_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Update conversation
        cur.execute(
            "UPDATE conversations SET name = ?, updatedAt = CURRENT_TIMESTAMP WHERE id = ? AND userId = ?",
            (req.name, conversation_id, user_id),
        )
        conn.commit()

        # Return updated conversation
        cur.execute(
            "SELECT id, userId, name, participants, createdAt, updatedAt FROM conversations WHERE id = ?",
            (conversation_id,),
        )
        updated_conv = cur.fetchone()

        crud_logger.info(
            f"Conversation {conversation_id} renamed to '{req.name}' by user {user_id}"
        )

        return Conversation(**dict(updated_conv))


@app.delete(
    "/api/conversation/{conversation_id}",
    status_code=status.HTTP_200_OK,
    tags=["Conversation"],
)
async def delete_conversation(
    conversation_id: str, current_user: dict = Depends(get_current_user)
):
    """
    Deletes a conversation along with all its associated messages for the
    current user. If the specified conversation does not exist or does not
    belong to the user, a 204 No Content response is returned.

    :param current_user: Dictionary containing details of the currently authorized user.
    :param conversation_id: The unique identifier of the conversation to be deleted.
    :type conversation_id: str
    """
    user_id = current_user["user_id"]

    with get_db() as conn:
        cur = conn.cursor()

        # Check if conversation exists and belongs to user
        cur.execute(
            "SELECT id FROM conversations WHERE id = ? AND userId = ?",
            (conversation_id, user_id),
        )
        if not cur.fetchone():
            # Return 204 No Content if conversation doesn't exist
            return Response(status_code=status.HTTP_204_NO_CONTENT)

        # Delete all messages in the conversation
        cur.execute("DELETE FROM messages WHERE conversationId = ?", (conversation_id,))

        # Delete the conversation
        cur.execute(
            "DELETE FROM conversations WHERE id = ? AND userId = ?",
            (conversation_id, user_id),
        )

        conn.commit()

        crud_logger.info(
            f"Conversation {conversation_id} and all messages deleted by user {user_id}"
        )

        return {"message": "Conversation deleted successfully"}


@app.get(
    "/api/conversation/messages/{conversation_id}/{timestamp}/{messages_count}",
    response_model=List[MessageResponse],
    responses={
        status.HTTP_204_NO_CONTENT: {"description": "No messages found"},
        status.HTTP_206_PARTIAL_CONTENT: {
            "description": "Partial content, more messages available"
        },
        status.HTTP_400_BAD_REQUEST: {
            "model": ErrorResponse,
            "description": "Conversation ID or timestamp missing",
        },
        status.HTTP_403_FORBIDDEN: {
            "model": ErrorResponse,
            "description": "Access denied",
        },
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Conversation not found",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Internal server error",
        },
    },
    tags=["Conversation"],
)
async def get_conversation_messages(
    conversation_id: str,
    timestamp: int,
    messages_count: int,
    response: Response,
    current_user: dict = Depends(get_current_user),
    after_timestamp: Optional[int] = None,
):
    """
    Fetches messages from a specific conversation based on the provided pagination
    or timestamp criteria. This endpoint supports both incremental synchronization
    and traditional pagination of conversation messages.

    :param conversation_id: The unique identifier of the conversation to fetch messages from
    :param timestamp: The reference timestamp used for paginated message retrieval
    :param messages_count: The maximum number of messages to retrieve
    :param response: An instance of FastAPI response used for setting headers and status codes
    :param current_user: The user object of the current authenticated user
        (includes user_id and other attributes as needed)
    :param after_timestamp: Optional parameter used for incremental sync. When provided,
        retrieves messages newer than the given timestamp
    :return: A list of messages (formatted as dictionaries) from the requested conversation
    """
    print(f"Get conversation messages called - after_timestamp: {after_timestamp}")

    try:
        if not conversation_id or timestamp is None:
            response.status_code = status.HTTP_400_BAD_REQUEST
            return ErrorResponse(
                error="Conversation ID and latest timestamp are required"
            )

        # Verify ownership (guests can access any conversation)
        if not verify_conversation_ownership(
            conversation_id,
            current_user["user_id"],
            current_user.get("is_guest", False),
        ):
            response.status_code = status.HTTP_403_FORBIDDEN
            return ErrorResponse(error="Access denied to this conversation")

        with get_db() as conn:
            cur = conn.cursor()

            # Different queries for incremental sync vs pagination
            if after_timestamp is not None:
                # Incremental sync: get messages newer than after_timestamp
                cur.execute(
                    """
          SELECT id, conversationId, roleName, content, time, type, version, lastModified, rating
          FROM messages
          WHERE conversationId = ? AND time > ?
          ORDER BY time ASC
          """,
                    (conversation_id, after_timestamp),
                )
            else:
                # Normal pagination: get messages before timestamp
                cur.execute(
                    """
          SELECT id, conversationId, roleName, content, time, type, version, lastModified, rating
          FROM messages
          WHERE conversationId = ? AND time < ?
          ORDER BY time DESC LIMIT ?
          """,
                    (conversation_id, timestamp, min(messages_count, 30)),
                )

            messages_rows = cur.fetchall()

            if messages_rows:
                messages_data = [dict(msg) for msg in messages_rows]

                # For pagination, reverse to get chronological order
                if after_timestamp is None:
                    messages_data.reverse()

                # Check if there might be more messages
                has_more = False
                if (
                    after_timestamp is None
                    and messages_count > 30
                    and len(messages_data) == 30
                ):
                    has_more = True
                    response.status_code = status.HTTP_206_PARTIAL_CONTENT
                else:
                    response.status_code = status.HTTP_200_OK

                # Add header to indicate if more messages exist
                if after_timestamp is not None:
                    # For incremental sync, check if there are any messages we didn't fetch
                    if messages_data:
                        oldest_fetched = messages_data[0]["time"]
                        cur.execute(
                            "SELECT COUNT(*) as count FROM messages WHERE conversationId = ? AND time < ?",
                            (conversation_id, oldest_fetched),
                        )
                        older_count = cur.fetchone()["count"]
                        response.headers["X-Has-More-Messages"] = str(older_count > 0)
                    else:
                        # No new messages, but check if there are any messages at all
                        cur.execute(
                            "SELECT COUNT(*) as count FROM messages WHERE conversationId = ?",
                            (conversation_id,),
                        )
                        total_count = cur.fetchone()["count"]
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


@app.post(
    "/api/message/send",
    response_model=Dict[str, int],
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "model": ErrorResponse,
            "description": "Message content cannot be empty",
        },
        status.HTTP_403_FORBIDDEN: {
            "model": ErrorResponse,
            "description": "Access denied",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Internal server error",
        },
    },
    tags=["Message"],
)
async def user_send_message(
    request_body: ApiMessageSend,
    response: Response,
    current_user: dict = Depends(get_current_user),
):
    """
    Handles the sending of a message in a conversation. This endpoint processes the
    provided request body to determine the type and content of the message, verifies
    whether the current user has access to the specified conversation, and inserts
    the message into the database.

    :param request_body: The request payload containing details of the message, such
        as `conversationId`, `content`, `roleName`, `time`, `type`, `version`, and
        `lastModified`.
    :type request_body: ApiMessageSend
    :param response: The HTTP response object to set the response status code
        and return any errors if they occur.
    :type response: Response
    :param current_user: The authenticated user information, typically obtained from
        dependency injection in FastAPI.
    :type current_user: dict
    :return: A dictionary containing the `id` of the message if successfully created.
    :rtype: Dict[str, int]
    :raises HTTPException: Raises specific HTTP exceptions with appropriate status
        codes for cases such as empty message content, access denial, or internal
        server errors.
    """
    crud_logger.info(
        f"Message send called - User: {current_user['user_id']}, Conversation: {request_body.conversationId}"
    )

    try:
        if not request_body.content:
            response.status_code = status.HTTP_400_BAD_REQUEST
            return ErrorResponse(error="Message content cannot be empty")

        # Verify ownership
        if not verify_conversation_ownership(
            request_body.conversationId,
            current_user["user_id"],
            current_user.get("is_guest", False),
        ):
            response.status_code = status.HTTP_403_FORBIDDEN
            return ErrorResponse(error="Access denied to this conversation")

        message_id = int(time.time() * 1000)

        # Extract content based on message type
        content_str = ""
        message_type = getattr(
            request_body, "type", "text"
        )  # Default to 'text' for backwards compatibility

        if message_type == "text":
            if isinstance(request_body.content, str):
                # Legacy format - just a string
                content_str = request_body.content
            elif isinstance(request_body.content, dict):
                # New format - TextContent object
                content_str = request_body.content.get("content", "")
                # Store attachments as JSON in content for now
                attachments = request_body.content.get("attachments", [])
                if attachments:
                    content_obj = {"content": content_str, "attachments": attachments}
                    content_str = json.dumps(content_obj)
        elif message_type == "voice":
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
                (
                    message_id,
                    request_body.conversationId,
                    request_body.roleName,
                    content_str,
                    request_body.time,
                    message_type,
                    request_body.version or 1,
                    request_body.lastModified or int(time.time()),
                ),
            )
            conn.commit()

        crud_logger.info(f"Message sent successfully - Message ID: {message_id}")
        return {"id": message_id}

    except Exception as e:
        crud_logger.error(f"Error sending message: {str(e)}", exc_info=True)
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return ErrorResponse(
            error=f"Failed to send message: {str(e)}. Please try again later."
        )


@app.post(
    "/api/message/generate",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "model": ErrorResponse,
            "description": "Conversation ID missing",
        },
        status.HTTP_403_FORBIDDEN: {
            "model": ErrorResponse,
            "description": "Access denied",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Internal server error",
        },
    },
    tags=["Message"],
    dependencies=[Depends(rate_limit_guest)],
)
async def generate_message(
    request_body: ApiMessageGenerate,
    response: Response,
    current_user: dict = Depends(get_current_user),
):
    """
    Generates a message for a conversation based on the provided context, user role, and AI response generation.
    This endpoint interacts with a database to store the generated message and ensures user access verification
    for the conversation. Additionally, it handles errors related to conversation ID validation, user access
    denial, or other server-side issues.

    :param request_body: The request payload containing details of the conversation ID and role.
    :type request_body: ApiMessageGenerate
    :param response: FastAPI Response object to set response status codes.
    :type response: Response
    :param current_user: Details of the currently authenticated user.
    :type current_user: dict
    :return: A dictionary containing the generated message details if successful, or an error response structure.
    :rtype: dict
    """
    crud_logger.info(
        f"Generate message called - User: {current_user['user_id']}, Conversation: {request_body.conversationId}"
    )

    try:
        # Verify ownership
        if not verify_conversation_ownership(
            request_body.conversationId,
            current_user["user_id"],
            current_user.get("is_guest", False),
        ):
            response.status_code = status.HTTP_403_FORBIDDEN
            return ErrorResponse(error="Access denied to this conversation")

        if not request_body.conversationId:
            response.status_code = status.HTTP_400_BAD_REQUEST
            return ErrorResponse(error="Conversation ID missing or invalid in request")

        # Get conversation context for the LLM
        context = await get_conversation_context(request_body.conversationId)

        # Generate AI response
        ai_response_content = await generate_llm_response(
            context,
            DEFAULT_TEMPERATURE,
            DEFAULT_TOP_P,
            DEFAULT_SYSTEM_PROMPT,
            DEFAULT_MODEL,
        )

        message_id = int(time.time() * 1000)
        current_time = int(time.time())

        message_doc_data = {
            "id": message_id,
            "conversationId": request_body.conversationId,
            "roleName": request_body.roleName,
            "content": ai_response_content,
            "time": current_time,
            "version": 1,
            "lastModified": current_time,
        }

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
        INSERT INTO messages (id, conversationId, roleName, content, time, type, version, lastModified)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
                (
                    message_id,
                    request_body.conversationId,
                    request_body.roleName,
                    message_doc_data["content"],
                    current_time,
                    "text",
                    1,
                    current_time,
                ),
            )
            conn.commit()

        return message_doc_data

    except Exception as e:
        print(f"Error: {str(e)}")
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return ErrorResponse(error=str(e))


@app.patch(
    "/api/message/patch",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Message ID missing or invalid request"
        },
        status.HTTP_403_FORBIDDEN: {
            "model": ErrorResponse,
            "description": "Access denied",
        },
        status.HTTP_404_NOT_FOUND: {"description": "Message not found"},
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "Version conflict",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Internal server error",
        },
    },
    tags=["Message"],
)
async def patch_message(
    request_body: MessagePatch,
    response: Response,
    current_user: dict = Depends(get_current_user),
):
    """
    Handles the patching of a message within a conversation. This endpoint allows authorized
    users to update a specific message by its ID. It includes version control to ensure
    data consistency during concurrent updates and verifies ownership of the conversation
    before processing the request. Additionally, the method attempts to parse and return the
    content type appropriately when applicable.

    :param request_body: Contains the request data necessary for updating the message.
    :param response: The HTTP response object to set status codes and return responses.
    :param current_user: The current user making the patch request, obtained via dependency injection.
    :return: A MessageResponse object representing the updated message, or an ErrorResponse
             if the operation fails.
    """
    crud_logger.info(
        f"Patch message called - User: {current_user['user_id']}, Message: {request_body.id}, Conversation: {request_body.conversationId}"
    )

    try:
        if not request_body.id:
            response.status_code = status.HTTP_400_BAD_REQUEST
            return Response(
                status_code=status.HTTP_400_BAD_REQUEST, content="Message ID missing"
            )

        # Verify ownership
        if not verify_conversation_ownership(
            request_body.conversationId,
            current_user["user_id"],
            current_user.get("is_guest", False),
        ):
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
                (request_body.id, request_body.conversationId),
            )
            result = cur.fetchone()

            if not result:
                response.status_code = status.HTTP_404_NOT_FOUND
                return Response(
                    status_code=status.HTTP_404_NOT_FOUND, content="Message not found"
                )

            current_version = result[0] or 1

            # Check for version conflict
            if current_version != request_body.version:
                response.status_code = status.HTTP_409_CONFLICT
                return ErrorResponse(
                    error=f"Version conflict: current version is {current_version}, provided version is {request_body.version}"
                )

            # Update with version increment
            new_version = current_version + 1
            cur.execute(
                """
        UPDATE messages
        SET content = ?, version = ?, lastModified = ?
        WHERE id = ? AND conversationId = ? AND version = ?
        """,
                (
                    request_body.content,
                    new_version,
                    int(time.time()),
                    request_body.id,
                    request_body.conversationId,
                    request_body.version,
                ),
            )
            conn.commit()

            if cur.rowcount == 0:
                response.status_code = status.HTTP_409_CONFLICT
                return ErrorResponse(error="Version conflict during update")

            # Fetch the updated message to return
            cur.execute(
                """
        SELECT id, conversationId, roleName, content, time, type, version, lastModified, rating
        FROM messages
        WHERE id = ? AND conversationId = ?
        """,
                (request_body.id, request_body.conversationId),
            )
            updated_row = cur.fetchone()

            if updated_row:
                # Parse content based on type
                message_type = updated_row["type"] or "text"
                content = updated_row["content"]

                # Try to parse JSON content for complex types
                try:
                    if message_type == "text" and content.startswith("{"):
                        content_obj = json.loads(content)
                        if "content" in content_obj:
                            content = content_obj["content"]
                except:
                    pass  # Use content as-is if not JSON

                crud_logger.info(
                    f"Message patched successfully - Message ID: {request_body.id}, New version: {new_version}"
                )
                return MessageResponse(
                    id=updated_row["id"],
                    conversationId=updated_row["conversationId"],
                    roleName=updated_row["roleName"],
                    content=content,
                    time=updated_row["time"],
                    type=message_type,
                    version=updated_row["version"],
                    lastModified=updated_row["lastModified"],
                    rating=updated_row["rating"],
                )

        return None

    except Exception as e:
        crud_logger.error(f"Error patching message: {str(e)}", exc_info=True)
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return ErrorResponse(
            error=f"Failed to update message: {str(e)}. Please refresh and try again."
        )


@app.delete(
    "/api/message/delete/{conversation_id}/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Conversation ID or Message ID missing"
        },
        status.HTTP_403_FORBIDDEN: {
            "model": ErrorResponse,
            "description": "Access denied",
        },
        status.HTTP_404_NOT_FOUND: {"description": "Message not found"},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Internal server error",
        },
    },
    tags=["Message"],
)
async def delete_message(
    conversation_id: str,
    message_id: int,
    response: Response,
    current_user: dict = Depends(get_current_user),
):
    """
    Deletes a specific message within a conversation. The endpoint requires the conversation ID,
    message ID, and the current authenticated user to verify access and execute the operation.
    If successful, the message is deleted from the database.

    :param conversation_id: Unique identifier of the conversation containing the message
    :type conversation_id: str
    :param message_id: Unique identifier of the message to be deleted
    :type message_id: int
    :param response: The response object to modify the HTTP response status
    :param current_user: Dictionary object representing the current user, fetched via dependency injection
    :return: None
    :raises HTTP_400_BAD_REQUEST: If `conversation_id` or `message_id` is missing
    :raises HTTP_403_FORBIDDEN: If the user does not have permission to delete the message in the conversation
    :raises HTTP_404_NOT_FOUND: If the message does not exist in the database
    :raises HTTP_500_INTERNAL_SERVER_ERROR: In case of unexpected server errors
    """
    crud_logger.info(
        f"Delete message called - User: {current_user['user_id']}, Message: {message_id}, Conversation: {conversation_id}"
    )

    try:
        if not conversation_id or not message_id:
            response.status_code = status.HTTP_400_BAD_REQUEST
            return Response(
                status_code=status.HTTP_400_BAD_REQUEST,
                content="Conversation ID or Message ID missing",
            )

        # Verify ownership
        if not verify_conversation_ownership(
            conversation_id,
            current_user["user_id"],
            current_user.get("is_guest", False),
        ):
            response.status_code = status.HTTP_403_FORBIDDEN
            return ErrorResponse(error="Access denied to this conversation")

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM messages WHERE conversationId = ? AND id = ?",
                (conversation_id, message_id),
            )
            conn.commit()

            if cur.rowcount == 0:
                crud_logger.warning(
                    f"Message not found for deletion - Message ID: {message_id}"
                )
                response.status_code = status.HTTP_404_NOT_FOUND
                return Response(
                    status_code=status.HTTP_404_NOT_FOUND, content="Message not found"
                )

        crud_logger.info(f"Message deleted successfully - Message ID: {message_id}")
        return None

    except Exception as e:
        crud_logger.error(f"Error deleting message: {str(e)}", exc_info=True)
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return ErrorResponse(
            error=f"Failed to delete message: {str(e)}. Please check your connection and try again."
        )


@app.post(
    "/api/message/rate",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "model": ErrorResponse,
            "description": "Invalid request",
        },
        status.HTTP_403_FORBIDDEN: {
            "model": ErrorResponse,
            "description": "Access denied",
        },
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Message not found",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Internal server error",
        },
    },
    tags=["Message"],
)
async def rate_message(
    request_body: RateMessageRequest,
    response: Response,
    current_user: dict = Depends(get_current_user),
):
    """
    Rate a message within a conversation. This endpoint allows users to rate a message
    using a thumbs up (1), thumbs down (0), or remove their rating (null). It ensures the
    user's ownership of the conversation before performing the operation.

    :param request_body: The request payload containing the `id` of the message to rate,
        the `conversationId` it belongs to, and the `rating` to apply.
    :type request_body: RateMessageRequest
    :param response: HTTP response object for assigning custom status codes and response
        headers.
    :type response: Response
    :param current_user: Information of the currently authenticated user, obtained via
        dependency injection.
    :type current_user: dict
    :return: A response containing the updated message record with the applied rating.
    :rtype: MessageResponse
    :raises HTTP_400_BAD_REQUEST: If the provided rating value is invalid.
    :raises HTTP_403_FORBIDDEN: If the user does not have access to the specified
        conversation.
    :raises HTTP_404_NOT_FOUND: If the message to rate does not exist in the conversation.
    :raises HTTP_500_INTERNAL_SERVER_ERROR: If an internal server error occurs.
    """
    crud_logger.info(
        f"Rate message called - User: {current_user['user_id']}, Message: {request_body.id}, Rating: {request_body.rating}"
    )

    try:
        # Validate rating value (None is allowed to remove rating)
        if request_body.rating is not None and request_body.rating not in [0, 1]:
            response.status_code = status.HTTP_400_BAD_REQUEST
            return ErrorResponse(
                error="Rating must be 0 (thumbs down), 1 (thumbs up), or null to remove rating"
            )

        # Verify ownership
        if not verify_conversation_ownership(
            request_body.conversationId,
            current_user["user_id"],
            current_user.get("is_guest", False),
        ):
            response.status_code = status.HTTP_403_FORBIDDEN
            return ErrorResponse(error="Access denied to this conversation")

        with get_db() as conn:
            cur = conn.cursor()

            # Update the rating
            cur.execute(
                """
        UPDATE messages
        SET rating = ?
        WHERE id = ? AND conversationId = ?
        """,
                (request_body.rating, request_body.id, request_body.conversationId),
            )

            if cur.rowcount == 0:
                response.status_code = status.HTTP_404_NOT_FOUND
                return ErrorResponse(error="Message not found")

            conn.commit()

            # Fetch the updated message
            cur.execute(
                """
        SELECT id, conversationId, roleName, content, time, type, version, lastModified, rating
        FROM messages
        WHERE id = ? AND conversationId = ?
        """,
                (request_body.id, request_body.conversationId),
            )

            row = cur.fetchone()
            if row:
                # Parse content based on type
                message_type = row["type"] or "text"
                content = row["content"]

                # Try to parse JSON content for complex types
                try:
                    if message_type == "text" and content.startswith("{"):
                        content_obj = json.loads(content)
                        if "content" in content_obj:
                            content = content_obj["content"]
                except:
                    pass  # Use content as-is if not JSON

                rating_text = (
                    "removed"
                    if request_body.rating is None
                    else str(request_body.rating)
                )
                crud_logger.info(
                    f"Message rated successfully - Message ID: {request_body.id}, Rating: {rating_text}"
                )
                return MessageResponse(
                    id=row["id"],
                    conversationId=row["conversationId"],
                    roleName=row["roleName"],
                    content=content,
                    time=row["time"],
                    type=message_type,
                    version=row["version"],
                    lastModified=row["lastModified"],
                    rating=row["rating"],
                )

        return None

    except Exception as e:
        crud_logger.error(f"Error rating message: {str(e)}", exc_info=True)
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return ErrorResponse(error=f"Failed to rate message: {str(e)}")


@app.post(
    "/api/message/regenerate",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "model": ErrorResponse,
            "description": "Invalid request",
        },
        status.HTTP_403_FORBIDDEN: {
            "model": ErrorResponse,
            "description": "Access denied",
        },
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Message not found",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Internal server error",
        },
    },
    tags=["Message"],
    dependencies=[Depends(rate_limit_guest)],
)
async def regenerate_message(
    request_body: RegenerateMessageRequest,
    response: Response,
    current_user: dict = Depends(get_current_user),
):
    """
    Handles the regeneration of an AI message within a conversation. The endpoint
    verifies ownership of the conversation, ensures the message to regenerate
    exists, and is an AI-generated message. It rebuilds the conversation context
    and regenerates a response using an LLM model. If successful, the message is
    updated with the new version and returned.

    :param request_body: The details of the message to regenerate, including the
        message ID and conversation ID.
    :type request_body: RegenerateMessageRequest

    :param response: The FastAPI Response object to send the HTTP response.
    :type response: Response

    :param current_user: The current authenticated user information, including
        user ID and permissions.
    :type current_user: dict

    :return: Returns the updated message after regeneration if successful.
    :rtype: MessageResponse

    :raises HTTPException: 400 if the requested message is not an AI message.
    :raises HTTPException: 403 if the user does not have access to the conversation.
    :raises HTTPException: 404 if the specified message is not found.
    :raises HTTPException: 500 if any internal server error occurs.
    """
    crud_logger.info(
        f"Regenerate message called - User: {current_user['user_id']}, Message: {request_body.id}"
    )

    try:
        # Verify ownership
        if not verify_conversation_ownership(
            request_body.conversationId,
            current_user["user_id"],
            current_user.get("is_guest", False),
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this conversation",
            )

        with get_db() as conn:
            cur = conn.cursor()

            # Get the message to regenerate
            cur.execute(
                """
        SELECT id, conversationId, roleName, time, version
        FROM messages
        WHERE id = ? AND conversationId = ?
        """,
                (request_body.id, request_body.conversationId),
            )

            message_row = cur.fetchone()
            if not message_row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Message not found"
                )

            # Verify it's an AI message
            if message_row["roleName"] == "user":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Can only regenerate AI messages",
                )

            # Get all messages before this one
            cur.execute(
                """
        SELECT roleName, content, time
        FROM messages
        WHERE conversationId = ? AND time < ?
        ORDER BY time ASC
        """,
                (request_body.conversationId, message_row["time"]),
            )

            previous_messages = cur.fetchall()

            # Build conversation context
            context_messages = []
            for msg in previous_messages:
                context_messages.append(
                    {
                        "role": "user" if msg["roleName"] == "user" else "assistant",
                        "content": msg["content"],
                    }
                )

            # Build prompt from context messages
            prompt_lines = []
            for msg in context_messages:
                role = "User" if msg["role"] == "user" else "Assistant"
                prompt_lines.append(f"{role}: {msg['content']}")
            prompt_lines.append("Assistant:")
            prompt = "\n".join(prompt_lines)

            # Generate new AI response
            ai_response_content = await generate_llm_response(
                prompt,
                DEFAULT_TEMPERATURE,
                DEFAULT_TOP_P,
                DEFAULT_SYSTEM_PROMPT,
                DEFAULT_MODEL,
            )

            # Update the message with new content
            new_version = (message_row["version"] if message_row["version"] else 1) + 1
            current_time = int(time.time())

            cur.execute(
                """
        UPDATE messages
        SET content = ?, version = ?, lastModified = ?
        WHERE id = ? AND conversationId = ?
        """,
                (
                    ai_response_content,
                    new_version,
                    current_time,
                    request_body.id,
                    request_body.conversationId,
                ),
            )

            conn.commit()

            # Fetch and return the updated message
            cur.execute(
                """
        SELECT id, conversationId, roleName, content, time, type, version, lastModified, rating
        FROM messages
        WHERE id = ? AND conversationId = ?
        """,
                (request_body.id, request_body.conversationId),
            )

            row = cur.fetchone()
            if row:
                crud_logger.info(
                    f"Message regenerated successfully - Message ID: {request_body.id}"
                )
                return MessageResponse(
                    id=row["id"],
                    conversationId=row["conversationId"],
                    roleName=row["roleName"],
                    content=row["content"],
                    time=row["time"],
                    type=row["type"] or "text",
                    version=row["version"],
                    lastModified=row["lastModified"],
                    rating=row["rating"],
                )

        return None

    except Exception as e:
        crud_logger.error(f"Error regenerating message: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to regenerate message: {str(e)}",
        )


@app.post(
    "/api/message/send-and-generate",
    response_model=SendAndGenerateResponse,
    status_code=status.HTTP_201_CREATED,
    # ... (responses remain the same) ...
)
async def send_and_generate_message(
    request_body: ApiMessageSendAndGenerate,
    response: Response,
    current_user: dict = Depends(get_current_user),
):
    """
    Handles the processing and storage of user-generated messages while optionally
    generating AI responses. This endpoint enables communication by allowing a user
    to send a message to a specified conversation and receive an AI-generated
    response based on the context of the conversation.

    :param request_body: Data of the message request that includes conversation ID,
        message type, content, role information, and other metadata.
    :type request_body: ApiMessageSendAndGenerate
    :param response: A fastapi Response object used to manipulate HTTP response
        codes if an error or special condition is encountered.
    :type response: Response
    :param current_user: A dictionary representing the current user info fetched
        using a dependency injection method. It includes user credentials like
        user_id and guest state.
    :type current_user: dict
    :return: A SendAndGenerateResponse object containing user-generated message
        data as well as an AI-generated response message data (if applicable).
    :rtype: SendAndGenerateResponse
    """
    try:
        if not verify_conversation_ownership(
            request_body.conversationId,
            current_user["user_id"],
            current_user.get("is_guest", False),
        ):
            response.status_code = status.HTTP_403_FORBIDDEN
            return ErrorResponse(error="Access denied to this conversation")

        user_message_id = int(time.time() * 1000)
        content_str = ""
        message_type = request_body.type
        if message_type == "text":
            if isinstance(request_body.content, str):
                content_str = request_body.content
            elif isinstance(request_body.content, dict):
                content_str = request_body.content.get("content", "")
                attachments = request_body.content.get("attachments", [])
                if attachments:
                    content_obj = {"content": content_str, "attachments": attachments}
                    content_str = json.dumps(content_obj)
        elif message_type == "voice":
            content_str = (
                json.dumps(request_body.content)
                if isinstance(request_body.content, dict)
                else str(request_body.content)
            )

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
        INSERT INTO messages (id, conversationId, roleName, content, time, type, version, lastModified)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
                (
                    user_message_id,
                    request_body.conversationId,
                    request_body.roleName,
                    content_str,
                    request_body.time,
                    message_type,
                    request_body.version or 1,
                    request_body.lastModified or int(time.time()),
                ),
            )
            conn.commit()

        user_message_response = MessageResponse(
            id=user_message_id,
            conversationId=request_body.conversationId,
            roleName=request_body.roleName,
            content=content_str,
            time=request_body.time,
            type=message_type,
            version=request_body.version or 1,
            lastModified=request_body.lastModified or int(time.time()),
        )

        ai_message_response = None
        if request_body.generateResponse:
            context = await get_conversation_context(
                request_body.conversationId, limit=6
            )

            # ** THE FIX IS HERE **
            # The backend now uses its own default values for the LLM.
            ai_response_content = await generate_llm_response(
                context,
                DEFAULT_TEMPERATURE,
                DEFAULT_TOP_P,
                DEFAULT_SYSTEM_PROMPT,
                DEFAULT_MODEL,
            )

            ai_message_id = int(time.time() * 1000) + 1
            current_time = int(time.time())
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
          INSERT INTO messages (id, conversationId, roleName, content, time, type, version, lastModified)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?)
          """,
                    (
                        ai_message_id,
                        request_body.conversationId,
                        request_body.aiParticipant,
                        ai_response_content,
                        current_time,
                        "text",
                        1,
                        current_time,
                    ),
                )
                conn.commit()

            ai_message_response = MessageResponse(
                id=ai_message_id,
                conversationId=request_body.conversationId,
                roleName=request_body.aiParticipant,
                content=ai_response_content,
                time=current_time,
                type="text",
                version=1,
                lastModified=current_time,
            )

        return SendAndGenerateResponse(
            userMessage=user_message_response, aiMessage=ai_message_response
        )

    except Exception as e:
        print(f"Error in send_and_generate: {str(e)}")
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return ErrorResponse(error=str(e))


@app.post(
    "/api/files/upload",
    response_model=List[str],
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "model": ErrorResponse,
            "description": "No files provided",
        },
        # status.HTTP_413_PAYLOAD_TOO_LARGE: {"model": ErrorResponse, "description": "File too large"},
        # Does not work with the current version of starlette, use ENTITY_TOO_LARGE instead
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: {
            "model": ErrorResponse,
            "description": "File too large",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Internal server error",
        },
    },
    tags=["Files"],
)
async def upload_files(
    files: List[UploadFile] = File(...), current_user: dict = Depends(get_current_user)
):
    """
    Handles the upload of multiple files via a POST request. This endpoint validates
    the files against a maximum allowed size, generates unique IDs for the files,
    and saves them to a local directory. It returns a list of unique file identifiers
    of successfully uploaded files. If no files are provided or a file exceeds the
    maximum allowed size of 10 MB, an appropriate HTTP response is returned.

    :param files: The list of files to be uploaded
    :type files: List[UploadFile]
    :param current_user: The currently authenticated user making the request
    :type current_user: dict
    :return: A list of unique file IDs representing the uploaded files
    :rtype: List[str]
    :raises HTTPException: Raised on validation errors like missing files, files
        exceeding the size limit, or on internal server errors
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
                raise HTTPException(
                    status_code=413,
                    detail=f"File {file.filename} exceeds maximum size of 10MB",
                )

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
            print(
                f"Uploaded file: {file.filename} -> {file_id} (size: {len(contents)} bytes) saved to {file_path}"
            )

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
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-CSRF-Token",
        "X-Requested-With",
        "Accept",
        "Origin",
    ],
    expose_headers=[
        "X-CSRF-Token",
        "X-Has-More-Messages",
        "Content-Type",
        "Authorization",
        "X-CSP-Nonce",
    ],
)


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """
    Logging middleware for detailed request and response monitoring. This middleware logs the HTTP request
    and response details for specified CRUD endpoints. It skips logging for OPTIONS requests and non-CRUD
    endpoints. Additionally, it calculates and logs request body size for POST, PATCH, and PUT methods,
    and measures the time taken to process each request.

    :param request: The incoming HTTP request object.
    :type request: Request
    :param call_next: The function that receives the request and produces a response.
    :type call_next: Callable
    :return: The HTTP response object after processing the request.
    :rtype: Response
    """
    # Skip logging for OPTIONS requests and non-CRUD endpoints
    if request.method == "OPTIONS" or (
        not request.url.path.startswith("/api/message")
        and not request.url.path.startswith("/api/conversation")
    ):
        return await call_next(request)

    # Log request
    start_time = time.time()

    # Log request body size for POST/PATCH/PUT
    body_size = 0
    if request.method in ["POST", "PATCH", "PUT"]:
        # Don't read the body here as it interferes with the request processing
        # Just get the content-length header if available
        body_size = int(request.headers.get("content-length", 0))

    # Log request details
    crud_logger.info(
        f"Request: {request.method} {request.url.path} - Body size: {body_size} bytes"
    )

    # Process request
    response = await call_next(request)

    # Log response
    duration = time.time() - start_time
    crud_logger.info(
        f"Response: {request.method} {request.url.path} - Status: {response.status_code} - Duration: {duration:.3f}s"
    )

    return response


@app.middleware("http")
async def csrf_protection_middleware(request: Request, call_next):
    """
    Middleware to ensure CSRF protection for HTTP requests.

    This middleware validates the presence and correctness of a CSRF token for
    incoming requests, ensuring that requests requiring CSRF protection are
    rejected with an appropriate error if the validation fails. It bypasses CSRF
    checks for OPTIONS requests, which serve as CORS preflight requests. Additionally,
    on failure, necessary CORS headers are added to the error response to comply
    with cross-origin resource sharing policies.

    :param request: The incoming HTTP request to process.
    :type request: Request
    :param call_next: The next function in the middleware chain to execute.
    :type call_next: Callable[[Request], Awaitable[Response]]
    :return: The HTTP response after processing the request, with CSRF
             validation checks applied.
    :rtype: Response
    """
    # Skip CSRF for OPTIONS requests (CORS preflight)
    if request.method == "OPTIONS":
        response = await call_next(request)
        return response

    # Validate CSRF token
    if not await validate_csrf_token(request):
        response = JSONResponse(
            content={"error": "CSRF validation failed"}, status_code=403
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
    Middleware to enhance security by adding various HTTP security headers to the response.

    This middleware dynamically generates a Content Security Policy (CSP) header with
    a nonce for each request and adjusts the CSP policy based on whether the environment
    is in development or production mode. Additionally, it sets headers to prevent MIME
    type sniffing, enable XSS protection, enforce HTTPS in production, prevent clickjacking,
    and configure permissions policies.

    :param request: The incoming HTTP request object.
    :type request: Request
    :param call_next: The next middleware or route handler in the chain.
    :type call_next: Callable
    :return: The modified HTTP response with added security headers.
    :rtype: Response
    """
    # Generate nonce for this request
    csp_nonce = secrets.token_urlsafe(16)
    request.state.csp_nonce = csp_nonce

    response = await call_next(request)

    # Prevent MIME type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"

    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "DENY"

    # Enable XSS filter (legacy but still useful for older browsers)
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # Force HTTPS (only in production - not when using dev certs)
    if not os.getenv("USE_DEV_CERTS", "False").lower() == "true":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

    # Content Security Policy
    # For Angular compatibility, we need a more permissive policy in development
    # In production, consider migrating away from unsafe-inline and unsafe-eval
    is_dev = os.getenv("USE_DEV_CERTS", "False").lower() == "true"

    # Check if this is a Swagger UI request
    is_swagger_ui = request.url.path == "/api/docs"

    if is_swagger_ui:
        # Special CSP for Swagger UI to allow CDN resources
        csp_directives = [
            "default-src 'self' https://cdn.jsdelivr.net https://fastapi.tiangolo.com",
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
            "img-src 'self' data: blob: https://fastapi.tiangolo.com",
            "font-src 'self' data: https://cdn.jsdelivr.net",
            "connect-src 'self'",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ]
    elif is_dev:
        # Development CSP - more permissive for Angular CLI
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'",  # Required for Angular dev mode
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com",
            "img-src 'self' data: blob:",
            "connect-src 'self' wss: https: ws://localhost:* http://localhost:*",  # Allow dev server websockets
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ]
    else:
        # Production CSP - stricter but still Angular-compatible
        # Note: Moving to nonce-based CSP requires Angular build configuration changes
        csp_directives = [
            "default-src 'self'",
            f"script-src 'self' 'nonce-{csp_nonce}' 'strict-dynamic'",  # Nonce-based with strict-dynamic
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",  # Styles still need unsafe-inline
            "font-src 'self' https://fonts.gstatic.com",
            "img-src 'self' data: blob:",
            "connect-src 'self' wss: https:",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "require-trusted-types-for 'script'",  # Additional XSS protection
        ]

    response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

    # Send nonce in header for Angular to use
    response.headers["X-CSP-Nonce"] = csp_nonce

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
        print(
            f"[API] OpenAPI schema available at: https://{host}:{port}{app.openapi_url}"
        )
        print(f"[DOCS] Swagger UI available at: https://{host}:{port}/api/docs")
    else:
        print(f"[SERVER] Starting server at http://{host}:{port}")
        print(
            f"[API] OpenAPI schema available at: http://{host}:{port}{app.openapi_url}"
        )
        print(f"[DOCS] Swagger UI available at: http://{host}:{port}/api/docs")

    current_script_name = Path(__file__).stem
    uvicorn.run(f"{current_script_name}:app", **run_args)
