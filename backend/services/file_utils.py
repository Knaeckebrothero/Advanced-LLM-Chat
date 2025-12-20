# backend/services/file_utils.py
"""
Shared file handling utilities used across multiple service modules.
"""

from pathlib import Path
from typing import Optional

from ..config import FILES_DIR


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


def is_audio(mime_type: str) -> bool:
    """Check if the MIME type is a supported audio format."""
    # Handle MIME types with parameters (e.g., "audio/webm;codecs=opus")
    base_mime = mime_type.lower().split(';')[0].strip()
    return base_mime in SUPPORTED_AUDIO_TYPES


def get_audio_extension(mime_type: str) -> Optional[str]:
    """Get the file extension for an audio MIME type."""
    base_mime = mime_type.lower().split(';')[0].strip()
    return SUPPORTED_AUDIO_TYPES.get(base_mime)
