"""
Message API endpoints.
"""
import json
import logging
import time
import asyncio
import uuid
from collections import defaultdict
from typing import Dict, AsyncGenerator
from fastapi import APIRouter, Response, Depends, HTTPException, status
from sse_starlette.sse import EventSourceResponse
from backend.models.common import ErrorResponse
from backend.models.message import (
    ApiMessageSend,
    ApiMessageGenerate,
    ApiMessageSendAndGenerate,
    MessagePatch,
    MessageResponse,
    SendAndGenerateResponse,
    RateMessageRequest,
    RegenerateMessageRequest,
    StreamGenerateRequest,
    AgentStep,
    MessageStartEvent
)
from backend.database import db
from backend.security.auth import get_current_user, verify_conversation_ownership, rate_limit_guest
from backend.security.logging import crud_logger
from backend.services.llm import get_conversation_context, generate_llm_response
from backend.config import DEFAULT_MODEL, DEFAULT_TEMPERATURE, DEFAULT_TOP_P, DEFAULT_SYSTEM_PROMPT
from backend.services.agent import create_fessi_agent
from backend.services.llm_provider import is_provider_available
from backend.services.image_handler import extract_image_attachments, extract_document_attachments, extract_audio_attachments
from backend.services.conversation_history import ConversationHistoryBuilder
from backend.models.attachments import AttachmentType
from backend.services.tts_handler import (
    generate_speech,
    get_tts_audio_path,
    get_cached_tts_audio,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/message", tags=["Message"])


def _save_agent_message(
    message_id: int,
    conversation_id: str,
    role_name: str,
    msg_time: int,
    content
) -> None:
    """
    Save an agent message using JSONB storage.

    Extracts agent fields from various input formats and calls
    db.create_agent_message with proper column storage.
    """
    logger.debug(f"Saving agent message - id: {message_id}, conversation: {conversation_id}")

    # Handle different input formats
    if hasattr(content, 'model_dump'):
        agent_data = content.model_dump()
    elif isinstance(content, dict):
        agent_data = content
    else:
        # Fallback for string content
        agent_data = {
            'finalResponse': str(content),
            'steps': [],
            'status': 'complete'
        }

    # Extract fields with defaults
    steps = agent_data.get('steps', [])
    final_response = agent_data.get('finalResponse', '')
    agent_status = agent_data.get('status', 'complete')
    error = agent_data.get('error')

    logger.debug(f"Agent message has {len(steps)} steps, status: {agent_status}")

    db.create_agent_message(
        message_id=message_id,
        conversation_id=conversation_id,
        role_name=role_name,
        time=msg_time,
        final_response=final_response,
        status=agent_status,
        error=error,
        steps=steps
    )


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
    Handles the sending of a message in a conversation.
    """
    crud_logger.info(
        f"Message send called - User: {current_user['user_id']}, Conversation: {request_body.conversationId}")

    try:
        if not request_body.content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Message content cannot be empty"
            )

        # Verify ownership
        if not verify_conversation_ownership(request_body.conversationId, current_user['user_id'],
                                              current_user.get("is_guest", False)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this conversation"
            )

        message_id = int(time.time() * 1000)

        # Extract content based on message type
        content_str = ""
        message_type = getattr(request_body, 'type', 'text')

        if message_type == 'text':
            # Check for top-level attachments (frontend sends them alongside content, not inside it)
            top_level_attachments = getattr(request_body, 'attachments', None)

            if isinstance(request_body.content, str):
                content_str = request_body.content
                # Check for top-level attachments when content is a plain string
                if top_level_attachments:
                    content_obj = {
                        'content': content_str,
                        'attachments': top_level_attachments
                    }
                    content_str = json.dumps(content_obj)
                    crud_logger.info(f"Stored message with {len(top_level_attachments)} attachment(s) from top-level")
            elif isinstance(request_body.content, dict):
                content_str = request_body.content.get('content', '')
                attachments = request_body.content.get('attachments', [])
                # Also check top-level attachments if none in content
                if not attachments and top_level_attachments:
                    attachments = top_level_attachments
                if attachments:
                    content_obj = {
                        'content': content_str,
                        'attachments': attachments
                    }
                    content_str = json.dumps(content_obj)
                    crud_logger.info(f"Stored message with {len(attachments)} attachment(s) from dict")
            elif hasattr(request_body.content, 'content'):
                # Handle TextContent model - include attachments if present
                content_str = request_body.content.content
                attachments = getattr(request_body.content, 'attachments', None)
                # Also check top-level attachments
                if not attachments and top_level_attachments:
                    attachments = top_level_attachments
                if attachments:
                    # Convert FileReference models or dicts to JSON-serializable dicts
                    attachment_dicts = []
                    for att in attachments:
                        if hasattr(att, 'model_dump'):
                            attachment_dicts.append(att.model_dump())
                        elif isinstance(att, dict):
                            attachment_dicts.append(att)
                    if attachment_dicts:
                        content_obj = {
                            'content': content_str,
                            'attachments': attachment_dicts
                        }
                        content_str = json.dumps(content_obj)
                        crud_logger.info(f"Stored message with {len(attachment_dicts)} attachment(s) from TextContent model")
        elif message_type == 'voice':
            if isinstance(request_body.content, dict):
                content_str = json.dumps(request_body.content)
            elif hasattr(request_body.content, 'model_dump'):
                content_str = json.dumps(request_body.content.model_dump())
            else:
                content_str = str(request_body.content)
        elif message_type == 'agent':
            # Use JSONB storage for agent messages (same as streaming endpoint)
            _save_agent_message(
                message_id=message_id,
                conversation_id=request_body.conversationId,
                role_name=request_body.roleName,
                msg_time=request_body.time,
                content=request_body.content
            )
            crud_logger.info(f"Agent message sent successfully - Message ID: {message_id}")
            return {"id": message_id}

        # For text/voice messages, use regular message storage
        db.create_message(
            message_id=message_id,
            conversation_id=request_body.conversationId,
            role_name=request_body.roleName,
            content=content_str,
            time=request_body.time,
            msg_type=message_type,
            version=request_body.version or 1,
            last_modified=request_body.lastModified or int(time.time())
        )

        crud_logger.info(f"Message sent successfully - Message ID: {message_id}")
        return {"id": message_id}

    except HTTPException:
        raise
    except Exception as e:
        crud_logger.error(f"Error sending message: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send message: {str(e)}. Please try again later."
        )


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
    Generates a message for a conversation based on the provided context.
    """
    crud_logger.info(
        f"Generate message called - User: {current_user['user_id']}, Conversation: {request_body.conversationId}")

    try:
        # Verify ownership
        if not verify_conversation_ownership(request_body.conversationId, current_user['user_id'],
                                              current_user.get("is_guest", False)):
            logger.warning(f"Access denied for user {current_user['user_id']} to conversation {request_body.conversationId}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this conversation"
            )

        if not request_body.conversationId:
            logger.warning("Generate message called without conversation ID")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Conversation ID missing or invalid in request"
            )

        # Get conversation context for the LLM
        logger.debug(f"Getting conversation context for {request_body.conversationId}")
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

        message_doc = db.create_message(
            message_id=message_id,
            conversation_id=request_body.conversationId,
            role_name=request_body.roleName,
            content=ai_response_content,
            time=current_time,
            msg_type='text',
            version=1,
            last_modified=current_time
        )

        logger.info(f"Generated message {message_id} - response length: {len(ai_response_content)} chars")

        return {
            'id': message_id,
            'conversationId': request_body.conversationId,
            'roleName': request_body.roleName,
            'content': ai_response_content,
            'time': current_time,
            'version': 1,
            'lastModified': current_time
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating message: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


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
    Handles the patching of a message within a conversation.
    """
    crud_logger.info(
        f"Patch message called - User: {current_user['user_id']}, Message: {request_body.id}, Conversation: {request_body.conversationId}")

    try:
        if not request_body.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Message ID missing"
            )

        # Verify ownership
        if not verify_conversation_ownership(request_body.conversationId, current_user['user_id'],
                                              current_user.get("is_guest", False)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this conversation"
            )

        # First check current version
        current_version = db.get_message_version(request_body.id, request_body.conversationId)

        if current_version is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Message not found"
            )

        # Check for version conflict
        if current_version != request_body.version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Version conflict: current version is {current_version}, provided version is {request_body.version}"
            )

        # Update with version increment
        updated_message = db.update_message(
            message_id=request_body.id,
            conversation_id=request_body.conversationId,
            content=request_body.content,
            version=request_body.version,
            last_modified=int(time.time())
        )

        if not updated_message:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Version conflict during update"
            )

        # Parse content based on type
        message_type = updated_message.get('type') or 'text'
        content = updated_message['content']

        # Try to parse JSON content for complex types
        try:
            if message_type == 'text' and content.startswith('{'):
                content_obj = json.loads(content)
                if 'content' in content_obj:
                    content = content_obj['content']
        except (json.JSONDecodeError, KeyError, AttributeError):
            pass

        crud_logger.info(
            f"Message patched successfully - Message ID: {request_body.id}, New version: {updated_message['version']}")
        return MessageResponse(
            id=updated_message['id'],
            conversationId=updated_message['conversationId'],
            roleName=updated_message['roleName'],
            content=content,
            time=updated_message['time'],
            type=message_type,
            version=updated_message['version'],
            lastModified=updated_message['lastModified'],
            rating=updated_message.get('rating')
        )

    except HTTPException:
        raise
    except Exception as e:
        crud_logger.error(f"Error patching message: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update message: {str(e)}. Please refresh and try again."
        )


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
    Deletes a specific message within a conversation.
    """
    crud_logger.info(
        f"Delete message called - User: {current_user['user_id']}, Message: {message_id}, Conversation: {conversation_id}")

    try:
        if not conversation_id or not message_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Conversation ID or Message ID missing"
            )

        # Verify ownership
        if not verify_conversation_ownership(conversation_id, current_user['user_id'],
                                              current_user.get("is_guest", False)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this conversation"
            )

        deleted = db.delete_message(message_id, conversation_id)

        if not deleted:
            crud_logger.warning(f"Message not found for deletion - Message ID: {message_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Message not found"
            )

        crud_logger.info(f"Message deleted successfully - Message ID: {message_id}")
        return None

    except HTTPException:
        raise
    except Exception as e:
        crud_logger.error(f"Error deleting message: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete message: {str(e)}. Please check your connection and try again."
        )


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
    Rate a message within a conversation.
    """
    crud_logger.info(
        f"Rate message called - User: {current_user['user_id']}, Message: {request_body.id}, Rating: {request_body.rating}")

    try:
        # Validate rating value (None is allowed to remove rating)
        if request_body.rating is not None and request_body.rating not in [0, 1]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Rating must be 0 (thumbs down), 1 (thumbs up), or null to remove rating"
            )

        # Verify ownership
        if not verify_conversation_ownership(request_body.conversationId, current_user['user_id'],
                                              current_user.get("is_guest", False)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this conversation"
            )

        # Update the rating
        updated_message = db.update_message_rating(
            request_body.id,
            request_body.conversationId,
            request_body.rating
        )

        if not updated_message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Message not found"
            )

        # Parse content based on type
        message_type = updated_message.get('type') or 'text'
        content = updated_message['content']

        # Try to parse JSON content for complex types
        try:
            if message_type == 'text' and content.startswith('{'):
                content_obj = json.loads(content)
                if 'content' in content_obj:
                    content = content_obj['content']
        except (json.JSONDecodeError, KeyError, AttributeError):
            pass

        rating_text = "removed" if request_body.rating is None else str(request_body.rating)
        crud_logger.info(f"Message rated successfully - Message ID: {request_body.id}, Rating: {rating_text}")
        return MessageResponse(
            id=updated_message['id'],
            conversationId=updated_message['conversationId'],
            roleName=updated_message['roleName'],
            content=content,
            time=updated_message['time'],
            type=message_type,
            version=updated_message['version'],
            lastModified=updated_message['lastModified'],
            rating=updated_message.get('rating')
        )

    except HTTPException:
        raise
    except Exception as e:
        crud_logger.error(f"Error rating message: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rate message: {str(e)}"
        )


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
    Handles the regeneration of an AI message within a conversation.
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

        # Get the message to regenerate
        message = db.get_message_by_id(request_body.id, request_body.conversationId)

        if not message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Message not found"
            )

        # Verify it's an AI message
        if message['roleName'] == 'user':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can only regenerate AI messages"
            )

        # Get all messages before this one for context
        all_messages = db.get_messages_by_conversation(
            request_body.conversationId,
            before_timestamp=message['time'],
            limit=20
        )

        # Build conversation context
        context_messages = []
        for msg in reversed(all_messages):  # Reverse to get chronological order
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
        current_version = message['version'] or 1
        updated_message = db.update_message(
            message_id=request_body.id,
            conversation_id=request_body.conversationId,
            content=ai_response_content,
            version=current_version,
            last_modified=int(time.time())
        )

        if updated_message:
            crud_logger.info(f"Message regenerated successfully - Message ID: {request_body.id}")
            return MessageResponse(
                id=updated_message['id'],
                conversationId=updated_message['conversationId'],
                roleName=updated_message['roleName'],
                content=updated_message['content'],
                time=updated_message['time'],
                type=updated_message.get('type') or 'text',
                version=updated_message['version'],
                lastModified=updated_message['lastModified'],
                rating=updated_message.get('rating')
            )

        return None

    except HTTPException:
        raise
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
    generating AI responses.
    """
    try:
        if not verify_conversation_ownership(request_body.conversationId, current_user['user_id'],
                                              current_user.get("is_guest", False)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this conversation"
            )

        user_message_id = int(time.time() * 1000)
        content_str = ""
        message_type = request_body.type
        if message_type == 'text':
            # Check for top-level attachments (frontend sends them alongside content, not inside it)
            top_level_attachments = getattr(request_body, 'attachments', None)

            if isinstance(request_body.content, str):
                content_str = request_body.content
                # Check for top-level attachments when content is a plain string
                if top_level_attachments:
                    content_obj = {
                        'content': content_str,
                        'attachments': top_level_attachments
                    }
                    content_str = json.dumps(content_obj)
                    crud_logger.info(f"[send_and_generate] Stored message with {len(top_level_attachments)} attachment(s) from top-level")
            elif isinstance(request_body.content, dict):
                content_str = request_body.content.get('content', '')
                attachments = request_body.content.get('attachments', [])
                # Also check top-level attachments if none in content
                if not attachments and top_level_attachments:
                    attachments = top_level_attachments
                if attachments:
                    content_obj = {'content': content_str, 'attachments': attachments}
                    content_str = json.dumps(content_obj)
                    crud_logger.info(f"[send_and_generate] Stored message with {len(attachments)} attachment(s) from dict")
            elif hasattr(request_body.content, 'content'):
                # Handle TextContent model - include attachments if present
                content_str = request_body.content.content
                attachments = getattr(request_body.content, 'attachments', None)
                # Also check top-level attachments
                if not attachments and top_level_attachments:
                    attachments = top_level_attachments
                if attachments:
                    # Convert FileReference models to dicts for JSON storage
                    attachment_dicts = []
                    for att in attachments:
                        if hasattr(att, 'model_dump'):
                            attachment_dicts.append(att.model_dump())
                        elif isinstance(att, dict):
                            attachment_dicts.append(att)
                    if attachment_dicts:
                        content_obj = {
                            'content': content_str,
                            'attachments': attachment_dicts
                        }
                        content_str = json.dumps(content_obj)
                        crud_logger.info(f"[send_and_generate] Stored message with {len(attachment_dicts)} attachment(s) from TextContent model")
        elif message_type == 'voice':
            if isinstance(request_body.content, dict):
                content_str = json.dumps(request_body.content)
            elif hasattr(request_body.content, 'model_dump'):
                content_str = json.dumps(request_body.content.model_dump())
            else:
                content_str = str(request_body.content)
        elif message_type == 'agent':
            # Use JSONB storage for agent messages (same as streaming endpoint)
            _save_agent_message(
                message_id=user_message_id,
                conversation_id=request_body.conversationId,
                role_name=request_body.roleName,
                msg_time=request_body.time,
                content=request_body.content
            )
            # Extract agent fields for response
            if hasattr(request_body.content, 'model_dump'):
                agent_data = request_body.content.model_dump()
            elif isinstance(request_body.content, dict):
                agent_data = request_body.content
            else:
                agent_data = {'finalResponse': str(request_body.content), 'steps': [], 'status': 'complete'}

            user_message_response = MessageResponse(
                id=user_message_id,
                conversationId=request_body.conversationId,
                roleName=request_body.roleName,
                content='',  # Empty for JSONB-stored agent messages
                time=request_body.time,
                type='agent',
                version=request_body.version or 1,
                lastModified=request_body.lastModified or int(time.time()),
                steps=agent_data.get('steps', []),
                finalResponse=agent_data.get('finalResponse', ''),
                status=agent_data.get('status', 'complete'),
                error=agent_data.get('error')
            )
            # Agent messages don't need AI generation - return immediately
            return SendAndGenerateResponse(userMessage=user_message_response, aiMessage=None)

        # For text/voice messages, use regular message storage
        db.create_message(
            message_id=user_message_id,
            conversation_id=request_body.conversationId,
            role_name=request_body.roleName,
            content=content_str,
            time=request_body.time,
            msg_type=message_type,
            version=request_body.version or 1,
            last_modified=request_body.lastModified or int(time.time())
        )

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

            ai_response_content = await generate_llm_response(
                context,
                DEFAULT_TEMPERATURE,
                DEFAULT_TOP_P,
                DEFAULT_SYSTEM_PROMPT,
                DEFAULT_MODEL
            )

            ai_message_id = int(time.time() * 1000) + 1
            current_time = int(time.time())

            db.create_message(
                message_id=ai_message_id,
                conversation_id=request_body.conversationId,
                role_name=request_body.aiParticipant,
                content=ai_response_content,
                time=current_time,
                msg_type='text',
                version=1,
                last_modified=current_time
            )

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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in send_and_generate: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/stream-generate",
             responses={
                 status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Access denied"},
                 status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse,
                                                          "description": "Internal server error"}
             },
             dependencies=[Depends(rate_limit_guest)])
