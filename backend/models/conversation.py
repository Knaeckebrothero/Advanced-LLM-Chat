"""
Conversation-related models.
"""
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel


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


class ConversationUpdateRequest(BaseModel):
    """
    Represents a request to update an existing conversation.

    :ivar name: The new name for the conversation.
    :type name: str
    """
    name: str


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
