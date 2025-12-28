# backend/services/tts_handler.py
"""
Text-to-Speech handler for generating audio from text.
Uses OpenAI TTS API (default) or compatible endpoints.
"""

import logging
import os
from pathlib import Path
from typing import Optional

from openai import AsyncOpenAI

from ..config import (
    FILES_DIR,
    TTS_BASE_URL,
    TTS_MODEL,
    TTS_VOICE_EN,
    TTS_VOICE_DE,
    TTS_TIMEOUT,
)

logger = logging.getLogger(__name__)

# Lazy-loaded client
_openai_client: Optional[AsyncOpenAI] = None


def _get_openai_client() -> Optional[AsyncOpenAI]:
    """
    Get OpenAI client for TTS API.

    Returns:
        AsyncOpenAI client or None if no API key is configured.
    """
    global _openai_client

    if _openai_client is not None:
        return _openai_client

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("No OPENAI_API_KEY configured - TTS will not be available")
        return None

    _openai_client = AsyncOpenAI(api_key=api_key, base_url=TTS_BASE_URL, timeout=TTS_TIMEOUT)
    logger.info(f"TTS client initialized: model={TTS_MODEL}, base_url={TTS_BASE_URL}, timeout={TTS_TIMEOUT}s")
    return _openai_client


def get_voice_for_language(language: str) -> str:
    """
    Get the configured voice for a language.

    Args:
        language: Language code ('en', 'de', etc.)

    Returns:
        Voice name for the specified language.
    """
    if language.lower() in ('de', 'german', 'deutsch'):
        return TTS_VOICE_DE
    return TTS_VOICE_EN


async def generate_speech(
    text: str,
    language: str = "en",
    output_path: Optional[Path] = None
) -> Optional[bytes]:
    """
    Generate speech audio from text.

    Args:
        text: Text to convert to speech.
        language: Language code ('en' or 'de') for voice selection.
        output_path: Optional path to save the audio file.

    Returns:
        Audio bytes (MP3 format) or None if generation fails.
    """
    client = _get_openai_client()
    if not client:
        return None

    voice = get_voice_for_language(language)

    try:
        logger.info(f"Generating TTS: {len(text)} chars, voice={voice}, model={TTS_MODEL}")

        response = await client.audio.speech.create(
            model=TTS_MODEL,
            voice=voice,
            input=text,
            response_format="mp3"
        )

        # Get audio bytes
        audio_bytes = response.content

        # Save to file if path provided
        if output_path and audio_bytes:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'wb') as f:
                f.write(audio_bytes)
            logger.info(f"Saved TTS audio to {output_path}")

        logger.info(f"TTS generation complete: {len(audio_bytes)} bytes")
        return audio_bytes

    except Exception as e:
        logger.error(f"TTS generation failed: {e}")
        return None


def get_tts_audio_path(message_id: int, conversation_id: str) -> Path:
    """
    Get the path where TTS audio for a message would be stored.

    Args:
        message_id: The message ID.
        conversation_id: The conversation ID.

    Returns:
        Path to the TTS audio file.
    """
    return Path(FILES_DIR) / f"tts_{conversation_id}_{message_id}.mp3"


def get_cached_tts_audio(message_id: int, conversation_id: str) -> Optional[bytes]:
    """
    Get cached TTS audio for a message if it exists.

    Args:
        message_id: The message ID.
        conversation_id: The conversation ID.

    Returns:
        Audio bytes or None if not cached.
    """
    audio_path = get_tts_audio_path(message_id, conversation_id)

    if audio_path.exists():
        try:
            with open(audio_path, 'rb') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading cached TTS audio: {e}")

    return None


def delete_cached_tts_audio(message_id: int, conversation_id: str) -> bool:
    """
    Delete cached TTS audio for a message.

    Args:
        message_id: The message ID.
        conversation_id: The conversation ID.

    Returns:
        True if deleted, False otherwise.
    """
    audio_path = get_tts_audio_path(message_id, conversation_id)

    if audio_path.exists():
        try:
            audio_path.unlink()
            logger.info(f"Deleted cached TTS audio: {audio_path}")
            return True
        except Exception as e:
            logger.error(f"Error deleting cached TTS audio: {e}")

    return False