async def stream_generate(
    request_body: StreamGenerateRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Stream agent reasoning steps and final response using Server-Sent Events.

    This endpoint returns an SSE stream with the following event types:
    - step: An agent reasoning step (thought, tool_call, tool_result, observation)
    - token: A token from the final response stream
    - done: Signals completion with the final message ID
    - error: An error occurred during processing

    The agent uses LangGraph to orchestrate multi-step reasoning with Neo4j tools
    for waste disposal knowledge retrieval.
    """
    crud_logger.info(
        f"Stream generate called - User: {current_user['user_id']}, Conversation: {request_body.conversationId}")

    # Verify ownership before starting stream
    if not verify_conversation_ownership(request_body.conversationId, current_user['user_id'],
                                          current_user.get("is_guest", False)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this conversation"
        )

    async def event_generator() -> AsyncGenerator[dict, None]:
        """Generate SSE events for agent reasoning and response."""
        message_id = int(time.time() * 1000)
        current_time = int(time.time())
        steps = []  # Will store step dicts (not models)
        final_response = ""
        # Track pending tool calls by tool name (queue per tool for parallel calls)
        pending_tool_calls: dict[str, list[str]] = defaultdict(list)

        # Send message envelope FIRST - provides metadata before any content
        message_start = MessageStartEvent(
            messageId=message_id,
            conversationId=request_body.conversationId,
            roleName=request_body.aiParticipant,
            time=current_time,
            type="agent"
        )
        yield {
            "event": "message_start",
            "data": json.dumps(message_start.model_dump())
        }

        try:
            # Build conversation history with placeholders for previous attachments
            history_builder = ConversationHistoryBuilder(db)
            history_messages, available_attachments = await history_builder.build_history(
                request_body.conversationId,
                limit=20,
                include_latest_attachments=True
            )

            if not history_messages:
                yield {
                    "event": "error",
                    "data": json.dumps({"error": "No messages found in conversation"})
                }
                return

            # Get latest user message text (for logging/validation)
            user_message = ""
            if history_messages:
                latest = history_messages[-1]
                if hasattr(latest, 'content'):
                    user_message = latest.content if isinstance(latest.content, str) else str(latest.content)

            if not user_message:
                yield {
                    "event": "error",
                    "data": json.dumps({"error": "No user message found in conversation"})
                }
                return

            # Filter attachments by type from available_attachments (for latest message processing)
            image_attachments = [
                {"fileId": att.file_id, "mimeType": att.mime_type, "name": att.file_name}
                for att in available_attachments
                if att.attachment_type == AttachmentType.IMAGE
            ]
            document_attachments = [
                {"fileId": att.file_id, "mimeType": att.mime_type, "name": att.file_name}
                for att in available_attachments
                if att.attachment_type == AttachmentType.PDF
            ]
            audio_attachments = [
                {"fileId": att.file_id, "mimeType": att.mime_type, "name": att.file_name}
                for att in available_attachments
                if att.attachment_type == AttachmentType.AUDIO
            ]

            # Log if attachments are found
            if image_attachments:
                crud_logger.info(f"Found {len(image_attachments)} image attachment(s) in conversation")
            if document_attachments:
                crud_logger.info(f"Found {len(document_attachments)} document attachment(s) in conversation")
            if audio_attachments:
                crud_logger.info(f"Found {len(audio_attachments)} audio attachment(s) in conversation")
            if available_attachments:
                crud_logger.info(f"Total available attachments for file retrieval: {len(available_attachments)}")

            # Check if we have an LLM provider configured
            use_agent = is_provider_available("openai") or is_provider_available("anthropic")

            if use_agent:
                # Use the real LangGraph agent
                crud_logger.info(f"Using LangGraph agent for message: {user_message[:50] if len(user_message) > 50 else user_message}...")

                try:
                    agent = create_fessi_agent()

                    # Get conversation history without the latest message (it will be built with attachments)
                    conversation_history = history_messages[:-1] if len(history_messages) > 1 else None

                    # Stream reasoning steps and response using astream_full
                    async for event_type, event_data in agent.astream_full(
                        user_message,
                        images=image_attachments,
                        documents=document_attachments,
                        audio=audio_attachments,
                        conversation_history=conversation_history
                    ):
                        if event_type == "step":
                            step_dict = event_data.model_dump()

                            # Add callId linking for tool calls and results
                            step_type = step_dict.get('type')
                            tool_title = step_dict.get('title', '')

                            if step_type == 'tool_call':
                                call_id = str(uuid.uuid4())
                                pending_tool_calls[tool_title].append(call_id)
                                step_dict['callId'] = call_id
                            elif step_type == 'tool_result':
                                # Extract original tool title from "Ergebnis: <tool_title>"
                                original_title = tool_title.replace('Ergebnis: ', '', 1)
                                if pending_tool_calls[original_title]:
                                    step_dict['callId'] = pending_tool_calls[original_title].pop(0)

                            steps.append(step_dict)
                            yield {
                                "event": "step",
                                "data": json.dumps(step_dict)
                            }
                        elif event_type == "token":
                            final_response += event_data
                            yield {
                                "event": "token",
                                "data": event_data
                            }

                except Exception as agent_error:
                    crud_logger.error(f"Agent error, falling back to basic LLM: {agent_error}", exc_info=True)
                    # Fall back to basic LLM if agent fails
                    final_response = await _fallback_generate(request_body.conversationId, steps)
                    # Stream fallback response
                    for i in range(0, len(final_response), 4):
                        token = final_response[i:i + 4]
                        yield {
                            "event": "token",
                            "data": token
                        }
                        await asyncio.sleep(0.01)

            else:
                # Fallback: Use the basic LLM (Replicate) when no LangChain provider is available
                crud_logger.info("No LangChain LLM provider available, using fallback Replicate LLM")

                # Emit a thinking step (as dict for consistency)
                thinking_step = {
                    "id": str(uuid.uuid4()),
                    "type": "thought",
                    "title": "Processing Request",
                    "content": "Analyzing message and preparing response...",
                    "timestamp": int(time.time() * 1000)
                }
                steps.append(thinking_step)
                yield {
                    "event": "step",
                    "data": json.dumps(thinking_step)
                }

                # Generate using fallback
                final_response = await _fallback_generate(request_body.conversationId, steps)

                # Emit observation step (as dict for consistency)
                observation_step = {
                    "id": str(uuid.uuid4()),
                    "type": "observation",
                    "title": "Response Generated",
                    "content": "Response has been successfully generated.",
                    "timestamp": int(time.time() * 1000)
                }
                steps.append(observation_step)
                yield {
                    "event": "step",
                    "data": json.dumps(observation_step)
                }

                # Stream the response tokens
                chunk_size = 4
                for i in range(0, len(final_response), chunk_size):
                    token = final_response[i:i + chunk_size]
                    yield {
                        "event": "token",
                        "data": token
                    }
                    await asyncio.sleep(0.01)

            # Save using JSONB storage (new schema)
            db.create_agent_message(
                message_id=message_id,
                conversation_id=request_body.conversationId,
                role_name=request_body.aiParticipant,
                time=current_time,
                final_response=final_response,
                status='complete',
                steps=steps  # Stored as JSONB array
            )

            # Signal completion
            yield {
                "event": "done",
                "data": json.dumps({
                    "messageId": message_id,
                    "conversationId": request_body.conversationId
                })
            }

            crud_logger.info(f"Stream generate completed - Message ID: {message_id}")

        except Exception as e:
            crud_logger.error(f"Error in stream generate: {str(e)}", exc_info=True)

            # Save error state using JSONB storage
            db.create_agent_message(
                message_id=message_id,
                conversation_id=request_body.conversationId,
                role_name=request_body.aiParticipant,
                time=current_time,
                final_response=final_response,
                status='error',
                error=str(e),
                steps=steps
            )

            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)})
            }

    return EventSourceResponse(event_generator())


@router.post("/tts/{conversation_id}/{message_id}",
             responses={
                 status.HTTP_200_OK: {"content": {"audio/mpeg": {}}, "description": "TTS audio file"},
                 status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "Message has no text content"},
                 status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Access denied"},
                 status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Message not found"},
                 status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "TTS generation failed"}
             })
async def generate_tts(
    conversation_id: str,
    message_id: int,
    language: str = "en",
    current_user: dict = Depends(get_current_user)
):
    """
    Generate text-to-speech audio for a message.

    Returns cached audio if available, otherwise generates new audio.
    The audio is saved for future requests.

    Args:
        conversation_id: The conversation UUID.
        message_id: The message ID.
        language: Language code for voice selection ('en' or 'de').

    Returns:
        MP3 audio file.
    """
    crud_logger.info(
        f"TTS requested - User: {current_user['user_id']}, Message: {message_id}, Language: {language}"
    )

    try:
        # Verify ownership
        if not verify_conversation_ownership(conversation_id, current_user['user_id'],
                                              current_user.get("is_guest", False)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this conversation"
            )

        # Check for cached audio first
        cached_audio = get_cached_tts_audio(message_id, conversation_id)
        if cached_audio:
            crud_logger.info(f"Returning cached TTS audio for message {message_id}")
            return Response(
                content=cached_audio,
                media_type="audio/mpeg",
                headers={"X-TTS-Cached": "true"}
            )

        # Get message content from database
        db_message = db.get_message_by_id(message_id, conversation_id)
        if not db_message:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

        # Extract text content based on message type
        text_content = ""
        content_type = db_message.get('type', 'text')

        if content_type == 'agent':
            # For agent messages, use final_response from JSONB columns
            text_content = db_message.get('final_response', '') or ''
        else:
            # For text messages, parse content (may be JSON with attachments)
            raw_content = db_message.get('content', '')
            try:
                if raw_content.startswith('{'):
                    content_obj = json.loads(raw_content)
                    text_content = content_obj.get('content', raw_content)
                else:
                    text_content = raw_content
            except (json.JSONDecodeError, AttributeError):
                text_content = raw_content

        if not text_content or not text_content.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Message has no text content"
            )

        # Generate TTS audio and save to cache
        audio_path = get_tts_audio_path(message_id, conversation_id)
        audio_bytes = await generate_speech(text_content, language, audio_path)

        if not audio_bytes:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="TTS generation failed"
            )

        crud_logger.info(f"Generated TTS audio for message {message_id}: {len(audio_bytes)} bytes")
        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={"X-TTS-Cached": "false"}
        )

    except HTTPException:
        raise
    except Exception as e:
        crud_logger.error(f"Error generating TTS: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"TTS generation failed: {str(e)}"
        )


async def _get_last_user_message(conversation_id: str) -> tuple[str, list[dict], list[dict], list[dict]]:
    """
    Get the last user message from a conversation, including any attachments.

    Args:
        conversation_id: The conversation ID.

    Returns:
        Tuple of (text_content, image_attachments, document_attachments, audio_attachments).
    """
    messages = db.get_messages_by_conversation(conversation_id, limit=10)

    crud_logger.debug(f"Retrieved {len(messages)} messages for conversation {conversation_id}")

    # Find the last user message (messages are returned in reverse order)
    for msg in messages:
        if msg.get('roleName') == 'user':
            content = msg.get('content', '')
            images = []
            documents = []
            audio = []

            crud_logger.info(f"Found user message - content starts with: {content[:100] if content else '(empty)'}...")
            crud_logger.info(f"Content is JSON: {content.startswith('{') if content else False}")

            # Handle JSON-encoded content (contains attachments)
            if content.startswith('{'):
                try:
                    content_obj = json.loads(content)
                    text_content = content_obj.get('content', content)
                    crud_logger.info(f"Parsed JSON content - has attachments key: {'attachments' in content_obj}")
                    if 'attachments' in content_obj:
                        crud_logger.info(f"Attachments count: {len(content_obj.get('attachments', []))}")
                        crud_logger.info(f"Attachments: {content_obj.get('attachments', [])}")
                    images = extract_image_attachments(content_obj)
                    documents = extract_document_attachments(content_obj)
                    audio = extract_audio_attachments(content_obj)
                    crud_logger.info(f"Extracted: {len(images)} images, {len(documents)} documents, {len(audio)} audio files")
                    return (text_content, images, documents, audio)
                except json.JSONDecodeError as e:
                    crud_logger.error(f"Failed to parse JSON content: {e}")
                    pass

            return (content, images, documents, audio)

    crud_logger.warning(f"No user message found in conversation {conversation_id}")
    return ("", [], [], [])


async def _fallback_generate(conversation_id: str, steps: list) -> str:
    """
    Fallback generation using the basic Replicate LLM.

    Args:
        conversation_id: The conversation ID.
        steps: List to append any additional steps to.

    Returns:
        The generated response text.
    """
    context = await get_conversation_context(conversation_id, limit=6)
    return await generate_llm_response(
        context,
        DEFAULT_TEMPERATURE,
        DEFAULT_TOP_P,
        DEFAULT_SYSTEM_PROMPT,
        DEFAULT_MODEL
    )
