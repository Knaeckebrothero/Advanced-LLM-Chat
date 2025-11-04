"""
Message API endpoints.
"""
import json
import time
from typing import Dict
from fastapi import APIRouter, Response, Depends, HTTPException, status
from backend.models.common import ErrorResponse
from backend.models.message import (
    ApiMessageSend,
    ApiMessageGenerate,
    ApiMessageSendAndGenerate,
    MessagePatch,
    MessageResponse,
    SendAndGenerateResponse,
    RateMessageRequest,
    RegenerateMessageRequest
)
from backend.database.db import get_db
from backend.security.auth import get_current_user, verify_conversation_ownership, rate_limit_guest
from backend.security.logging import crud_logger
from backend.services.llm import get_conversation_context, generate_llm_response
from backend.config import DEFAULT_MODEL, DEFAULT_TEMPERATURE, DEFAULT_TOP_P, DEFAULT_SYSTEM_PROMPT

router = APIRouter(prefix="/api/message", tags=["Message"])


@router.post("/send",
             response_model=Dict[str, int],
             status_code=status.HTTP_201_CREATED,
             responses={
                 status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "Message content cannot be empty"},
                 status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Access denied"},
                 status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse,
                                                          "description": "Internal server error"}
             })
async def user_send_message(request_body: ApiMessageSend, response: Response,
                             current_user: dict = Depends(get_current_user)):
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
        f"Message send called - User: {current_user['user_id']}, Conversation: {request_body.conversationId}")

    try:
        if not request_body.content:
            response.status_code = status.HTTP_400_BAD_REQUEST
            return ErrorResponse(error="Message content cannot be empty")

        # Verify ownership
        if not verify_conversation_ownership(request_body.conversationId, current_user['user_id'],
                                              current_user.get("is_guest", False)):
            response.status_code = status.HTTP_403_FORBIDDEN
            return ErrorResponse(error="Access denied to this conversation")

        message_id = int(time.time() * 1000)

        # Extract content based on message type
        content_str = ""
        message_type = getattr(request_body, 'type', 'text')  # Default to 'text' for backwards compatibility

        if message_type == 'text':
            if isinstance(request_body.content, str):
                # Legacy format - just a string
                content_str = request_body.content
            elif isinstance(request_body.content, dict):
                # New format - TextContent object
                content_str = request_body.content.get('content', '')
                # Store attachments as JSON in content for now
                attachments = request_body.content.get('attachments', [])
                if attachments:
                    content_obj = {
                        'content': content_str,
                        'attachments': attachments
                    }
                    content_str = json.dumps(content_obj)
        elif message_type == 'voice':
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
                (message_id, request_body.conversationId, request_body.roleName,
                 content_str, request_body.time, message_type,
                 request_body.version or 1, request_body.lastModified or int(time.time()))
            )
            conn.commit()

        crud_logger.info(f"Message sent successfully - Message ID: {message_id}")
        return {"id": message_id}

    except Exception as e:
        crud_logger.error(f"Error sending message: {str(e)}", exc_info=True)
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return ErrorResponse(error=f"Failed to send message: {str(e)}. Please try again later.")


@router.post("/generate",
             response_model=MessageResponse,
             status_code=status.HTTP_201_CREATED,
             responses={
                 status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "Conversation ID missing"},
                 status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Access denied"},
                 status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse,
                                                          "description": "Internal server error"}
             },
             dependencies=[Depends(rate_limit_guest)])
async def generate_message(request_body: ApiMessageGenerate, response: Response,
                            current_user: dict = Depends(get_current_user)):
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
        f"Generate message called - User: {current_user['user_id']}, Conversation: {request_body.conversationId}")

    try:
        # Verify ownership
        if not verify_conversation_ownership(request_body.conversationId, current_user['user_id'],
                                              current_user.get("is_guest", False)):
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
            DEFAULT_MODEL
        )

        message_id = int(time.time() * 1000)
        current_time = int(time.time())

        message_doc_data = {
            'id': message_id,
            'conversationId': request_body.conversationId,
            'roleName': request_body.roleName,
            'content': ai_response_content,
            'time': current_time,
            'version': 1,
            'lastModified': current_time
        }

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO messages (id, conversationId, roleName, content, time, type, version, lastModified)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (message_id, request_body.conversationId, request_body.roleName,
                 message_doc_data['content'], current_time, 'text', 1, current_time)
            )
            conn.commit()

        return message_doc_data

    except Exception as e:
        print(f"Error: {str(e)}")
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return ErrorResponse(error=str(e))


