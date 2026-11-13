"""
Message API endpoints.
"""
import json
import logging
import time
from dataclasses import dataclass
from typing import Dict, AsyncGenerator, Iterable, List, Optional, Tuple
from fastapi import APIRouter, Request, Response, Depends, HTTPException, status
from sse_starlette.sse import EventSourceResponse
from backend.models.common import ErrorResponse
from backend.models.message import (
    ApiMessageSend,
    ApiMessageGenerate,
    ApiMessageSendAndGenerate,
    MessageInsert,
    MessagePatch,
    MessageResponse,
    SendAndGenerateResponse,
    RateMessageRequest,
    RegenerateMessageRequest,
    StreamGenerateRequest,
    SummarizeRequest,
    ContextSizeRequest,
    ContextSize,
    SystemPrompt,
    SystemPromptUpdate,
    MessageStartEvent,
    ConversationSummary,
    AgentStep
)
from backend.database import db
from backend.security.auth import get_current_user, verify_conversation_ownership
from backend.security.errors import answer_error
from backend.security.guest_limits import count_guest_request, guest_write, rate_limit_guest
from backend.security.logging import crud_logger
from backend.llm import (
    ModelConfig, ToolRegistry, Usage, build_system_prompt, run_agent, skill_tools, tools_for_groups,
    with_instructions, with_mcp_servers, with_memory, with_skills
)
from backend.llm.prompts import hide_section, without_hide_section
from backend.llm.tools import MEMORY_TOOL_NAMES
from backend.catalog.resolver import (
    ModelNotAllowed,
    ModelNotAvailable,
    conversation_hidden,
    persona_prompt_for_conversation,
    persona_skills,
    persona_tool_groups,
    persona_vault,
    resolve_auxiliary_model,
    resolve_model,
)
from backend.services import knowledge_base as kb
from backend.services import memory_snapshot
from backend.services.hidden_content import auto_hide_definition, family_mode, restore_hidden, visible
from backend.services.mcp.tools import McpToolset, Notice, notice_step, tools_for_answer as mcp_tools_for_answer
from backend.services.llm import generate_reply
from backend.llm.tool_record import with_text as record_with_text
from backend.services.conversation_history import (
    CONTINUE_NOTE, ConversationHistoryBuilder, HistoryEntry, continue_message, entry_tokens, estimate_tokens,
    history_token_budget, needs_continue_note, summary_message
)
from backend.config import DEFAULT_CONTEXT_WINDOW
from backend.services.conversation_summary import SummaryFailed, messages_to_summarize, summarize
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

# Id prefix of the step that shows a summary of the oldest messages being written (the frontend knows it)
SUMMARY_STEP_PREFIX = "summary-"

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


def _own_system_prompt(conversation: Optional[dict], hide: bool = False) -> Optional[str]:
    """
    The conversation's own system prompt, set in manual editing: it is sent as it is, in place
    of the one built from the conversation's agent. None without one ('' sends none). With
    hide (a device in family mode) without its hidden lines, like the memory.
    """
    own = (conversation or {}).get('system_prompt')
    if own is None:
        return None
    return (visible(own) or "") if hide else own


def _system_prompt(current_user: dict, conversation_id: str, tools=None) -> str:
    """
    The system prompt for a conversation: its own if it has one, else its persona (if any) plus
    the tool instructions.
    """
    conversation = db.get_conversation_by_id(conversation_id)
    own = _own_system_prompt(conversation)
    if own is not None:
        return own
    return build_system_prompt(persona_prompt_for_conversation(current_user, conversation), tools)


def _agent_tools(current_user: dict, conversation: Optional[dict], config: ModelConfig,
                 hide: bool = False, hide_definition: str = "", skills: Iterable[dict] = ()) -> Optional[ToolRegistry]:
    """
    The tools for an answer: the tools the server enables, limited to the tool
    groups of the conversation's persona (if it has a selection; the knowledge
    base only comes with a selection). The file tools only see the current
    user's files of this conversation (a vision model gets images themselves),
    the knowledge base tools only their notes (never a guest's): the shared
    knowledge base, or the persona's own one (persona_vault()). With hide, the device
    is in family mode, which the knowledge base and past chat tools then leave out;
    hide_definition is what the agent hides on its own (none without it). With the
    persona's skills (persona_skills()), use_skill loads them (docs/skills.md).

    :return: The tools, or None for none (the model doesn't support tools, or
        the persona selected no enabled tool group).
    """
    if not config.supports_tools:
        return None
    tools = tools_for_groups(persona_tool_groups(current_user, conversation), user_id=current_user['user_id'],
                             guest=bool(current_user.get('is_guest')), conversation=conversation,
                             vault=persona_vault(current_user, conversation), vision=config.supports_vision,
                             family_mode=hide, hide_definition=hide_definition)
    for tool in skill_tools(list(skills)):
        tools.add(tool)
    return tools if len(tools) else None


