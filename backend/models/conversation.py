"""
Conversation-related models.
"""
from typing import Dict, List, Optional
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
    :ivar modelId: The catalog model of the conversation; None means the user's default model.
    :type modelId: Optional[int]
    :ivar personaId: The persona of the conversation; None means no persona.
    :type personaId: Optional[int]
    :ivar personaValues: Values for the persona's variables.
    :type personaValues: Optional[Dict[str, str]]
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
    # Model catalog selection
    modelId: Optional[int] = None
    personaId: Optional[int] = None
    personaValues: Optional[Dict[str, str]] = None


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
    :ivar modelId: The catalog model of the conversation; None means the user's default model.
    :type modelId: Optional[int]
    :ivar personaId: The persona of the conversation; None means no persona.
    :type personaId: Optional[int]
    :ivar personaValues: Values for the persona's variables.
    :type personaValues: Optional[Dict[str, str]]
    """
    id: str
    userId: int
    name: str
    participants: Optional[str] = None
    createdAt: datetime
    updatedAt: datetime
    # Model catalog selection
    modelId: Optional[int] = None
    personaId: Optional[int] = None
    personaValues: Optional[Dict[str, str]] = None

    @classmethod
    def from_row(cls, row: dict) -> "Conversation":
        """
        Build the API model from a conversations row (snake_case catalog columns).

        :param row: A row from the conversations table.
        :type row: dict
        :return: The conversation as returned by the API.
        :rtype: Conversation
        """
        return cls(
            id=row['id'],
            userId=row['userId'],
            name=row['name'],
            participants=row.get('participants'),
            createdAt=row['createdAt'],
            updatedAt=row['updatedAt'],
            modelId=row.get('model_id'),
            personaId=row.get('persona_id'),
            personaValues=row.get('persona_values'),
        )


class ConversationCreateRequest(BaseModel):
    """
    Represents a request to create a new conversation.

    This class is used to encapsulate the necessary data for creating a new
    conversation, including the name of the conversation and the list of participants.

    :ivar name: The name of the conversation to be created.
    :type name: str
    :ivar participants: A list of participants to be included in the conversation.
    :type participants: List[str]
    :ivar modelId: Optional catalog model; None means the user's default model.
    :type modelId: Optional[int]
    :ivar personaId: Optional persona; None means no persona.
    :type personaId: Optional[int]
    :ivar personaValues: Optional values for the persona's variables.
    :type personaValues: Optional[Dict[str, str]]
    """
    name: str
    participants: List[str]
    modelId: Optional[int] = None
    personaId: Optional[int] = None
    personaValues: Optional[Dict[str, str]] = None


class ConversationUpdateRequest(BaseModel):
    """
    Represents a request to update an existing conversation.

    Only the fields that are sent change. For the catalog fields, null clears
    the selection (the user's default model, no persona); clearing the persona
    also clears its values unless personaValues is sent as well.

    :ivar name: The new name for the conversation (optional).
    :type name: Optional[str]
    :ivar modelId: The new catalog model, or None for the user's default model.
    :type modelId: Optional[int]
    :ivar personaId: The new persona, or None for no persona.
    :type personaId: Optional[int]
    :ivar personaValues: New values for the persona's variables.
    :type personaValues: Optional[Dict[str, str]]
    """
    name: Optional[str] = None
    modelId: Optional[int] = None
    personaId: Optional[int] = None
    personaValues: Optional[Dict[str, str]] = None


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
