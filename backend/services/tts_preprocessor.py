# backend/services/tts_preprocessor.py
"""
TTS Text Preprocessor - transforms text for optimal speech synthesis.

Uses an LLM to convert markdown-heavy, structured text into clean prose
suitable for text-to-speech. Handles:
- Markdown formatting removal
- Table conversion to descriptive prose
- Code block handling (skip or summarize)
- List conversion to flowing sentences
- Non-vocal character removal
"""

import logging
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from .llm_provider import get_llm, wrap_system_prompt_with_reasoning
from ..config import TTS_PREPROCESS_ENABLED

logger = logging.getLogger(__name__)

# Preprocessing prompt
TTS_PREPROCESS_PROMPT = """You are a text preprocessor for a text-to-speech system. Convert the following message into clean, natural prose that sounds good when read aloud.

Rules:
1. Remove ALL markdown formatting:
   - Convert **bold** and *italic* markers to plain text
   - Remove # headers, convert to natural sentence starters
   - Remove code fence markers (```)

2. Handle tables:
   - Convert tabular data to natural descriptive sentences
   - Don't read tables cell by cell - describe the key information
   - Example: Instead of reading "Name | Age", say "The data shows names along with ages"

3. Handle code blocks:
   - For short code: briefly mention what it does without reading syntax
   - For longer code: summarize its purpose in one sentence
   - Never read out raw code syntax, variable names, or brackets

4. Handle lists:
   - Convert bullet points to flowing prose using transitional words
   - Example: "- First\n- Second" becomes "First, there is... Additionally, there is..."

5. Remove or convert:
   - URLs: mention "a link" or omit if not important
   - Special characters that can't be spoken naturally
   - Multiple consecutive newlines

6. Preserve:
   - The meaning and tone of the original text
   - Technical terms and proper names
   - Numbers (keep them readable)

Output ONLY the processed text, ready for TTS. Do not include explanations or meta-commentary.

Text to process:
"""


def needs_preprocessing(text: str) -> bool:
    """
    Quick heuristic to determine if text needs LLM preprocessing.

    Returns False for simple text to avoid unnecessary LLM calls.

    Args:
        text: The text to check.

    Returns:
        True if text likely contains markdown or structured content.
    """
    if not text or len(text) < 50:
        return False

    # Check for markdown indicators
    markdown_indicators = [
        '**', '```', '|', '# ', '## ', '### ',
        '- ', '* ', '1. ', '[', '](', '<', '>'
    ]

    for indicator in markdown_indicators:
        if indicator in text:
            return True

    return False


async def preprocess_for_tts(text: str) -> Optional[str]:
    """
    Preprocess text using LLM to optimize for TTS.

    Uses the configured LLM provider from llm_provider.py.

    Args:
        text: Raw message text (may contain markdown, tables, etc.)

    Returns:
        Processed text optimized for speech, or None if preprocessing fails or is disabled.
    """
    if not TTS_PREPROCESS_ENABLED:
        logger.debug("TTS preprocessing disabled")
        return None

    if not needs_preprocessing(text):
        logger.debug("Text doesn't need preprocessing (simple text)")
        return None

    try:
        logger.info(f"Preprocessing text for TTS: {len(text)} chars")

        # Get the configured LLM with lower temperature for consistency
        llm = get_llm(temperature=0.3)

        # Wrap preprocessing prompt with auxiliary reasoning level
        wrapped_prompt = wrap_system_prompt_with_reasoning(
            TTS_PREPROCESS_PROMPT,
            auxiliary=True
        )

        # Use SystemMessage for instruction, HumanMessage for text
        messages = [
            SystemMessage(content=wrapped_prompt),
            HumanMessage(content=text)
        ]

        # Invoke the LLM
        response = await llm.ainvoke(messages)

        processed_text = response.content

        if processed_text and isinstance(processed_text, str):
            processed_text = processed_text.strip()
            logger.info(f"TTS preprocessing complete: {len(text)} -> {len(processed_text)} chars")
            return processed_text

        logger.warning("TTS preprocessing returned empty or invalid response")
        return None

    except Exception as e:
        logger.error(f"TTS preprocessing failed: {e}", exc_info=True)
        return None


def is_preprocessing_enabled() -> bool:
    """Check if TTS preprocessing is enabled."""
    return TTS_PREPROCESS_ENABLED