@router.patch("/patch",
              response_model=MessageResponse,
              status_code=status.HTTP_200_OK,
              responses={
                  status.HTTP_400_BAD_REQUEST: {"description": "Message ID missing or invalid request"},
                  status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Access denied"},
                  status.HTTP_404_NOT_FOUND: {"description": "Message not found"},
                  status.HTTP_409_CONFLICT: {"model": ErrorResponse, "description": "Version conflict"},
                  status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse,
                                                           "description": "Internal server error"}
              })
async def patch_message(request_body: MessagePatch, response: Response,
                        current_user: dict = Depends(get_current_user)):
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
        f"Patch message called - User: {current_user['user_id']}, Message: {request_body.id}, Conversation: {request_body.conversationId}")

    try:
        if not request_body.id:
            response.status_code = status.HTTP_400_BAD_REQUEST
            return Response(status_code=status.HTTP_400_BAD_REQUEST, content="Message ID missing")

        # Verify ownership
        if not verify_conversation_ownership(request_body.conversationId, current_user['user_id'],
                                              current_user.get("is_guest", False)):
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
                (request_body.id, request_body.conversationId)
            )
            result = cur.fetchone()

            if not result:
                response.status_code = status.HTTP_404_NOT_FOUND
                return Response(status_code=status.HTTP_404_NOT_FOUND, content="Message not found")

            current_version = result[0] or 1

            # Check for version conflict
            if current_version != request_body.version:
                response.status_code = status.HTTP_409_CONFLICT
                return ErrorResponse(
                    error=f"Version conflict: current version is {current_version}, provided version is {request_body.version}")

            # Update with version increment
            new_version = current_version + 1
            cur.execute(
                """
                UPDATE messages
                SET content = ?, version = ?, lastModified = ?
                WHERE id = ? AND conversationId = ? AND version = ?
                """,
                (request_body.content, new_version, int(time.time()),
                 request_body.id, request_body.conversationId, request_body.version)
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
                (request_body.id, request_body.conversationId)
            )
            updated_row = cur.fetchone()

            if updated_row:
                # Parse content based on type
                message_type = updated_row['type'] or 'text'
                content = updated_row['content']

                # Try to parse JSON content for complex types
                try:
                    if message_type == 'text' and content.startswith('{'):
                        content_obj = json.loads(content)
                        if 'content' in content_obj:
                            content = content_obj['content']
                except:
                    pass  # Use content as-is if not JSON

                crud_logger.info(
                    f"Message patched successfully - Message ID: {request_body.id}, New version: {new_version}")
                return MessageResponse(
                    id=updated_row['id'],
                    conversationId=updated_row['conversationId'],
                    roleName=updated_row['roleName'],
                    content=content,
                    time=updated_row['time'],
                    type=message_type,
                    version=updated_row['version'],
                    lastModified=updated_row['lastModified'],
                    rating=updated_row['rating']
                )

        return None

    except Exception as e:
        crud_logger.error(f"Error patching message: {str(e)}", exc_info=True)
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return ErrorResponse(error=f"Failed to update message: {str(e)}. Please refresh and try again.")


@router.delete("/delete/{conversation_id}/{message_id}",
               status_code=status.HTTP_204_NO_CONTENT,
               responses={
                   status.HTTP_400_BAD_REQUEST: {"description": "Conversation ID or Message ID missing"},
                   status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Access denied"},
                   status.HTTP_404_NOT_FOUND: {"description": "Message not found"},
                   status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse,
                                                            "description": "Internal server error"}
               })
async def delete_message(conversation_id: str, message_id: int, response: Response,
                         current_user: dict = Depends(get_current_user)):
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
        f"Delete message called - User: {current_user['user_id']}, Message: {message_id}, Conversation: {conversation_id}")

    try:
        if not conversation_id or not message_id:
            response.status_code = status.HTTP_400_BAD_REQUEST
            return Response(status_code=status.HTTP_400_BAD_REQUEST,
                            content="Conversation ID or Message ID missing")

        # Verify ownership
        if not verify_conversation_ownership(conversation_id, current_user['user_id'],
                                              current_user.get("is_guest", False)):
            response.status_code = status.HTTP_403_FORBIDDEN
            return ErrorResponse(error="Access denied to this conversation")

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM messages WHERE conversationId = ? AND id = ?",
                (conversation_id, message_id)
            )
            conn.commit()

            if cur.rowcount == 0:
                crud_logger.warning(f"Message not found for deletion - Message ID: {message_id}")
                response.status_code = status.HTTP_404_NOT_FOUND
                return Response(status_code=status.HTTP_404_NOT_FOUND, content="Message not found")

        crud_logger.info(f"Message deleted successfully - Message ID: {message_id}")
        return None

    except Exception as e:
        crud_logger.error(f"Error deleting message: {str(e)}", exc_info=True)
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return ErrorResponse(
            error=f"Failed to delete message: {str(e)}. Please check your connection and try again.")


