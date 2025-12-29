# backend/services/title_generator.py
"""
Title generation service for conversations.
Generates concise conversation titles based on the first user message.
"""

import logging
from typing import Optional
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

TITLE_PROMPT = """Generate a short title (3-6 words) for a conversation starting with this message.
Return ONLY the title. No quotes, no ending punctuation.

Message: {message}"""


async def generate_conversation_title(
    first_message: str,
    fallback_title: Optional[str] = None
) -> str:
    """
    Generate a conversation title using the LLM.

    Args:
        first_message: The user's first message in the conversation.
        fallback_title: Optional fallback if generation fails.
                       Defaults to truncated first_message.

    Returns:
        Generated title (3-6 words) or fallback on failure.
    """
    if fallback_title is None:
        fallback_title = _truncate_title(first_message)

    try:
        from .llm_provider import get_llm

        llm = get_llm(temperature=0.3)

        messages = [
            SystemMessage(content="You generate concise conversation titles."),
            HumanMessage(content=TITLE_PROMPT.format(message=first_message[:500]))
        ]

        response = await llm.ainvoke(messages)
        title = _sanitize_title(response.content.strip())

        if len(title) < 2:
            logger.warning("Generated title too short, using fallback")
            return fallback_title

        logger.info(f"Generated conversation title: {title}")
        return title

    except Exception as e:
        logger.error(f"Title generation failed: {e}")
        return fallback_title


def _truncate_title(message: str, max_len: int = 50) -> str:
    """Truncate message to create a fallback title."""
    msg = message.strip()
    if len(msg) <= max_len:
        return msg
    # Try to break at word boundary
    truncated = msg[:max_len - 3]
    last_space = truncated.rfind(' ')
    if last_space > max_len // 2:
        truncated = truncated[:last_space]
    return truncated + '...'


def _sanitize_title(title: str) -> str:
    """Clean up generated title."""
    # Remove surrounding quotes if present
    title = title.strip('"\'')
    # Remove trailing punctuation
    title = title.rstrip('.!?')
    # Limit length
    if len(title) > 100:
        title = title[:97] + '...'
    return title
