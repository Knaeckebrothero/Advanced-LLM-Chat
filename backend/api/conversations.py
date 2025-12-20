"""
Conversation API endpoints.
"""
import json
import logging
import time
from typing import List, Optional
from fastapi import APIRouter, Response, Depends, HTTPException, status
from backend.models.common import ErrorResponse
from backend.models.conversation import (
    Conversation,
    ConversationResponse,
    ConversationCreateRequest,
    ConversationUpdateRequest,
    ConversationWithDetails
)
from backend.models.message import MessageResponse
from backend.database import db
from backend.security.auth import get_current_user, verify_conversation_ownership
from backend.security.logging import crud_logger
from backend.utils.hash import generate_hash, generate_sha256_hash
from backend.services.llm import generate_conversation_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Conversation"])


@router.get("/conversations",
            response_model=List[ConversationResponse],
            responses={
                status.HTTP_204_NO_CONTENT: {"description": "No conversations found"},
                status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Internal server error"}
            })
async def get_conversations(response: Response, current_user: dict = Depends(get_current_user)):
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
    user_id = current_user['user_id']
    logger.debug(f"Get conversations called for user_id: {user_id}")

    # Guest users don't have server-side conversations
    if current_user.get("is_guest"):
        logger.debug("Guest user - returning empty conversations")
        response.status_code = status.HTTP_204_NO_CONTENT
        return []

    try:
        # Fetch conversations for the current user
        conversations = db.get_conversations_by_user(user_id)

        if not conversations:
            logger.debug(f"No conversations found for user_id: {user_id}")
            response.status_code = status.HTTP_204_NO_CONTENT
            return []

        logger.debug(f"Found {len(conversations)} conversations for user_id: {user_id}")

        conversation_responses = []
        for conv in conversations:
            conversation_id = conv['id']
            # Fetch messages for each conversation to calculate hash
            messages = db.get_messages_by_conversation(conversation_id, limit=1000)
            message_contents = [{'content': m['content']} for m in messages]
            hashsum = generate_hash(message_contents)

            # Parse participants (stored as JSON string)
            participants = json.loads(conv['participants']) if conv['participants'] else []

            conversation_responses.append(ConversationResponse(
                id=conversation_id,
                userId=conv['userId'],
                name=conv['name'],
                participants=participants,
                createdAt=conv['createdAt'],
                updatedAt=conv['updatedAt'],
                hashsum=hashsum,
                version=conv['version'] or 1,
                lastModified=conv['lastModified'] or int(time.time())
            ))

        logger.info(f"Returning {len(conversation_responses)} conversations for user_id: {user_id}")
        return conversation_responses

    except Exception as e:
        logger.error(f"Error fetching conversations for user_id {user_id}: {str(e)}", exc_info=True)
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return ErrorResponse(error=str(e))


@router.get("/conversation/{conversation_id}",
            response_model=ConversationWithDetails,
            responses={
                status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Conversation not found"},
                status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Access denied"}
            })
async def get_conversation(conversation_id: str, response: Response, current_user: dict = Depends(get_current_user)):
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
    user_id = current_user['user_id']
    logger.debug(f"Get conversation {conversation_id} for user_id: {user_id}")

    try:
        # Fetch conversation details
        conv = db.get_conversation_by_id(conversation_id, user_id)

        if not conv:
            logger.debug(f"Conversation {conversation_id} not found for user_id: {user_id}")
            response.status_code = status.HTTP_404_NOT_FOUND
            return ErrorResponse(error="Conversation not found")

        # Get message count
        message_count = db.get_message_count(conversation_id)

        # Get all messages to compute hash
        messages = db.get_messages_by_conversation(conversation_id, limit=1000)

        # Compute SHA-256 hash of conversation content
        content_str = ''.join([msg['content'] for msg in messages if msg.get('content')])
        sync_hash = generate_sha256_hash(content_str) if content_str else None

        # Parse participants (stored as JSON string)
        participants = json.loads(conv['participants']) if conv['participants'] else []

        logger.debug(f"Returning conversation {conversation_id} with {message_count} messages")

        # Return conversation with details
        return ConversationWithDetails(
            id=conv['id'],
            userId=conv['userId'],
            name=conv['name'],
            participants=participants,
            createdAt=conv['createdAt'],
            lastModified=conv['updatedAt'],
            messageCount=message_count,
            syncHash=sync_hash
        )

    except Exception as e:
        logger.error(f"Error fetching conversation {conversation_id}: {str(e)}", exc_info=True)
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return ErrorResponse(error=str(e))


