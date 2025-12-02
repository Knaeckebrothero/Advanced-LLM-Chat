"""
Message API endpoints.
"""
import json
import time
import asyncio
import uuid
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
    AgentStep
)
from backend.database import db
from backend.security.auth import get_current_user, verify_conversation_ownership, rate_limit_guest
from backend.security.logging import crud_logger
from backend.services.llm import get_conversation_context, generate_llm_response
from backend.config import DEFAULT_MODEL, DEFAULT_TEMPERATURE, DEFAULT_TOP_P, DEFAULT_SYSTEM_PROMPT
from backend.services.agent import create_fessi_agent
from backend.services.llm_provider import is_provider_available

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
    Handles the sending of a message in a conversation.
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
        message_type = getattr(request_body, 'type', 'text')

        if message_type == 'text':
            if isinstance(request_body.content, str):
                content_str = request_body.content
            elif isinstance(request_body.content, dict):
                content_str = request_body.content.get('content', '')
                attachments = request_body.content.get('attachments', [])
                if attachments:
                    content_obj = {
                        'content': content_str,
                        'attachments': attachments
                    }
                    content_str = json.dumps(content_obj)
            elif hasattr(request_body.content, 'content'):
                # Handle TextContent model
                content_str = request_body.content.content
        elif message_type == 'voice':
            if isinstance(request_body.content, dict):
                content_str = json.dumps(request_body.content)
            elif hasattr(request_body.content, 'model_dump'):
                content_str = json.dumps(request_body.content.model_dump())
            else:
                content_str = str(request_body.content)
        elif message_type == 'agent':
            # Handle agent messages - serialize the full AgentContent
            if hasattr(request_body.content, 'model_dump'):
                content_str = json.dumps(request_body.content.model_dump())
            elif isinstance(request_body.content, dict):
                content_str = json.dumps(request_body.content)
            else:
                content_str = str(request_body.content)

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
    Generates a message for a conversation based on the provided context.
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

        return {
            'id': message_id,
            'conversationId': request_body.conversationId,
            'roleName': request_body.roleName,
            'content': ai_response_content,
            'time': current_time,
            'version': 1,
            'lastModified': current_time
        }

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
    Handles the patching of a message within a conversation.
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

        # First check current version
        current_version = db.get_message_version(request_body.id, request_body.conversationId)

        if current_version is None:
            response.status_code = status.HTTP_404_NOT_FOUND
            return Response(status_code=status.HTTP_404_NOT_FOUND, content="Message not found")

        # Check for version conflict
        if current_version != request_body.version:
            response.status_code = status.HTTP_409_CONFLICT
            return ErrorResponse(
                error=f"Version conflict: current version is {current_version}, provided version is {request_body.version}")

        # Update with version increment
        updated_message = db.update_message(
            message_id=request_body.id,
            conversation_id=request_body.conversationId,
            content=request_body.content,
            version=request_body.version,
            last_modified=int(time.time())
        )

        if not updated_message:
            response.status_code = status.HTTP_409_CONFLICT
            return ErrorResponse(error="Version conflict during update")

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
    Deletes a specific message within a conversation.
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

        deleted = db.delete_message(message_id, conversation_id)

        if not deleted:
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
    Rate a message within a conversation.
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

        # Update the rating
        updated_message = db.update_message_rating(
            request_body.id,
            request_body.conversationId,
            request_body.rating
        )

        if not updated_message:
            response.status_code = status.HTTP_404_NOT_FOUND
            return ErrorResponse(error="Message not found")

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
            elif hasattr(request_body.content, 'content'):
                content_str = request_body.content.content
        elif message_type == 'voice':
            if isinstance(request_body.content, dict):
                content_str = json.dumps(request_body.content)
            elif hasattr(request_body.content, 'model_dump'):
                content_str = json.dumps(request_body.content.model_dump())
            else:
                content_str = str(request_body.content)
        elif message_type == 'agent':
            if hasattr(request_body.content, 'model_dump'):
                content_str = json.dumps(request_body.content.model_dump())
            elif isinstance(request_body.content, dict):
                content_str = json.dumps(request_body.content)
            else:
                content_str = str(request_body.content)

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

    except Exception as e:
        print(f"Error in send_and_generate: {str(e)}")
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return ErrorResponse(error=str(e))


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
        steps = []
        final_response = ""

        try:
            # Get the last user message from the conversation
            user_message = await _get_last_user_message(request_body.conversationId)

            if not user_message:
                yield {
                    "event": "error",
                    "data": json.dumps({"error": "No user message found in conversation"})
                }
                return

            # Check if we have an LLM provider configured
            use_agent = is_provider_available("openai") or is_provider_available("anthropic")

            if use_agent:
                # Use the real LangGraph agent
                crud_logger.info(f"Using LangGraph agent for message: {user_message[:50]}...")

                try:
                    agent = create_fessi_agent()

                    # Stream reasoning steps and response using astream_full
                    async for event_type, event_data in agent.astream_full(user_message):
                        if event_type == "step":
                            steps.append(event_data)
                            yield {
                                "event": "step",
                                "data": json.dumps(event_data.model_dump())
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

                # Emit a thinking step
                thinking_step = AgentStep(
                    id=str(uuid.uuid4()),
                    type="thought",
                    title="Verarbeite Anfrage",
                    content="Analysiere die Nachricht und bereite eine Antwort vor...",
                    timestamp=int(time.time() * 1000)
                )
                steps.append(thinking_step)
                yield {
                    "event": "step",
                    "data": json.dumps(thinking_step.model_dump())
                }

                # Generate using fallback
                final_response = await _fallback_generate(request_body.conversationId, steps)

                # Emit observation step
                observation_step = AgentStep(
                    id=str(uuid.uuid4()),
                    type="observation",
                    title="Antwort generiert",
                    content="Die Antwort wurde erfolgreich generiert.",
                    timestamp=int(time.time() * 1000)
                )
                steps.append(observation_step)
                yield {
                    "event": "step",
                    "data": json.dumps(observation_step.model_dump())
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

            # Save the complete message to the database
            current_time = int(time.time())

            # Serialize agent content for storage
            agent_content = {
                "type": "agent",
                "steps": [s.model_dump() for s in steps],
                "finalResponse": final_response,
                "status": "complete"
            }

            db.create_message(
                message_id=message_id,
                conversation_id=request_body.conversationId,
                role_name=request_body.aiParticipant,
                content=json.dumps(agent_content),
                time=current_time,
                msg_type='agent',
                version=1,
                last_modified=current_time
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
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)})
            }

    return EventSourceResponse(event_generator())


async def _get_last_user_message(conversation_id: str) -> str:
    """
    Get the last user message from a conversation.

    Args:
        conversation_id: The conversation ID.

    Returns:
        The content of the last user message, or empty string if not found.
    """
    messages = db.get_messages_by_conversation(conversation_id, limit=10)

    # Find the last user message (messages are returned in reverse order)
    for msg in messages:
        if msg.get('roleName') == 'user':
            content = msg.get('content', '')
            # Handle JSON-encoded content
            if content.startswith('{'):
                try:
                    content_obj = json.loads(content)
                    return content_obj.get('content', content)
                except json.JSONDecodeError:
                    pass
            return content

    return ""


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