def _memory_prompt(system_prompt: str, current_user: dict, conversation: Optional[dict],
                   tools: Optional[ToolRegistry], hide: bool = False) -> Tuple[str, Optional[str]]:
    """
    The system prompt with the agent's memory, if it has the memory tools (the knowledge base),
    and the note on what changed in the memory since: the prompt shows the conversation's
    snapshot of it (memory_snapshot.prompt_memory()), which stays the same while the conversation
    goes on, so the provider's prompt cache keeps working. With hide without its hidden lines.

    Returns:
        (the system prompt, the note for the newest user message or None)
    """
    if tools is None or not set(tools.names()) & set(MEMORY_TOOL_NAMES):
        return system_prompt, None
    vault = persona_vault(current_user, conversation)
    memory = kb.get_memory(current_user['user_id'], vault, family_mode=hide)
    content = memory['content'] if memory else None
    if not (conversation or {}).get('id'):
        return with_memory(system_prompt, content), None  # No conversation to keep a snapshot for
    shown = memory_snapshot.prompt_memory(conversation['id'], content, vault, hide)
    return with_memory(system_prompt, shown.content, today=shown.day), shown.note


def _resolve_model_or_503(current_user: dict, conversation_id: str, model_id: Optional[int] = None) -> ModelConfig:
    """_resolve_model for the non-streaming endpoints: no model is a 503."""
    try:
        return _resolve_model(current_user, conversation_id, model_id)
    except NoModelAvailableError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))


def _step_to_dict(step) -> dict:
    """An agent step as stored and streamed; callId only on tool steps."""
    step_dict = step.model_dump()
    if step_dict.get('callId') is None:
        step_dict.pop('callId', None)
    return step_dict


async def _mcp_tools(current_user: dict, conversation: Optional[dict], config: ModelConfig,
                     tools: Optional[ToolRegistry], answer_id: Optional[int] = None
                     ) -> Tuple[Optional[ToolRegistry], McpToolset]:
    """
    The tools of the agent's MCP servers added to an answer's tools (docs/mcp.md). A failure
    here never fails the answer: it goes on without MCP tools. The files their results bring
    (e.g. generated images) are recorded with answer_id, the id of the message being written.
    """
    if not config.supports_tools:
        return tools, McpToolset()
    registry = tools if tools is not None else ToolRegistry()
    try:
        toolset = await mcp_tools_for_answer(current_user, conversation, set(registry.names()), answer_id)
    except Exception as e:
        crud_logger.error(f"MCP tools of conversation {(conversation or {}).get('id')} failed: {e}", exc_info=True)
        return tools, McpToolset()
    for tool in toolset.tools:
        registry.add(tool)
    return (registry if len(registry) else None), toolset


@dataclass
class AnswerParts:
    """What an answer in a conversation is built from, its system prompt still in its two parts."""
    tools: Optional[ToolRegistry]
    history_builder: ConversationHistoryBuilder
    base_prompt: str            # The system prompt without the conversation's system messages
    own_prompt: bool            # base_prompt is the conversation's own, not built from its agent
    instructions: List[str]     # The conversation's system messages, which follow it
    notices: List[Notice]       # The MCP servers that gave no tools
    memory_note: Optional[str] = None  # What changed in the memory since the prompt's snapshot (memory_snapshot)

    @property
    def system_prompt(self) -> str:
        return with_instructions(self.base_prompt, self.instructions)


async def _answer_context(
    current_user: dict,
    conversation_id: str,
    config: ModelConfig,
    *,
    mcp: bool = True,
    answer_id: Optional[int] = None,
    hide: bool = False
) -> Tuple[Optional[ToolRegistry], ConversationHistoryBuilder, str, int, List[Notice], Optional[str]]:
    """
    What an answer in this conversation is built from (_answer_parts()): the tools, the
    history builder, the system prompt, the token budget of the history, the MCP servers
    that gave no tools (to show as steps), and the note on what changed in the memory since
    the prompt's snapshot of it (for the newest user message, memory_snapshot.with_note()).
    """
    parts = await _answer_parts(current_user, conversation_id, config, mcp=mcp, answer_id=answer_id, hide=hide)
    system_prompt = parts.system_prompt
    return (parts.tools, parts.history_builder, system_prompt,
            history_token_budget(config, system_prompt, parts.tools), parts.notices, parts.memory_note)


