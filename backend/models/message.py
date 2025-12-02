"""
Message-related models.
"""
from typing import List, Optional, Union, Literal
from pydantic import BaseModel, Field


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


class AgentStep(BaseModel):
    """
    Represents a single step in the agent's reasoning process.

    This class encapsulates the details of an individual reasoning step,
    including its type, title, content, and optional metadata like duration
    for performance tracking or tool-specific data.

    :ivar id: Unique identifier for this step.
    :type id: str
    :ivar type: Type of step (thought, tool_call, tool_result, observation).
    :type type: Literal["thought", "tool_call", "tool_result", "observation"]
    :ivar title: Brief title describing this step.
    :type title: str
    :ivar content: Detailed content of this step.
    :type content: str
    :ivar timestamp: Unix timestamp in milliseconds when this step occurred.
    :type timestamp: int
    :ivar duration: Optional duration in milliseconds for this step.
    :type duration: Optional[int]
    :ivar metadata: Optional tool-specific metadata (e.g., Neo4j query results).
    :type metadata: Optional[dict]
    """
    id: str
    type: Literal["thought", "tool_call", "tool_result", "observation"]
    title: str
    content: str
    timestamp: int
    duration: Optional[int] = None
    metadata: Optional[dict] = None


class AgentContent(BaseModel):
    """
    Represents the content of an agent message with reasoning steps and final response.

    This class models the complete output of a reasoning agent, including all
    intermediate steps (thoughts, tool calls, observations) and the final response
    to the user's query.

    :ivar type: Always "agent" for agent messages.
    :type type: Literal["agent"]
    :ivar steps: List of reasoning steps taken by the agent.
    :type steps: List[AgentStep]
    :ivar finalResponse: The final response text to display to the user.
    :type finalResponse: str
    :ivar status: Current status of the agent (thinking, responding, complete, error).
    :type status: Literal["thinking", "responding", "complete", "error"]
    :ivar error: Optional error message if status is "error".
    :type error: Optional[str]
    """
    type: Literal["agent"] = "agent"
    steps: List[AgentStep] = []
    finalResponse: str = ""
    status: Literal["thinking", "responding", "complete", "error"] = "complete"
    error: Optional[str] = None


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
    type: Literal["text", "voice", "agent"]
    content: Union[str, TextContent, VoiceContent, AgentContent]  # Backwards compatible - str for legacy, objects for new types
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
    type: Literal["text", "voice", "agent"]
    content: Union[str, TextContent, VoiceContent, AgentContent]
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
    :ivar content: Actual message content or body. Can be string for text/voice
        or AgentContent for agent messages.
    :type content: Union[str, AgentContent]
    :ivar time: UNIX epoch timestamp of when the message was created.
    :type time: int
    :ivar type: Optional type of the message for categorization (text, voice, agent).
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
    :ivar steps: Agent reasoning steps (only for agent messages).
    :type steps: Optional[List[AgentStep]]
    :ivar finalResponse: Agent final response (only for agent messages).
    :type finalResponse: Optional[str]
    :ivar status: Agent status (only for agent messages).
    :type status: Optional[str]
    :ivar error: Agent error message (only for agent messages).
    :type error: Optional[str]
    """
    id: int
    conversationId: str  # Now using UUID
    roleName: str
    content: Union[str, AgentContent]  # Now supports both text and agent content
    time: int
    type: Optional[str] = "text"  # Default to "text" for backwards compatibility
    version: int = 1
    lastModified: Optional[int] = None
    rating: Optional[int] = None  # 1 for thumbs up, 0 for thumbs down, None for unrated
    # Additional fields for agent messages (flattened for backwards compatibility)
    steps: Optional[List[AgentStep]] = None
    finalResponse: Optional[str] = None
    status: Optional[str] = None
    error: Optional[str] = None


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


class StreamGenerateRequest(BaseModel):
    """
    Represents a request to stream an agent response for a conversation.

    This class is used to initiate a Server-Sent Events (SSE) stream that
    sends agent reasoning steps and final response tokens in real-time.

    :ivar conversationId: Unique identifier for the conversation.
    :type conversationId: str
    :ivar aiParticipant: Name of the AI participant. Defaults to "Assistant".
    :type aiParticipant: str
    """
    conversationId: str  # UUID
    aiParticipant: str = "Assistant"


class MessageStartEvent(BaseModel):
    """
    Metadata sent at the start of a streaming response.

    This event is sent before any reasoning steps or tokens to provide
    the frontend with message metadata (ID, timestamp) upfront, enabling
    proper message tracking even if the stream is interrupted.

    :ivar messageId: Unique identifier for the message (timestamp-based).
    :type messageId: int
    :ivar conversationId: UUID of the conversation this message belongs to.
    :type conversationId: str
    :ivar roleName: Name of the AI participant (e.g., "Assistant").
    :type roleName: str
    :ivar time: Unix timestamp (seconds) when the message was created.
    :type time: int
    :ivar type: Always "agent" for agent messages.
    :type type: Literal["agent"]
    """
    messageId: int
    conversationId: str
    roleName: str
    time: int
    type: Literal["agent"] = "agent"


class StreamEvent(BaseModel):
    """
    Represents an event in the SSE stream.

    :ivar event: Type of event (message_start, step, token, done, error).
    :type event: Literal["message_start", "step", "token", "done", "error"]
    :ivar data: Event payload (MessageStartEvent for message_start, AgentStep for step, string for token, etc.).
    :type data: Union[MessageStartEvent, AgentStep, str, dict]
    """
    event: Literal["message_start", "step", "token", "done", "error"]
    data: Union[MessageStartEvent, AgentStep, str, dict]
