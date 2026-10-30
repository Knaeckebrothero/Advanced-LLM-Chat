"""
LLM (Large Language Model) service operations.
"""
import logging
import uuid
from typing import Optional

from backend.database import db
from backend.llm import ModelConfig, Usage, build_system_prompt, complete
from .conversation_history import ConversationHistoryBuilder

log = logging.getLogger(__name__)


def generate_conversation_id() -> str:
    """
    Generates a unique conversation identifier.

    This function creates a unique identifier for a conversation using a UUID
    (Universally Unique Identifier). It ensures the generated ID is globally
    unique.

    :returns: A unique string identifier for a conversation.
    :rtype: str
    """
    return str(uuid.uuid4())


async def generate_reply(
    config: ModelConfig,
    conversation_id: str,
    system_prompt: Optional[str] = None,
    limit: int = 20,
    before_message: Optional[dict] = None
) -> tuple[str, Usage]:
    """
    Generate a plain text reply to a conversation, without tools or streaming.

    Used by the non-streaming endpoints (generate, send-and-generate, regenerate);
    the chat itself uses the streaming agent.

    :param config: The model that answers.
    :param conversation_id: The conversation to answer.
    :param system_prompt: Optional system prompt; defaults to the assistant's identity prompt.
    :param limit: Maximum number of earlier messages sent as context.
    :param before_message: Only use messages before this message row (regenerating it).
    :return: The reply text and the token usage.
    :raises ValueError: If the conversation has no messages.
    """
    history_builder = ConversationHistoryBuilder(db)
    messages, _ = await history_builder.build_history(
        conversation_id,
        limit=limit,
        include_latest_attachments=True,
        supports_vision=config.supports_vision,
        before_message=before_message
    )
    if not messages:
        raise ValueError("No messages found in conversation")

    log.debug(f"Generating reply for {conversation_id} with {config.model_id}: {len(messages)} messages of context")
    reply, usage = await complete(
        config,
        messages,
        system_prompt=system_prompt or build_system_prompt(None, None)
    )
    log.info(f"LLM response generated: {len(reply)} characters")
    return reply, usage