async def _answer_parts(
    current_user: dict,
    conversation_id: str,
    config: ModelConfig,
    *,
    mcp: bool = True,
    answer_id: Optional[int] = None,
    hide: bool = False
) -> AnswerParts:
    """
    What an answer in this conversation is built from: the tools, the history builder and
    the system prompt.

    The persona decides the prompt and which tools the model gets; the prompt only
    describes the tools it really has. Its skills are listed next (docs/skills.md), for a
    model with tools. The tools of the agent's MCP servers come next
    (not with mcp=False, which doesn't connect to them); answer_id is the id of the message
    being written, recorded with the files those tools create. With the knowledge base, the
    agent's memory follows: the conversation's snapshot of it (backend/services/memory_snapshot.py),
    the same for every answer while the conversation goes on, and what changed since as a note
    for the newest user message (memory_note).
    The conversation's system messages are instructions to the model and come last. With hide,
    the device is in family mode: the memory and the tools leave it out.

    A conversation with its own system prompt (manual editing, _own_system_prompt()) sends that
    in place of all of this but its system messages. The tools stay as they are.
    """
    conversation = db.get_conversation_by_id(conversation_id)
    # In a hidden conversation hidden content is plainly shown, so its agent sees all of its memory
    hide = hide and not conversation_hidden(conversation)
    # What the agent hides on its own: the user's words, else the server's (empty: nothing)
    hide_definition = auto_hide_definition(current_user.get('user_id')) if config.supports_tools else ""
    # The agent's skills, listed in the prompt and loaded with use_skill; a model without tools has none
    skills = persona_skills(current_user, conversation) if config.supports_tools else []
    tools = _agent_tools(current_user, conversation, config, hide, hide_definition, skills)
    toolset = McpToolset()
    if mcp:
        tools, toolset = await _mcp_tools(current_user, conversation, config, tools, answer_id)
    if tools is not None and current_user.get('is_guest'):
        tools.hide_errors = True  # A guest sees that a tool failed, not the text of an unexpected error
    history_builder = ConversationHistoryBuilder(db)
    base_prompt = _own_system_prompt(conversation, hide)
    own_prompt = base_prompt is not None
    memory_note = None
    if base_prompt is None:
        base_prompt, memory_note = _memory_prompt(
            with_mcp_servers(with_skills(build_system_prompt(persona_prompt_for_conversation(current_user, conversation),
                                                             tools, hide_definition), skills),
                             toolset.servers, toolset.unavailable()),
            current_user, conversation, tools, hide)
    return AnswerParts(tools, history_builder, base_prompt, own_prompt,
                       history_builder.system_instructions(conversation_id), toolset.notices, memory_note)


async def _fold_into_summary(
    conversation_id: str,
    config: ModelConfig,
    entries: List[HistoryEntry],
    fold_count: int,
    summary: Optional[dict],
    token_budget: int,
    on_request: bool = False
) -> Tuple[dict, Usage]:
    """
    Fold the oldest fold_count entries (the history after the stored summary) into the
    conversation's summary and store it; on_request as for summarize().

    :return: The stored summary row and the usage of its model calls.
    :raises SummaryFailed: No summary could be written; nothing is stored.
    """
    content, usage = await summarize(
        config, entries[:fold_count], summary['content'] if summary else None, token_budget, on_request)
    stored = db.save_conversation_summary(
        conversation_id,
        covers_until=entries[fold_count - 1][0],
        message_count=(summary['message_count'] if summary else 0) + fold_count,
        content=content,
        model_name=config.display_name
    )
    return stored, usage


def _summary_step(step_id: str, started_ms: int, count: int, state: str, detail: str = "") -> dict:
    """The step that shows a summary of the oldest messages being written ('running', 'done' or 'failed')."""
    plural = "message" if count == 1 else "messages"
    title, content = {
        "running": (f"Summarizing {count} earlier {plural}",
                    "They no longer fit the model's context window."),
        "done": (f"Summarized {count} earlier {plural}",
                 f"From here on the model gets a summary instead of them. {detail}".strip()),
        "failed": ("Could not summarize earlier messages",
                   f"The oldest messages that don't fit the context window are left out. ({detail})"),
    }[state]
    now_ms = int(time.time() * 1000)
    step = AgentStep(id=step_id, type="observation", title=title, content=content, timestamp=started_ms,
                     duration=now_ms - started_ms if state != "running" else None)
    return _step_to_dict(step)