@router.post("/conversation/create",
             response_model=Conversation,
             status_code=status.HTTP_201_CREATED)
async def create_conversation(req: ConversationCreateRequest, current_user: dict = Depends(get_current_user)):
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
    user_id = current_user['user_id']
    logger.debug(f"Creating conversation for user_id: {user_id}, name: {req.name}")

    participants_json = json.dumps(req.participants)
    new_id = generate_conversation_id()  # Generate UUID

    new_conv = db.create_conversation(
        conversation_id=new_id,
        user_id=user_id,
        name=req.name,
        participants=participants_json
    )

    crud_logger.info(f"Conversation created - id: {new_id}, user_id: {user_id}, name: {req.name}")

    return Conversation(**new_conv)


@router.patch("/conversation/{conversation_id}",
              response_model=Conversation)
async def update_conversation(
        conversation_id: str,
        req: ConversationUpdateRequest,
        current_user: dict = Depends(get_current_user)
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
    user_id = current_user['user_id']
    logger.debug(f"Updating conversation {conversation_id} for user_id: {user_id}")

    # Check if conversation exists and belongs to user
    existing = db.get_conversation_by_id(conversation_id, user_id)
    if not existing:
        logger.debug(f"Conversation {conversation_id} not found for update")
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Update conversation
    updated_conv = db.update_conversation(
        conversation_id=conversation_id,
        user_id=user_id,
        name=req.name
    )

    crud_logger.info(f"Conversation {conversation_id} renamed to '{req.name}' by user {user_id}")

    return Conversation(**updated_conv)


@router.delete("/conversation/{conversation_id}",
               status_code=status.HTTP_200_OK)
async def delete_conversation(
        conversation_id: str,
        current_user: dict = Depends(get_current_user)
):
    """
    Deletes a conversation along with all its associated messages for the
    current user. If the specified conversation does not exist or does not
    belong to the user, a 204 No Content response is returned.

    :param current_user: Dictionary containing details of the currently authorized user.
    :param conversation_id: The unique identifier of the conversation to be deleted.
    :type conversation_id: str
    """
    user_id = current_user['user_id']
    logger.debug(f"Deleting conversation {conversation_id} for user_id: {user_id}")

    # Delete conversation (messages are cascade-deleted via ON DELETE CASCADE)
    deleted = db.delete_conversation(conversation_id, user_id)

    if not deleted:
        # Return 204 No Content if conversation doesn't exist
        logger.debug(f"Conversation {conversation_id} not found for deletion")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    crud_logger.info(f"Conversation {conversation_id} and all messages deleted by user {user_id}")

    return {"message": "Conversation deleted successfully"}


@router.get("/conversation/messages/{conversation_id}/{timestamp}/{messages_count}",
            response_model=List[MessageResponse],
            responses={
                status.HTTP_204_NO_CONTENT: {"description": "No messages found"},
                status.HTTP_206_PARTIAL_CONTENT: {"description": "Partial content, more messages available"},
                status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "Conversation ID or timestamp missing"},
                status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Access denied"},
                status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Conversation not found"},
                status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Internal server error"}
            })
