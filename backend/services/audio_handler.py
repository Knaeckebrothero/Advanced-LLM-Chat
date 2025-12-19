# backend/services/audio_handler.py
"""
Audio handling utilities for transcription.
Handles audio transcription using OpenAI Whisper and preparing transcripts for LLM context.
"""

import logging
from pathlib import Path
from typing import Optional

from ..config import FILES_DIR

logger = logging.getLogger(__name__)

# Supported audio MIME types
SUPPORTED_AUDIO_TYPES = {
    'audio/webm': 'webm',
    'audio/ogg': 'ogg',
    'audio/mp4': 'm4a',
    'audio/mpeg': 'mp3',
    'audio/wav': 'wav',
    'audio/x-wav': 'wav',
    'audio/mp3': 'mp3',
    'audio/m4a': 'm4a',
}

# Whisper model to use (tiny, base, small, medium, large)
# tiny is fastest but less accurate, large is most accurate but slow
WHISPER_MODEL = 'base'

# Lazy-loaded whisper model (cached after first load)
_whisper_model = None


def is_audio(mime_type: str) -> bool:
    """Check if the MIME type is a supported audio format."""
    # Handle MIME types with parameters (e.g., "audio/webm;codecs=opus")
    base_mime = mime_type.lower().split(';')[0].strip()
    return base_mime in SUPPORTED_AUDIO_TYPES


def get_audio_type(mime_type: str) -> Optional[str]:
    """Get the audio type from MIME type."""
    # Handle MIME types with parameters (e.g., "audio/webm;codecs=opus")
    base_mime = mime_type.lower().split(';')[0].strip()
    return SUPPORTED_AUDIO_TYPES.get(base_mime)


def get_file_path(file_id: str) -> Optional[Path]:
    """
    Find a file in the files directory by its ID (without extension).

    Args:
        file_id: The file ID (filename without extension).

    Returns:
        Path to the file if found, None otherwise.
    """
    files_dir = Path(FILES_DIR)
    if not files_dir.exists():
        return None

    for file_path in files_dir.iterdir():
        if file_path.is_file() and file_path.stem == file_id:
            return file_path

    return None


def _get_whisper_model():
    """
    Lazy-load and cache the whisper model.

    Returns:
        Whisper model or None if loading fails.
    """
    global _whisper_model

    if _whisper_model is not None:
        return _whisper_model

    try:
        import whisper
        logger.info(f"Loading Whisper model: {WHISPER_MODEL}")
        _whisper_model = whisper.load_model(WHISPER_MODEL)
        logger.info("Whisper model loaded successfully")
        return _whisper_model
    except ImportError:
        logger.error("openai-whisper not installed. Run: pip install openai-whisper")
        return None
    except Exception as e:
        logger.error(f"Error loading Whisper model: {e}")
        return None


def transcribe_audio(file_path: Path, language: Optional[str] = None) -> Optional[str]:
    """
    Transcribe audio file using Whisper.

    Args:
        file_path: Path to the audio file.
        language: Optional language code (e.g., 'en', 'de'). Auto-detect if None.

    Returns:
        Transcribed text or None if transcription fails.
    """
    model = _get_whisper_model()
    if model is None:
        return None

    try:
        logger.info(f"Transcribing audio file: {file_path}")

        # Transcribe with options
        options = {
            'fp16': False,  # Use FP32 for CPU compatibility
        }
        if language:
            options['language'] = language

        result = model.transcribe(str(file_path), **options)
        transcript = result.get('text', '').strip()

        if transcript:
            logger.info(f"Transcription complete: {len(transcript)} characters")
        else:
            logger.warning("Transcription returned empty text")

        return transcript if transcript else None
    except Exception as e:
        logger.error(f"Error transcribing audio {file_path}: {e}")
        return None


def process_audio(file_path: Path, file_id: str) -> dict:
    """
    Process an audio file: transcribe and save transcript.

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

    # Transcribe audio
    transcript = transcribe_audio(file_path)
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
