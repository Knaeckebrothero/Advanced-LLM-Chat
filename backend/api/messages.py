"""
Message API endpoints.
"""
import json
import logging
import time
from typing import Dict, AsyncGenerator, Optional
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
    MessageStartEvent
)
from backend.database import db
from backend.security.auth import get_current_user, verify_conversation_ownership, rate_limit_guest
from backend.security.logging import crud_logger
from backend.llm import ModelConfig, Usage, build_system_prompt, default_tools, run_agent
from backend.catalog.resolver import (
    ModelNotAllowed,
    ModelNotAvailable,
    persona_prompt_for_conversation,
    resolve_auxiliary_model,
    resolve_model,
)
from backend.services.llm import generate_reply
from backend.services.conversation_history import ConversationHistoryBuilder, history_token_budget
from backend.models.attachments import AttachmentType
from backend.services.tts_handler import (
    generate_speech,
    get_tts_audio_path,
    get_cached_tts_audio,
    get_cached_preprocessed_text,
    cache_preprocessed_text,
)
from backend.services.tts_preprocessor import preprocess_for_tts

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/message", tags=["Message"])

NO_MODEL_MESSAGE = (
    "No language model is configured. Set OPENAI_API_KEY or ANTHROPIC_API_KEY, "
    "or add a model to the model catalog."
)


class NoModelAvailableError(Exception):
    """No model can answer this request."""


def _resolve_model(current_user: dict, conversation_id: str, model_id: Optional[int] = None) -> ModelConfig:
    """
    The model that answers in this conversation.

    An explicitly requested model wins, then the conversation's model, the user's
    default model, the first catalog model and finally the environment model
    (see backend.catalog.resolver.resolve_model).

    :raises NoModelAvailableError: If no model is configured.
    :raises HTTPException: 403 if the requested model is not available to the user.
    """
    conversation = db.get_conversation_by_id(conversation_id)
    try:
        return resolve_model(current_user, model_id, conversation)
    except ModelNotAllowed as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ModelNotAvailable as e:
        raise NoModelAvailableError(str(e) or NO_MODEL_MESSAGE)


def _system_prompt(current_user: dict, conversation_id: str, tools=None) -> str:
    """The system prompt for a conversation: its persona (if any) plus the tool instructions."""
    conversation = db.get_conversation_by_id(conversation_id)
    return build_system_prompt(persona_prompt_for_conversation(current_user, conversation), tools)


def _resolve_model_or_503(current_user: dict, conversation_id: str) -> ModelConfig:
    """_resolve_model for the non-streaming endpoints: no model is a 503."""
    try:
        return _resolve_model(current_user, conversation_id)
    except NoModelAvailableError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))


