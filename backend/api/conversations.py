"""
Conversation API endpoints.
"""
import json
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
from backend.database.db import get_db
from backend.security.auth import get_current_user, verify_conversation_ownership
from backend.security.logging import crud_logger
from backend.utils.hash import generate_hash, generate_sha256_hash
from backend.services.llm import generate_conversation_id

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
    print("Get conversations for user called")
    user_id = current_user['user_id']

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
                (user_id,)
            )
            conversation_rows = cur.fetchall()

            if not conversation_rows:
                response.status_code = status.HTTP_204_NO_CONTENT
                return []

            conversation_responses = []
            for conv_row in conversation_rows:
                conversation_id = conv_row['id']
                # Fetch messages for each conversation to calculate hash
                cur.execute(
                    "SELECT content FROM messages WHERE conversationId = ?",
                    (conversation_id,)
                )
                messages = cur.fetchall()
                hashsum = generate_hash(messages)

                # Parse participants (stored as JSON string)
                participants = json.loads(conv_row['participants']) if conv_row['participants'] else []

                conversation_responses.append(ConversationResponse(
                    id=conversation_id,
                    userId=conv_row['userId'],
                    name=conv_row['name'],
                    participants=participants,
                    createdAt=conv_row['createdAt'],
                    updatedAt=conv_row['updatedAt'],
                    hashsum=hashsum,
                    version=conv_row['version'] or 1,
                    lastModified=conv_row['lastModified'] or int(time.time())
                ))

            return conversation_responses

    except Exception as e:
        print(f"Error: {str(e)}")
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

    try:
        with get_db() as conn:
            cur = conn.cursor()

            # Fetch conversation details
            cur.execute("""
                        SELECT id, userId, name, participants, createdAt, updatedAt
                        FROM conversations
                        WHERE id = ? AND userId = ?
                        """, (conversation_id, user_id))

            conv_row = cur.fetchone()

            if not conv_row:
                response.status_code = status.HTTP_404_NOT_FOUND
                return ErrorResponse(error="Conversation not found")

            # Get message count
            cur.execute("SELECT COUNT(*) as count FROM messages WHERE conversationId = ?", (conversation_id,))
            message_count = cur.fetchone()['count']

            # Get all messages to compute hash
            cur.execute("SELECT content FROM messages WHERE conversationId = ? ORDER BY time", (conversation_id,))
            messages = cur.fetchall()

            # Compute SHA-256 hash of conversation content
            content_str = ''.join([msg['content'] for msg in messages if msg['content']])
            sync_hash = generate_sha256_hash(content_str) if content_str else None

            # Return conversation with details
            return ConversationWithDetails(
                id=conv_row['id'],
                userId=conv_row['userId'],
                name=conv_row['name'],
                participants=conv_row['participants'],
                createdAt=conv_row['createdAt'],
                lastModified=conv_row['updatedAt'],
                messageCount=message_count,
                syncHash=sync_hash
            )

    except Exception as e:
        print(f"Error fetching conversation: {str(e)}")
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
    with get_db() as conn:
        cur = conn.cursor()
        participants_json = json.dumps(req.participants)
        new_id = generate_conversation_id()  # Generate UUID

        cur.execute(
            "INSERT INTO conversations (id, userId, name, participants) VALUES (?, ?, ?, ?)",
            (new_id, user_id, req.name, participants_json)
        )
        conn.commit()

        cur.execute("SELECT id, userId, name, participants, createdAt, updatedAt FROM conversations WHERE id = ?",
                    (new_id,))
        new_conv_row = cur.fetchone()

        return Conversation(**dict(new_conv_row))


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

    with get_db() as conn:
        cur = conn.cursor()

        # Check if conversation exists and belongs to user
        cur.execute(
            "SELECT id FROM conversations WHERE id = ? AND userId = ?",
            (conversation_id, user_id)
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Update conversation
        cur.execute(
            "UPDATE conversations SET name = ?, updatedAt = CURRENT_TIMESTAMP WHERE id = ? AND userId = ?",
            (req.name, conversation_id, user_id)
        )
        conn.commit()

        # Return updated conversation
        cur.execute(
            "SELECT id, userId, name, participants, createdAt, updatedAt FROM conversations WHERE id = ?",
            (conversation_id,)
        )
        updated_conv = cur.fetchone()

        crud_logger.info(f"Conversation {conversation_id} renamed to '{req.name}' by user {user_id}")

        return Conversation(**dict(updated_conv))


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

    with get_db() as conn:
        cur = conn.cursor()

        # Check if conversation exists and belongs to user
        cur.execute(
            "SELECT id FROM conversations WHERE id = ? AND userId = ?",
            (conversation_id, user_id)
        )
        if not cur.fetchone():
            # Return 204 No Content if conversation doesn't exist
            return Response(status_code=status.HTTP_204_NO_CONTENT)

        # Delete all messages in the conversation
        cur.execute("DELETE FROM messages WHERE conversationId = ?", (conversation_id,))

        # Delete the conversation
        cur.execute("DELETE FROM conversations WHERE id = ? AND userId = ?", (conversation_id, user_id))

        conn.commit()

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
    print(f"Get conversation messages called - after_timestamp: {after_timestamp}")

    try:
        if not conversation_id or timestamp is None:
            response.status_code = status.HTTP_400_BAD_REQUEST
            return ErrorResponse(error="Conversation ID and latest timestamp are required")

        # Verify ownership (guests can access any conversation)
        if not verify_conversation_ownership(conversation_id, current_user['user_id'],
                                              current_user.get("is_guest", False)):
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
                    (conversation_id, after_timestamp)
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
                    (conversation_id, timestamp, min(messages_count, 30))
                )

            messages_rows = cur.fetchall()

            if messages_rows:
                messages_data = [dict(msg) for msg in messages_rows]

                # For pagination, reverse to get chronological order
                if after_timestamp is None:
                    messages_data.reverse()

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
                        cur.execute(
                            "SELECT COUNT(*) as count FROM messages WHERE conversationId = ? AND time < ?",
                            (conversation_id, oldest_fetched)
                        )
                        older_count = cur.fetchone()['count']
                        response.headers["X-Has-More-Messages"] = str(older_count > 0)
                    else:
                        # No new messages, but check if there are any messages at all
                        cur.execute(
                            "SELECT COUNT(*) as count FROM messages WHERE conversationId = ?",
                            (conversation_id,)
                        )
                        total_count = cur.fetchone()['count']
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
