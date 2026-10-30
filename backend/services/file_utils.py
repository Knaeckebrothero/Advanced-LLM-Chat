# backend/services/file_utils.py
"""
Shared file handling utilities used across multiple service modules.
"""

import logging
import re
import shutil
from pathlib import Path
from typing import Optional

from ..config import FILES_DIR

log = logging.getLogger(__name__)

# The IDs upload_files() (backend/api/files.py) gives uploads: file_<milliseconds>_<hex>.
# Files derived from an upload are named <file ID>_<suffix>, e.g. _text.txt, _page_1.png
FILE_ID_PATTERN = re.compile(r"file_\d+_[0-9a-f]+")


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
        log.debug(f"Files directory does not exist: {FILES_DIR}")
        return None

    for file_path in files_dir.iterdir():
        if file_path.is_file() and file_path.stem == file_id:
            log.debug(f"Found file: {file_path}")
            return file_path

    log.debug(f"File not found: {file_id}")
    return None


def is_file_id(value) -> bool:
    """Whether a value has the form of an upload's file ID (FILE_ID_PATTERN)."""
    return isinstance(value, str) and FILE_ID_PATTERN.fullmatch(value) is not None


def stored_file_ids() -> set[str]:
    """
    The IDs of the uploads stored in the files directory (not of their derived files).

    Returns:
        The file IDs; empty if the directory does not exist.
    """
    files_dir = Path(FILES_DIR)
    if not files_dir.is_dir():
        return set()
    return {path.stem for path in files_dir.iterdir() if path.is_file() and is_file_id(path.stem)}


def delete_stored_file(file_id: str) -> int:
    """
    Delete an upload and the files derived from it: the extracted text and page
    images of a PDF, the transcript of an audio file.

    Args:
        file_id: The file ID (filename without extension).

    Returns:
        Number of files (or directories) deleted; 0 for a value that is not a file ID.

    Raises:
        OSError: If a file cannot be deleted.
    """
    if not is_file_id(file_id):
        log.warning(f"Not deleting '{file_id}': not a file ID")
        return 0
    files_dir = Path(FILES_DIR)
    if not files_dir.is_dir():
        return 0

    deleted = 0
    for path in files_dir.iterdir():
        if path.stem != file_id and not path.name.startswith(f"{file_id}_"):
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        log.debug(f"Deleted {path}")
        deleted += 1
    return deleted


def is_audio(mime_type: str) -> bool:
    """Check if the MIME type is a supported audio format."""
    # Handle MIME types with parameters (e.g., "audio/webm;codecs=opus")
    base_mime = mime_type.lower().split(';')[0].strip()
    return base_mime in SUPPORTED_AUDIO_TYPES


def get_audio_extension(mime_type: str) -> Optional[str]:
    """Get the file extension for an audio MIME type."""
    base_mime = mime_type.lower().split(';')[0].strip()
    return SUPPORTED_AUDIO_TYPES.get(base_mime)
