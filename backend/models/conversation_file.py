"""
Conversation file: one conversation with all its messages, for export and import
(docs/conversation_file.md).
"""
from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, Field
from backend.models.message import AgentStep, MessageUsage

CONVERSATION_FILE_TYPE = "advanced-llm-chat-conversation"
CONVERSATION_FILE_VERSION = 1
MAX_IMPORTED_MESSAGES = 10000


class ConversationFileMessage(BaseModel):
    """
    One message of a conversation file. Messages have no id: the order of the
    list is the order of the conversation.

    :ivar roleName: 'user', 'Assistant' or 'system' ('assistant' is read as 'Assistant').
    :ivar type: 'text', 'voice' or 'agent'.
    :ivar time: When the message was written (ISO 8601, UTC if without a time zone).
    :ivar content: The text; for an agent message its final response.
    :ivar attachments: File references of a text message; the files are not in the file.
    :ivar rating: 1 (thumbs up), 0 (thumbs down) or None.
    :ivar steps: The reasoning steps of an agent message.
    :ivar status: The status of an agent message.
    :ivar error: The error of an agent message that failed.
    :ivar modelName: The model that wrote an agent message.
    :ivar usage: Tokens and cost of an agent message.
    """
    roleName: str
    type: Literal["text", "voice", "agent"] = "text"
    time: datetime
    content: str = ""
    attachments: Optional[List[dict]] = None
    rating: Optional[int] = Field(None, ge=0, le=1)
    steps: Optional[List[AgentStep]] = None
    status: Optional[Literal["thinking", "responding", "complete", "error"]] = None
    error: Optional[str] = None
    modelName: Optional[str] = None
    usage: Optional[MessageUsage] = None


class ConversationFileHeader(BaseModel):
    """
    The conversation of a conversation file. Without dates, the import takes
    them from the first and the last message.

    :ivar name: The conversation's name.
    :ivar createdAt: When the conversation was created.
    :ivar updatedAt: When the conversation was last changed.
    """
    name: str = Field(min_length=1, max_length=500)
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None


class ConversationFile(BaseModel):
    """
    A conversation with all its messages. Ids, the model and the agent of the
    conversation belong to one server and are not part of the file.

    :ivar type: Always CONVERSATION_FILE_TYPE.
    :ivar version: The format version, CONVERSATION_FILE_VERSION.
    :ivar exportedAt: When the file was exported.
    :ivar conversation: The conversation's name and dates.
    :ivar messages: The messages, oldest first.
    """
    type: Literal["advanced-llm-chat-conversation"]
    version: Literal[1]
    exportedAt: Optional[datetime] = None
    conversation: ConversationFileHeader
    messages: List[ConversationFileMessage] = Field(max_length=MAX_IMPORTED_MESSAGES)