def _continue_step(step_id: str) -> dict:
    """The step that shows that the model was asked to go on after its own message, and with which words."""
    step = AgentStep(id=step_id, type="observation", title="Asked to go on",
                     content="The conversation ended with an answer, so the model got this note in place of a "
                             f"message from you: {CONTINUE_NOTE}",
                     timestamp=int(time.time() * 1000), duration=0)
    return _step_to_dict(step)


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
             },
             dependencies=[Depends(guest_write)])
async def user_send_message(request_body: ApiMessageSend, response: Response,
                             current_user: dict = Depends(get_current_user)):
    """
    Handles the sending of a message in a conversation.

    Returns the message's id and time. The server's clock decides both, like a messenger's
    server: the id is the time it stored the message in milliseconds, so the ids give the
    order of a conversation, and the client's time is ignored, since device clocks drift.
    """
    crud_logger.info(
        f"Message send called - User: {current_user['user_id']}, Conversation: {request_body.conversationId}")

    try:
        # Files alone are a message too (a photo without a word)
        if not request_body.content and not getattr(request_body, 'attachments', None):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Message content cannot be empty"
            )

        # Verify ownership
        if not verify_conversation_ownership(request_body.conversationId, current_user['user_id']):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this conversation"
            )

        message_id = int(time.time() * 1000)
        msg_time = message_id // 1000

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
                msg_time=msg_time,
                content=request_body.content
            )
            crud_logger.info(f"Agent message sent successfully - Message ID: {message_id}")
            return {"id": message_id, "time": msg_time}

        # For text/voice messages, use regular message storage
        db.create_message(
            message_id=message_id,
            conversation_id=request_body.conversationId,
            role_name=request_body.roleName,
            content=content_str,
            time=msg_time,
            msg_type=message_type,
            version=request_body.version or 1,
            last_modified=msg_time
        )

        crud_logger.info(f"Message sent successfully - Message ID: {message_id}")
        return {"id": message_id, "time": msg_time}

    except HTTPException:
        raise
    except Exception as e:
        crud_logger.error(f"Error sending message: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send message. Please try again later."
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
        if not verify_conversation_ownership(request_body.conversationId, current_user['user_id']):
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
            detail=answer_error(e, current_user)
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
              },
              dependencies=[Depends(guest_write)])
