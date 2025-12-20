# backend/services/audio_handler.py
"""
Audio handling utilities for transcription.
Handles audio transcription using OpenAI Whisper API (default) or local Whisper model (fallback).
"""

import logging
import os
from pathlib import Path
from typing import Optional

from openai import AsyncOpenAI

from ..config import (
    FILES_DIR,
    WHISPER_BASE_URL,
    WHISPER_MODEL,
    WHISPER_LANGUAGE,
    USE_LOCAL_WHISPER,
    LOCAL_WHISPER_MODEL,
)
from .file_utils import SUPPORTED_AUDIO_TYPES, is_audio, get_file_path, get_audio_extension

logger = logging.getLogger(__name__)

# Lazy-loaded clients
_openai_client: Optional[AsyncOpenAI] = None
_whisper_model = None  # Local Whisper model (cached after first load)


# Re-export for backwards compatibility
def get_audio_type(mime_type: str) -> Optional[str]:
    """Get the audio type from MIME type."""
    return get_audio_extension(mime_type)


def _get_openai_client() -> Optional[AsyncOpenAI]:
    """
    Get OpenAI client for Whisper API.

    Returns:
        AsyncOpenAI client or None if no API key is configured.
    """
    global _openai_client

    if _openai_client is not None:
        return _openai_client

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.info("No OPENAI_API_KEY configured - will use local Whisper for transcription")
        return None

    _openai_client = AsyncOpenAI(api_key=api_key, base_url=WHISPER_BASE_URL)
    logger.info(f"OpenAI Audio client initialized: model={WHISPER_MODEL}, base_url={WHISPER_BASE_URL}")
    return _openai_client


def _get_local_whisper_model():
    """
    Lazy-load and cache the local whisper model.

    Returns:
        Whisper model or None if loading fails.
    """
    global _whisper_model

    if _whisper_model is not None:
        return _whisper_model

    try:
        import whisper
        logger.info(f"Loading local Whisper model: {LOCAL_WHISPER_MODEL}")
        _whisper_model = whisper.load_model(LOCAL_WHISPER_MODEL)
        logger.info("Local Whisper model loaded successfully")
        return _whisper_model
    except ImportError:
        logger.error("openai-whisper not installed. Run: pip install openai-whisper")
        return None
    except Exception as e:
        logger.error(f"Error loading local Whisper model: {e}")
        return None


async def _transcribe_with_openai(file_path: Path) -> Optional[str]:
    """
    Transcribe audio file using OpenAI Whisper API.

    Args:
        file_path: Path to the audio file.

    Returns:
        Transcribed text or None if transcription fails.
    """
    client = _get_openai_client()
    if not client:
        return None

    try:
        logger.info(f"Transcribing with OpenAI API: {file_path}")

        with open(file_path, 'rb') as audio_file:
            kwargs = {"model": WHISPER_MODEL, "file": audio_file}
            if WHISPER_LANGUAGE:
                kwargs["language"] = WHISPER_LANGUAGE

            response = await client.audio.transcriptions.create(**kwargs)

        transcript = response.text.strip() if response.text else None

        if transcript:
            logger.info(f"OpenAI transcription complete: {len(transcript)} characters")
        else:
            logger.warning("OpenAI transcription returned empty text")

        return transcript
    except Exception as e:
        logger.error(f"Error with OpenAI transcription {file_path}: {e}")
        return None


def _transcribe_local(file_path: Path, language: Optional[str] = None) -> Optional[str]:
    """
    Transcribe audio file using local Whisper model (fallback).

    Args:
        file_path: Path to the audio file.
        language: Optional language code (e.g., 'en', 'de'). Auto-detect if None.

    Returns:
        Transcribed text or None if transcription fails.
    """
    model = _get_local_whisper_model()
    if model is None:
        return None

    try:
        logger.info(f"Transcribing with local Whisper: {file_path}")

        # Transcribe with options
        options = {
            'fp16': False,  # Use FP32 for CPU compatibility
        }
        if language:
            options['language'] = language

        result = model.transcribe(str(file_path), **options)
        transcript = result.get('text', '').strip()

        if transcript:
            logger.info(f"Local transcription complete: {len(transcript)} characters")
        else:
            logger.warning("Local transcription returned empty text")

        return transcript if transcript else None
    except Exception as e:
        logger.error(f"Error with local transcription {file_path}: {e}")
        return None


# Keep old function name for backwards compatibility (deprecated)
def transcribe_audio(file_path: Path, language: Optional[str] = None) -> Optional[str]:
    """Deprecated: Use process_audio() instead. This is the local-only transcription."""
    return _transcribe_local(file_path, language)


async def process_audio(file_path: Path, file_id: str) -> dict:
    """
    Process an audio file: transcribe and save transcript.

    Uses OpenAI Whisper API by default.
    Set USE_LOCAL_WHISPER=true to force local model.
    Falls back to local Whisper if API fails or no API key is configured.

    Args:
        file_path: Path to the audio file.
        file_id: File ID for naming output files.

    Returns:
        Dict with 'transcript_path' and 'transcript' on success.
    """
    output_dir = file_path.parent
    result = {
        'transcript_path': None,
        'transcript': None,
        'error': None
    }

    transcript = None

    # Try OpenAI API first (unless local is forced)
    if not USE_LOCAL_WHISPER:
        try:
            transcript = await _transcribe_with_openai(file_path)
        except Exception as e:
            logger.warning(f"OpenAI transcription failed, falling back to local: {e}")

    # Fallback to local Whisper if needed
    if not transcript:
        transcript = _transcribe_local(file_path, WHISPER_LANGUAGE)

    if transcript:
        # Save transcript to file
        transcript_path = output_dir / f"{file_id}_transcript.txt"
        try:
            with open(transcript_path, 'w', encoding='utf-8') as f:
                f.write(transcript)
            result['transcript_path'] = transcript_path
            result['transcript'] = transcript
            logger.info(f"Saved transcript to {transcript_path}")
        except Exception as e:
            logger.error(f"Error saving transcript: {e}")
            result['error'] = str(e)
    else:
        result['error'] = "Transcription failed or returned empty text"

    return result


def get_transcript(file_id: str) -> Optional[str]:
    """
    Get transcript for an audio file.

    Args:
        file_id: The file ID.

    Returns:
        Transcript text or None.
    """
    files_dir = Path(FILES_DIR)
    transcript_path = files_dir / f"{file_id}_transcript.txt"

    if transcript_path.exists():
        try:
            with open(transcript_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading transcript file {transcript_path}: {e}")

    return None


def prepare_audio_for_llm(file_id: str, name: str) -> Optional[dict]:
    """
    Prepare audio content for inclusion in LLM context.

    Args:
        file_id: The file ID.
        name: Display name of the audio file.

    Returns:
        Dict with 'text' containing the transcript, or None if no transcript available.
    """
    transcript = get_transcript(file_id)
    if not transcript:
        return None

    return {
        'text': transcript,
        'name': name,
        'type': 'audio_transcript'
    }