@router.post("/rate",
             response_model=MessageResponse,
             status_code=status.HTTP_200_OK,
             responses={
                 status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "Invalid request"},
                 status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Access denied"},
                 status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Message not found"},
                 status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse,
                                                          "description": "Internal server error"}
             })
async def rate_message(request_body: RateMessageRequest, response: Response,
                       current_user: dict = Depends(get_current_user)):
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
        f"Rate message called - User: {current_user['user_id']}, Message: {request_body.id}, Rating: {request_body.rating}")

    try:
        # Validate rating value (None is allowed to remove rating)
        if request_body.rating is not None and request_body.rating not in [0, 1]:
            response.status_code = status.HTTP_400_BAD_REQUEST
            return ErrorResponse(error="Rating must be 0 (thumbs down), 1 (thumbs up), or null to remove rating")

        # Verify ownership
        if not verify_conversation_ownership(request_body.conversationId, current_user['user_id'],
                                              current_user.get("is_guest", False)):
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
                (request_body.rating, request_body.id, request_body.conversationId)
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
                (request_body.id, request_body.conversationId)
            )

            row = cur.fetchone()
            if row:
                # Parse content based on type
                message_type = row['type'] or 'text'
                content = row['content']

                # Try to parse JSON content for complex types
                try:
                    if message_type == 'text' and content.startswith('{'):
                        content_obj = json.loads(content)
                        if 'content' in content_obj:
                            content = content_obj['content']
                except:
                    pass  # Use content as-is if not JSON

                rating_text = "removed" if request_body.rating is None else str(request_body.rating)
                crud_logger.info(f"Message rated successfully - Message ID: {request_body.id}, Rating: {rating_text}")
                return MessageResponse(
                    id=row['id'],
                    conversationId=row['conversationId'],
                    roleName=row['roleName'],
                    content=content,
                    time=row['time'],
                    type=message_type,
                    version=row['version'],
                    lastModified=row['lastModified'],
                    rating=row['rating']
                )

        return None

    except Exception as e:
        crud_logger.error(f"Error rating message: {str(e)}", exc_info=True)
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return ErrorResponse(error=f"Failed to rate message: {str(e)}")


@router.post("/regenerate",
             response_model=MessageResponse,
             status_code=status.HTTP_200_OK,
             responses={
                 status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "Invalid request"},
                 status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Access denied"},
                 status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Message not found"},
                 status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse,
                                                          "description": "Internal server error"}
             },
             dependencies=[Depends(rate_limit_guest)])