async def patch_message(request_body: MessagePatch, response: Response,
                        current_user: dict = Depends(get_current_user)):
    """
    Handles the patching of a message within a conversation.

    The content is the message's text: a text message keeps its attachments, an
    agent message keeps its steps and its tool record (only the answer text changes). With
    deleteFollowing, the later messages are deleted too, so the edited message
    can be answered again (stream-generate).
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
        if not verify_conversation_ownership(request_body.conversationId, current_user['user_id']):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this conversation"
            )

        current = db.get_message_by_id(request_body.id, request_body.conversationId)

        if current is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Message not found"
            )

        # Check for version conflict
        if current['version'] != request_body.version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Version conflict: current version is {current['version']}, provided version is {request_body.version}"
            )

        # A text message with attachments is stored as {"content", "attachments"} JSON; keep them
        content = request_body.content
        if (current.get('type') or 'text') == 'text' and (current['content'] or '').startswith('{'):
            try:
                stored = json.loads(current['content'])
            except json.JSONDecodeError:
                stored = None
            if isinstance(stored, dict) and stored.get('attachments'):
                content = json.dumps({**stored, 'content': request_body.content})

        # An answer keeps its tool calls and their results; the new text is its only text
        stored_record = db.get_tool_record(request_body.id) if current.get('type') == 'agent' else None

        # Update with version increment
        updated_message = db.update_message(
            message_id=request_body.id,
            conversation_id=request_body.conversationId,
            content=content,
            version=request_body.version,
            last_modified=int(time.time()),
            delete_following=request_body.deleteFollowing,
            tool_record=record_with_text(stored_record, request_body.content) if stored_record else None
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
            detail="Failed to update message. Please refresh and try again."
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
        if not verify_conversation_ownership(conversation_id, current_user['user_id']):
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
            detail="Failed to delete message. Please check your connection and try again."
        )


@router.post("/insert",
             response_model=MessageResponse,
             status_code=status.HTTP_201_CREATED,
             responses={
                 status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Access denied"},
                 status.HTTP_404_NOT_FOUND: {"description": "Message not found"},
                 status.HTTP_409_CONFLICT: {"model": ErrorResponse, "description": "No room next to the message"},
             },
             dependencies=[Depends(guest_write)])
async def insert_message(request_body: MessageInsert, current_user: dict = Depends(get_current_user)):
    """
    Insert a text message of the user, the assistant or the system before or after a message, without an answer.

    Its id (the order) lies between the message and its neighbour, so its time does too. A
    system message is an instruction to the model for the answers after it (see
    ConversationHistoryBuilder.system_instructions).
    """
    crud_logger.info(
        f"Insert message called - User: {current_user['user_id']}, Conversation: {request_body.conversationId}, "
        f"{request_body.position} {request_body.messageId}")

    if not verify_conversation_ownership(request_body.conversationId, current_user['user_id']):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this conversation")
    if db.get_message_by_id(request_body.messageId, request_body.conversationId) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    inserted = db.insert_message_next_to(
        conversation_id=request_body.conversationId,
        message_id=request_body.messageId,
        before=request_body.position == "before",
        role_name=request_body.roleName,
        content=request_body.content
    )
    if inserted is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="There is no room for a message here; insert it next to another message")

    return MessageResponse(
        id=inserted['id'],
        conversationId=inserted['conversationId'],
        roleName=inserted['roleName'],
        content=inserted['content'],
        time=inserted['time'],
        type='text',
        version=inserted['version'],
        lastModified=inserted['lastModified'],
        rating=inserted.get('rating')
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
        if not verify_conversation_ownership(request_body.conversationId, current_user['user_id']):
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
            detail="Failed to rate message"
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
        if not verify_conversation_ownership(request_body.conversationId, current_user['user_id']):
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
            detail=answer_error(e, current_user)
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
             },
             dependencies=[Depends(guest_write)])
async def send_and_generate_message(
        request_body: ApiMessageSendAndGenerate,
        request: Request,
        response: Response,
        current_user: dict = Depends(get_current_user)
):
    """
    Handles the processing and storage of user-generated messages while optionally
    generating AI responses.
    """
    try:
        if not verify_conversation_ownership(request_body.conversationId, current_user['user_id']):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this conversation"
            )

        # An answer counts against the guests' limit like the other generating endpoints,
        # before anything is stored (agent messages are stored without an answer)
        if request_body.generateResponse and request_body.type != 'agent':
            count_guest_request(request, current_user, "answers")

        # The server stamps the time, as in /send
        user_message_id = int(time.time() * 1000)
        user_message_time = user_message_id // 1000
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
                msg_time=user_message_time,
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
                time=user_message_time,
                type='agent',
                version=request_body.version or 1,
                lastModified=user_message_time,
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
            time=user_message_time,
            msg_type=message_type,
            version=request_body.version or 1,
            last_modified=user_message_time
        )

        user_message_response = MessageResponse(
            id=user_message_id,
            conversationId=request_body.conversationId,
            roleName=request_body.roleName,
            content=content_str,
            time=user_message_time,
            type=message_type,
            version=request_body.version or 1,
            lastModified=user_message_time
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
            detail=answer_error(e, current_user)
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
    current_user: dict = Depends(get_current_user),
    hide: bool = Depends(family_mode)
):
    """
    Stream agent reasoning steps and final response using Server-Sent Events.

    This endpoint returns an SSE stream with the following event types:
    - message_start: Message metadata, including the model that answers (modelId, modelName)
    - step: An agent reasoning step (thought, tool_call, tool_result, observation);
      a step with the id of an earlier one replaces it
    - step_delta: Text appended to an earlier step ({"id", "delta"}), the model's live reasoning
    - token: A token from the final response stream
    - summary: A new summary of the oldest messages (ConversationSummary), written
      before the answer when the history nearly fills the model's context window;
      a step shows it being written
    - done: Signals completion with the message ID, the model and the token usage
    - error: An error occurred during processing

    The agent loop (backend/llm) runs the model with its tools (the conversation's
    files, web search and the optional Neo4j knowledge graph), limited to the tool
    groups of the conversation's persona.
    """
    crud_logger.info(
        f"Stream generate called - User: {current_user['user_id']}, Conversation: {request_body.conversationId}")

    # Verify ownership before starting stream
    if not verify_conversation_ownership(request_body.conversationId, current_user['user_id']):
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
        answer_record: list = []  # The answer's tool calls and results as the model got them
        usage: Optional[Usage] = None
        summary_usage: Optional[Usage] = None

        def step_event(step_dict: dict) -> dict:
            """Record a step (a known id replaces the earlier one) and make its event."""
            position = step_positions.get(step_dict['id'])
            if position is None:
                step_positions[step_dict['id']] = len(steps)
                steps.append(step_dict)
            else:
                steps[position] = step_dict
            return {"event": "step", "data": json.dumps(step_dict)}

        def total_usage() -> Optional[Usage]:
            """The answer's usage, with the summary's model calls."""
            if summary_usage is None:
                return usage
            total = Usage()
            total.add(summary_usage)
            if usage is not None:
                total.add(usage)
            return total

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
            tools, history_builder, system_prompt, token_budget, mcp_notices, memory_note = await _answer_context(
                current_user, request_body.conversationId, config, answer_id=message_id, hide=hide)
            # MCP servers of the agent that give no tools this time (unreachable, or not signed in)
            for notice in mcp_notices:
                now_ms = int(time.time() * 1000)
                yield step_event(_step_to_dict(AgentStep(id=f"mcp-{notice.server_id}-{now_ms}", timestamp=now_ms,
                                                         **notice_step(notice))))

            # Build conversation history with placeholders for previous attachments: the
            # summary of the oldest messages, then as many messages as fit the model's context window
            summary = db.get_conversation_summary(request_body.conversationId)
            entries, available_attachments = await history_builder.build_entries(
                request_body.conversationId,
                include_latest_attachments=True,
                supports_vision=config.supports_vision,
                summary=summary
            )

            # Fold the oldest messages into the summary once the history nearly fills the window
            fold_count = messages_to_summarize(entries, summary, token_budget)
            if fold_count:
                started_ms = int(time.time() * 1000)
                step_id = f"{SUMMARY_STEP_PREFIX}{started_ms}"
                yield step_event(_summary_step(step_id, started_ms, fold_count, "running"))
                summary_usage = Usage()
                try:
                    summary, summary_usage = await _fold_into_summary(
                        request_body.conversationId, config, entries, fold_count, summary, token_budget)
                    entries = entries[fold_count:]
                    covered = summary['message_count']
                    detail = (f"It covers all {covered} messages up to here." if covered > fold_count else "")
                    yield step_event(_summary_step(step_id, started_ms, fold_count, "done", detail))
                    yield {
                        "event": "summary",
                        "data": json.dumps(ConversationSummary.from_row(summary).model_dump())
                    }
                except SummaryFailed as e:
                    summary_usage = e.usage
                    crud_logger.warning(f"Summary of {request_body.conversationId} failed ({e.reason}): {e}")
                    yield step_event(_summary_step(step_id, started_ms, fold_count, "failed", e.reason))
            history_messages = history_builder.assemble(request_body.conversationId, entries, summary, token_budget)

            if not history_messages:
                yield {
                    "event": "error",
                    "data": json.dumps({"error": "No messages found in conversation"})
                }
                return

            # Generate after an answer (manual editing): a note in the user's place asks the model
            # to go on, and a step shows that it got one
            if needs_continue_note(history_messages):
                history_messages.append(continue_message())
                yield step_event(_continue_step(f"continue-{message_id}"))

            if not any(message.get('role') == 'user' for message in history_messages):
                yield {
                    "event": "error",
                    "data": json.dumps({"error": "No user message found in conversation"})
                }
                return

            # What changed in the memory since the prompt's snapshot: a note at the start of the
            # newest user message, so the start of the request stays the same (memory_snapshot)
            history_messages = memory_snapshot.with_note(history_messages, memory_note)

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
                    yield step_event(_step_to_dict(event_data))
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
                elif event_type == "tool_record":
                    answer_record = event_data
                elif event_type == "usage":
                    usage = event_data

            # Save using JSONB storage, with the model that answered and its usage
            usage_data = (total_usage() or Usage()).to_api(config)
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
                usage=usage_data,
                tool_record=answer_record
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
            error_text = answer_error(e, current_user)

            # Save error state using JSONB storage, with the usage until the error
            db.create_agent_message(
                message_id=message_id,
                conversation_id=request_body.conversationId,
                role_name=request_body.aiParticipant,
                time=current_time,
                content=final_response,  # Response text (unified with text messages)
                status='error',
                error=error_text,
                steps=steps,
                model_id=config.id,
                model_name=config.display_name,
                usage=total_usage().to_api(config) if total_usage() else None,
                tool_record=answer_record  # The tools that ran before the error did run
            )

            yield {
                "event": "error",
                "data": json.dumps({"error": error_text})
            }

    return EventSourceResponse(event_generator())


@router.post("/summarize",
             response_model=ConversationSummary,
             responses={
                 status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Access denied"},
                 status.HTTP_409_CONFLICT: {"model": ErrorResponse,
                                            "description": "No messages after the summary"},
                 status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse,
                                                        "description": "Too short to summarize"},
                 status.HTTP_502_BAD_GATEWAY: {"model": ErrorResponse,
                                               "description": "The model could not write a summary"},
                 status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse, "description": "No model configured"}
             },
             dependencies=[Depends(rate_limit_guest)])
async def summarize_conversation(
    request_body: SummarizeRequest,
    current_user: dict = Depends(get_current_user)
) -> ConversationSummary:
    """
    Fold all messages of a conversation so far into its summary, at the user's request.

    stream-generate writes the summary on its own once the history nearly fills the
    model's context window; this writes it now and for every message: the next answer
    gets the summary and only the messages after it. The conversation's model writes
    it, merging the summary the conversation already has.

    :return: The new summary.
    :raises HTTPException: 403 without access to the conversation or its model, 409 if
        no message comes after the summary, 422 if the messages are too short to
        summarize, 502 if the model could not write a summary (nothing is stored),
        503 without a model.
    """
    conversation_id = request_body.conversationId
    if not verify_conversation_ownership(conversation_id, current_user['user_id']):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this conversation")

    config = _resolve_model_or_503(current_user, conversation_id)
    _, history_builder, _, token_budget, _, _ = await _answer_context(current_user, conversation_id, config, mcp=False)
    summary = db.get_conversation_summary(conversation_id)
    # Placeholders for all attachments: the summary keeps their file names and ids
    entries, _ = await history_builder.build_entries(
        conversation_id, include_latest_attachments=False, supports_vision=config.supports_vision, summary=summary)
    if not entries:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="There are no messages after the summary to summarize.")

    try:
        stored, usage = await _fold_into_summary(
            conversation_id, config, entries, len(entries), summary, token_budget, on_request=True)
    except SummaryFailed as e:
        crud_logger.warning(f"Summary of {conversation_id} on request failed ({e.reason}): {e}; "
                            f"tokens in/out: {e.usage.input_tokens}/{e.usage.output_tokens}")
        if e.reason in ("too_short", "not_smaller"):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail="The conversation is too short to summarize: a summary would be "
                                       "no shorter than its messages.")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=f"{config.display_name} could not write a summary ({e.reason}).")

    crud_logger.info(f"Conversation {conversation_id} summarized on request by user {current_user['user_id']}: "
                     f"{len(entries)} messages with {config.display_name}, "
                     f"tokens in/out: {usage.input_tokens}/{usage.output_tokens}")
    return ConversationSummary.from_row(stored)


@router.post("/context-size",
             response_model=ContextSize,
             responses={
                 status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Access denied"},
                 status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse, "description": "No model configured"}
             })
async def context_size(
    request_body: ContextSizeRequest,
    current_user: dict = Depends(get_current_user),
    hide: bool = Depends(family_mode)
) -> ContextSize:
    """
    About how many input tokens the next answer in a conversation sends (the token
    indicator of manual editing).

    Counts what stream-generate would send now: the system prompt, the tool definitions
    and the history (the summary, then the newest messages that fit the model's context
    window, the latest user message with its attachments, earlier answers with their tool
    calls and the results). Nothing is sent to a model, and the agent's MCP servers are not
    asked for their tools.

    :raises HTTPException: 403 without access to the conversation or the model, 503 without a model.
    """
    conversation_id = request_body.conversationId
    if not verify_conversation_ownership(conversation_id, current_user['user_id']):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this conversation")

    config = _resolve_model_or_503(current_user, conversation_id, request_body.modelId)
    tools, history_builder, system_prompt, token_budget, _, memory_note = await _answer_context(
        current_user, conversation_id, config, mcp=False, hide=hide)
    summary = db.get_conversation_summary(conversation_id)
    entries, _ = await history_builder.build_entries(
        conversation_id, include_latest_attachments=True, supports_vision=config.supports_vision, summary=summary)
    kept = history_builder.fit(conversation_id, entries, summary, token_budget)

    system_tokens = estimate_tokens(system_prompt)
    tool_tokens = estimate_tokens(json.dumps(tools.openai_schemas())) if tools else 0
    history_tokens = sum(entry_tokens(message) for message in kept)
    if summary:
        history_tokens += estimate_tokens(summary_message(summary['content'])["content"])
    if memory_note:
        history_tokens += estimate_tokens(memory_note)  # Goes with the newest user message
    message_count = len(kept)
    return ContextSize(
        modelId=config.id,
        contextWindow=config.context_window or DEFAULT_CONTEXT_WINDOW,
        inputTokens=system_tokens + tool_tokens + history_tokens,
        systemTokens=system_tokens,
        toolTokens=tool_tokens,
        historyTokens=history_tokens,
        historyBudget=token_budget,
        messageCount=message_count,
        leftOutCount=len(entries) - message_count,
        summarizes=messages_to_summarize(entries, summary, token_budget) > 0,
    )


def _shown_system_prompt(parts: AnswerParts, in_family_mode: bool) -> SystemPrompt:
    """The system prompt as the chat shows it: a device in family mode doesn't get the section on hidden content."""
    content = without_hide_section(parts.base_prompt) if in_family_mode else parts.base_prompt
    return SystemPrompt(content=content, custom=parts.own_prompt, tokens=estimate_tokens(content))