def _step_to_dict(step) -> dict:
    """An agent step as stored and streamed; callId only on tool steps."""
    step_dict = step.model_dump()
    if step_dict.get('callId') is None:
        step_dict.pop('callId', None)
    return step_dict


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
        content=final_response,  # Response text (unified with text messages)
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
                                                          "description": "Internal server error"},
                 status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse,
                                                        "description": "No language model configured"}
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

        # Generate AI response from the conversation history
        config = _resolve_model_or_503(current_user, request_body.conversationId)
        logger.debug(f"Generating reply for {request_body.conversationId} with {config.model_id}")
        ai_response_content, usage = await generate_reply(
            config,
            request_body.conversationId,
            system_prompt=request_body.systemPrompt or _system_prompt(current_user, request_body.conversationId)
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
                                                          "description": "Internal server error"},
                 status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse,
                                                        "description": "No language model configured"}
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

        # Generate a new AI response from the messages before this one
        config = _resolve_model_or_503(current_user, request_body.conversationId)
        try:
            ai_response_content, usage = await generate_reply(
                config,
                request_body.conversationId,
                system_prompt=_system_prompt(current_user, request_body.conversationId),
                before_message=message
            )
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

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
                                                          "description": "Internal server error"},
                 status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse,
                                                        "description": "No language model configured"}
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
            config = _resolve_model_or_503(current_user, request_body.conversationId)
            ai_response_content, usage = await generate_reply(
                config,
                request_body.conversationId,
                system_prompt=_system_prompt(current_user, request_body.conversationId)
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
    - message_start: Message metadata, including the model that answers (modelId, modelName)
    - step: An agent reasoning step (thought, tool_call, tool_result, observation);
      a step with the id of an earlier one replaces it
    - step_delta: Text appended to an earlier step ({"id", "delta"}), the model's live reasoning
    - token: A token from the final response stream
    - done: Signals completion with the message ID, the model and the token usage
    - error: An error occurred during processing

    The agent loop (backend/llm) runs the model with its tools (file retrieval,
    web search and the optional Neo4j knowledge graph).
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

    # Resolve the model before the stream starts, so a model the user may not use is a 403
    try:
        config = _resolve_model(current_user, request_body.conversationId, request_body.modelId)
    except NoModelAvailableError as e:
        config = None
        crud_logger.error(f"Stream generate without a model: {e}")

    async def event_generator() -> AsyncGenerator[dict, None]:
        """Generate SSE events for agent reasoning and response."""
        message_id = int(time.time() * 1000)
        current_time = int(time.time())
        steps = []  # Step dicts in order of first appearance (not models)
        step_positions: dict[str, int] = {}  # Step id -> index in steps, for replaced steps
        final_response = ""
        usage: Optional[Usage] = None

        # Send message envelope FIRST - provides metadata before any content
        message_start = MessageStartEvent(
            messageId=message_id,
            conversationId=request_body.conversationId,
            roleName=request_body.aiParticipant,
            time=current_time,
            type="agent",
            modelId=config.id if config else None,
            modelName=config.display_name if config else None
        )
        yield {
            "event": "message_start",
            "data": json.dumps(message_start.model_dump())
        }

        if config is None:
            yield {
                "event": "error",
                "data": json.dumps({"error": NO_MODEL_MESSAGE})
            }
            return

        try:
            tools = default_tools() if config.supports_tools else None
            system_prompt = _system_prompt(current_user, request_body.conversationId, tools)

            # Build conversation history with placeholders for previous attachments,
            # as much of it as fits the model's context window
            history_builder = ConversationHistoryBuilder(db)
            history_messages, available_attachments = await history_builder.build_history(
                request_body.conversationId,
                include_latest_attachments=True,
                supports_vision=config.supports_vision,
                token_budget=history_token_budget(config, system_prompt, tools)
            )

            if not history_messages:
                yield {
                    "event": "error",
                    "data": json.dumps({"error": "No messages found in conversation"})
                }
                return

            if not any(message.get('role') == 'user' for message in history_messages):
                yield {
                    "event": "error",
                    "data": json.dumps({"error": "No user message found in conversation"})
                }
                return

            # Log the attachments of the conversation (full content for the latest message only)
            if available_attachments:
                counts = {
                    attachment_type.value: sum(1 for att in available_attachments if att.attachment_type == attachment_type)
                    for attachment_type in AttachmentType
                }
                crud_logger.info(f"Attachments in conversation: {counts}")

            crud_logger.info(
                f"Running agent with {config.display_name} ({config.provider_name}) on "
                f"{len(history_messages)} messages")

            async for event_type, event_data in run_agent(
                config,
                history_messages,
                system_prompt=system_prompt,
                tools=tools
            ):
                if event_type == "step":
                    step_dict = _step_to_dict(event_data)
                    position = step_positions.get(step_dict['id'])
                    if position is None:
                        step_positions[step_dict['id']] = len(steps)
                        steps.append(step_dict)
                    else:
                        steps[position] = step_dict
                    yield {
                        "event": "step",
                        "data": json.dumps(step_dict)
                    }
                elif event_type == "step_delta":
                    # Keep the stored step current, in case the stream breaks before the step completes
                    position = step_positions.get(event_data['id'])
                    if position is not None:
                        steps[position]['content'] += event_data['delta']
                    yield {
                        "event": "step_delta",
                        "data": json.dumps(event_data)
                    }
                elif event_type == "token":
                    final_response += event_data
                    yield {
                        "event": "token",
                        "data": event_data
                    }
                elif event_type == "usage":
                    usage = event_data

            # Save using JSONB storage, with the model that answered and its usage
            usage_data = (usage or Usage()).to_api(config)
            db.create_agent_message(
                message_id=message_id,
                conversation_id=request_body.conversationId,
                role_name=request_body.aiParticipant,
                time=current_time,
                content=final_response,  # Response text (unified with text messages)
                status='complete',
                steps=steps,  # Stored as JSONB array
                model_id=config.id,
                model_name=config.display_name,
                usage=usage_data
            )

            # Signal completion
            yield {
                "event": "done",
                "data": json.dumps({
                    "messageId": message_id,
                    "conversationId": request_body.conversationId,
                    "modelId": config.id,
                    "modelName": config.display_name,
                    "usage": usage_data
                })
            }

            crud_logger.info(
                f"Stream generate completed - Message ID: {message_id}, "
                f"tokens in/out: {usage.input_tokens if usage else 0}/{usage.output_tokens if usage else 0}")

        except Exception as e:
            crud_logger.error(f"Error in stream generate: {str(e)}", exc_info=True)

            # Save error state using JSONB storage, with the usage until the error
            db.create_agent_message(
                message_id=message_id,
                conversation_id=request_body.conversationId,
                role_name=request_body.aiParticipant,
                time=current_time,
                content=final_response,  # Response text (unified with text messages)
                status='error',
                error=str(e),
                steps=steps,
                model_id=config.id,
                model_name=config.display_name,
                usage=usage.to_api(config) if usage else None
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

        # Extract text content from unified 'content' column
        # Both text and agent messages now store response in 'content'
        text_content = ""
        raw_content = db_message.get('content', '')

        # Text messages may have JSON with attachments, need to parse
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

        # Preprocess text for TTS (converts markdown, tables, code to speakable prose)
        final_text = text_content

        # Check for cached preprocessed text first
        preprocessed = get_cached_preprocessed_text(message_id, conversation_id)
        if preprocessed:
            crud_logger.info(f"Using cached preprocessed text for message {message_id}")
            final_text = preprocessed
        else:
            # Try to generate preprocessed text
            preprocessed = await preprocess_for_tts(text_content, config=resolve_auxiliary_model())
            if preprocessed:
                final_text = preprocessed
                cache_preprocessed_text(message_id, conversation_id, preprocessed)
                crud_logger.info(f"Generated and cached preprocessed text for message {message_id}")
            else:
                crud_logger.debug(f"Using original text for message {message_id} (preprocessing skipped or failed)")

        # Generate TTS audio and save to cache
        audio_path = get_tts_audio_path(message_id, conversation_id)
        audio_bytes = await generate_speech(final_text, language, audio_path)

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