async def regenerate_message(request_body: RegenerateMessageRequest, response: Response,
                              current_user: dict = Depends(get_current_user)):
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
    crud_logger.info(f"Regenerate message called - User: {current_user['user_id']}, Message: {request_body.id}")

    try:
        # Verify ownership
        if not verify_conversation_ownership(request_body.conversationId, current_user['user_id'],
                                              current_user.get("is_guest", False)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this conversation"
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
                (request_body.id, request_body.conversationId)
            )

            message_row = cur.fetchone()
            if not message_row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Message not found"
                )

            # Verify it's an AI message
            if message_row['roleName'] == 'user':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Can only regenerate AI messages"
                )

            # Get all messages before this one
            cur.execute(
                """
                SELECT roleName, content, time
                FROM messages
                WHERE conversationId = ? AND time < ?
                ORDER BY time ASC
                """,
                (request_body.conversationId, message_row['time'])
            )

            previous_messages = cur.fetchall()

            # Build conversation context
            context_messages = []
            for msg in previous_messages:
                context_messages.append({
                    "role": "user" if msg['roleName'] == 'user' else "assistant",
                    "content": msg['content']
                })

            # Build prompt from context messages
            prompt_lines = []
            for msg in context_messages:
                role = "User" if msg['role'] == 'user' else "Assistant"
                prompt_lines.append(f"{role}: {msg['content']}")
            prompt_lines.append("Assistant:")
            prompt = "\n".join(prompt_lines)

            # Generate new AI response
            ai_response_content = await generate_llm_response(
                prompt,
                DEFAULT_TEMPERATURE,
                DEFAULT_TOP_P,
                DEFAULT_SYSTEM_PROMPT,
                DEFAULT_MODEL
            )

            # Update the message with new content
            new_version = (message_row['version'] if message_row['version'] else 1) + 1
            current_time = int(time.time())

            cur.execute(
                """
                UPDATE messages
                SET content = ?, version = ?, lastModified = ?
                WHERE id = ? AND conversationId = ?
                """,
                (ai_response_content, new_version, current_time, request_body.id, request_body.conversationId)
            )

            conn.commit()

            # Fetch and return the updated message
            cur.execute(
                """
                SELECT id, conversationId, roleName, content, time, type, version, lastModified, rating
                FROM messages
                WHERE id = ? AND conversationId = ?
                """,
                (request_body.id, request_body.conversationId)
            )

            row = cur.fetchone()
            if row:
                crud_logger.info(f"Message regenerated successfully - Message ID: {request_body.id}")
                return MessageResponse(
                    id=row['id'],
                    conversationId=row['conversationId'],
                    roleName=row['roleName'],
                    content=row['content'],
                    time=row['time'],
                    type=row['type'] or 'text',
                    version=row['version'],
                    lastModified=row['lastModified'],
                    rating=row['rating']
                )

        return None

    except Exception as e:
        crud_logger.error(f"Error regenerating message: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to regenerate message: {str(e)}"
        )


@router.post("/send-and-generate",
             response_model=SendAndGenerateResponse,
             status_code=status.HTTP_201_CREATED,
             responses={
                 status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "Invalid request"},
                 status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Access denied"},
                 status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse,
                                                          "description": "Internal server error"}
             })
async def send_and_generate_message(
        request_body: ApiMessageSendAndGenerate,
        response: Response,
        current_user: dict = Depends(get_current_user)
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
        if not verify_conversation_ownership(request_body.conversationId, current_user['user_id'],
                                              current_user.get("is_guest", False)):
            response.status_code = status.HTTP_403_FORBIDDEN
            return ErrorResponse(error="Access denied to this conversation")

        user_message_id = int(time.time() * 1000)
        content_str = ""
        message_type = request_body.type
        if message_type == 'text':
            if isinstance(request_body.content, str):
                content_str = request_body.content
            elif isinstance(request_body.content, dict):
                content_str = request_body.content.get('content', '')
                attachments = request_body.content.get('attachments', [])
                if attachments:
                    content_obj = {'content': content_str, 'attachments': attachments}
                    content_str = json.dumps(content_obj)
        elif message_type == 'voice':
            content_str = json.dumps(request_body.content) if isinstance(request_body.content, dict) else str(
                request_body.content)

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO messages (id, conversationId, roleName, content, time, type, version, lastModified)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_message_id, request_body.conversationId, request_body.roleName,
                 content_str, request_body.time, message_type,
                 request_body.version or 1, request_body.lastModified or int(time.time()))
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
            lastModified=request_body.lastModified or int(time.time())
        )

        ai_message_response = None
        if request_body.generateResponse:
            context = await get_conversation_context(request_body.conversationId, limit=6)

            # ** THE FIX IS HERE **
            # The backend now uses its own default values for the LLM.
            ai_response_content = await generate_llm_response(
                context,
                DEFAULT_TEMPERATURE,
                DEFAULT_TOP_P,
                DEFAULT_SYSTEM_PROMPT,
                DEFAULT_MODEL
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
                    (ai_message_id, request_body.conversationId, request_body.aiParticipant,
                     ai_response_content, current_time, 'text', 1, current_time)
                )
                conn.commit()

            ai_message_response = MessageResponse(
                id=ai_message_id,
                conversationId=request_body.conversationId,
                roleName=request_body.aiParticipant,
                content=ai_response_content,
                time=current_time,
                type='text',
                version=1,
                lastModified=current_time
            )

        return SendAndGenerateResponse(
            userMessage=user_message_response,
            aiMessage=ai_message_response
        )

    except Exception as e:
        print(f"Error in send_and_generate: {str(e)}")
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return ErrorResponse(error=str(e))