@router.get("/system-prompt",
            response_model=SystemPrompt,
            responses={
                status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Access denied"},
                status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse, "description": "No model configured"}
            })
async def get_system_prompt(
    conversationId: str,
    modelId: Optional[int] = None,
    current_user: dict = Depends(get_current_user),
    hide: bool = Depends(family_mode)
) -> SystemPrompt:
    """
    The system prompt the next answer in a conversation gets, as its model gets it. Manual
    editing shows it as the conversation's first message.

    Built as stream-generate builds it, for the conversation's model (or modelId) and with
    the agent's MCP servers, but without the conversation's system messages: they follow it,
    and the chat shows them where they are. Nothing is sent to a model.

    :raises HTTPException: 403 without access to the conversation or the model, 503 without a model.
    """
    if not verify_conversation_ownership(conversationId, current_user['user_id']):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this conversation")
    config = _resolve_model_or_503(current_user, conversationId, modelId)
    return _shown_system_prompt(await _answer_parts(current_user, conversationId, config, hide=hide), hide)


@router.put("/system-prompt",
            response_model=SystemPrompt,
            responses={
                status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Access denied"},
                status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse, "description": "No model configured"}
            },
            dependencies=[Depends(guest_write)])
async def set_system_prompt(
    request_body: SystemPromptUpdate,
    current_user: dict = Depends(get_current_user),
    hide: bool = Depends(family_mode)
) -> SystemPrompt:
    """
    Set a conversation's own system prompt (manual editing): from now on its answers get this
    text as it is, in place of the prompt built from the conversation's agent, so the memory,
    the tool notes and the date in it no longer change. '' sends no system prompt; None goes
    back to the built one. The conversation's system messages still follow it, and the tools
    stay as they are.

    Returns the prompt the next answer gets.

    :raises HTTPException: 403 without access to the conversation or the model, 503 without a model.
    """
    conversation_id = request_body.conversationId
    if not verify_conversation_ownership(conversation_id, current_user['user_id']):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this conversation")
    config = _resolve_model_or_503(current_user, conversation_id, request_body.modelId)

    content = request_body.content
    if content is not None and hide:
        # A device in family mode was shown the prompt without its hidden lines and without the
        # section on hidden content: a save keeps what the device didn't see
        previous = (db.get_conversation_by_id(conversation_id) or {}).get('system_prompt')
        if previous is None:
            previous = (await _answer_parts(current_user, conversation_id, config, mcp=False, hide=hide)).base_prompt
        else:
            content = restore_hidden(previous, content)
        section = hide_section(previous)
        if section and not hide_section(content):
            content = f"{content.rstrip()}\n\n{section}" if content.strip() else section

    db.update_conversation(conversation_id, current_user['user_id'], system_prompt=content)
    crud_logger.info(f"System prompt of conversation {conversation_id} "
                     f"{'reset' if content is None else f'set ({len(content)} characters)'}")
    return _shown_system_prompt(await _answer_parts(current_user, conversation_id, config, hide=hide), hide)


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
    request: Request,
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
        if not verify_conversation_ownership(conversation_id, current_user['user_id']):
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

        # New speech costs a model call or two; cached speech (above) is free
        count_guest_request(request, current_user, "speech")

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
            detail="TTS generation failed"
        )