async def get_conversation_messages(
        conversation_id: str,
        timestamp: int,
        messages_count: int,
        response: Response,
        current_user: dict = Depends(get_current_user),
        after_timestamp: Optional[int] = None
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
    logger.debug(f"Get conversation messages - conversation_id: {conversation_id}, "
                 f"timestamp: {timestamp}, after_timestamp: {after_timestamp}")

    try:
        if not conversation_id or timestamp is None:
            logger.warning("Missing conversation_id or timestamp in request")
            response.status_code = status.HTTP_400_BAD_REQUEST
            return ErrorResponse(error="Conversation ID and latest timestamp are required")

        # Verify ownership (guests can access any conversation)
        if not verify_conversation_ownership(conversation_id, current_user['user_id'],
                                              current_user.get("is_guest", False)):
            logger.warning(f"Access denied for user {current_user['user_id']} to conversation {conversation_id}")
            response.status_code = status.HTTP_403_FORBIDDEN
            return ErrorResponse(error="Access denied to this conversation")

        # Different queries for incremental sync vs pagination
        if after_timestamp is not None:
            # Incremental sync: get messages newer than after_timestamp
            messages = db.get_messages_by_conversation(
                conversation_id,
                after_timestamp=after_timestamp
            )
        else:
            # Normal pagination: get messages before timestamp
            limit = min(messages_count, 30)
            messages = db.get_messages_by_conversation(
                conversation_id,
                before_timestamp=timestamp,
                limit=limit
            )

        if messages:
            messages_data = messages
            logger.debug(f"Retrieved {len(messages)} messages for conversation {conversation_id}")

            # For pagination, reverse to get chronological order (already DESC from DB)
            if after_timestamp is None:
                messages_data = list(reversed(messages_data))

            # Format agent messages for frontend (new JSONB schema)
            for msg in messages_data:
                if msg.get('type') == 'agent':
                    # Transform JSONB columns to frontend-expected format
                    # Steps come directly as array from JSONB
                    msg['steps'] = msg.get('agent_steps', [])
                    msg['finalResponse'] = msg.get('final_response', '')
                    msg['status'] = msg.get('agent_status', 'complete')
                    msg['error'] = msg.get('agent_error')

                    # Clean up internal column names
                    msg.pop('agent_steps', None)
                    msg.pop('final_response', None)
                    msg.pop('agent_status', None)
                    msg.pop('agent_error', None)
                elif msg.get('type') == 'text' or not msg.get('type'):
                    # Parse JSON content for text messages with attachments
                    content = msg.get('content', '')
                    if content and isinstance(content, str) and content.startswith('{'):
                        try:
                            content_obj = json.loads(content)
                            if isinstance(content_obj, dict) and 'content' in content_obj:
                                msg['content'] = content_obj.get('content', '')
                                if 'attachments' in content_obj:
                                    msg['attachments'] = content_obj['attachments']
                        except json.JSONDecodeError:
                            # Not valid JSON, keep as-is
                            pass

            # Check if there might be more messages
            has_more = False
            if after_timestamp is None and messages_count > 30 and len(messages_data) == 30:
                has_more = True
                response.status_code = status.HTTP_206_PARTIAL_CONTENT
            else:
                response.status_code = status.HTTP_200_OK

            # Add header to indicate if more messages exist
            if after_timestamp is not None:
                # For incremental sync, check if there are any messages we didn't fetch
                if messages_data:
                    oldest_fetched = messages_data[0]['time']
                    total_count = db.get_message_count(conversation_id)
                    older_messages = db.get_messages_by_conversation(
                        conversation_id,
                        before_timestamp=oldest_fetched,
                        limit=1
                    )
                    response.headers["X-Has-More-Messages"] = str(len(older_messages) > 0)
                else:
                    # No new messages, but check if there are any messages at all
                    total_count = db.get_message_count(conversation_id)
                    response.headers["X-Has-More-Messages"] = str(total_count > 0)
            else:
                # For initial load, use the has_more flag
                response.headers["X-Has-More-Messages"] = str(has_more)

            return messages_data
        else:
            # Return empty list instead of None to satisfy response model
            response.status_code = status.HTTP_200_OK
            # Add header for incremental sync
            if after_timestamp is not None:
                response.headers["X-Has-More-Messages"] = "false"
            return []

    except Exception as e:
        logger.error(f"Error in get_conversation_messages for {conversation_id}: {str(e)}", exc_info=True)
        # Return empty list on error to satisfy the response model
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return []
