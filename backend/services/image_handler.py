# backend/services/image_handler.py
"""
Image handling utilities for AI integration.
Handles reading, encoding, and preparing images for vision-capable LLMs.
"""

import base64
import logging
from pathlib import Path
from typing import Optional

from ..config import FILES_DIR, MODEL_RECEIVE_IMAGES

logger = logging.getLogger(__name__)

# Supported image MIME types for vision models
SUPPORTED_IMAGE_TYPES = {
    'image/jpeg': True,
    'image/jpg': True,
    'image/png': True,
    'image/gif': True,
    'image/webp': True,
}


def is_image_processing_enabled() -> bool:
    """Check if image processing is enabled via environment variable."""
    return MODEL_RECEIVE_IMAGES


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


def get_mime_type(file_path: Path) -> str:
    """
    Determine the MIME type based on file extension.

    Args:
        file_path: Path to the file.

    Returns:
        MIME type string.
    """
    extension_to_mime = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.webp': 'image/webp',
    }
    return extension_to_mime.get(file_path.suffix.lower(), 'application/octet-stream')


def is_supported_image(mime_type: str) -> bool:
    """
    Check if the MIME type is a supported image format.

    Args:
        mime_type: MIME type string.

    Returns:
        True if supported, False otherwise.
    """
    return mime_type.lower() in SUPPORTED_IMAGE_TYPES


def read_image_as_base64(file_id: str) -> Optional[tuple[str, str]]:
    """
    Read an image file and return as base64 encoded string.

    Args:
        file_id: The file ID to read.

    Returns:
        Tuple of (base64_data, mime_type) if successful, None otherwise.
    """
    file_path = get_file_path(file_id)
    if not file_path:
        logger.warning(f"File not found: {file_id}")
        return None

    mime_type = get_mime_type(file_path)
    if not is_supported_image(mime_type):
        logger.warning(f"Unsupported image type: {mime_type}")
        return None

    try:
        with open(file_path, 'rb') as f:
            image_data = f.read()

        base64_data = base64.b64encode(image_data).decode('utf-8')
        return (base64_data, mime_type)
    except Exception as e:
        logger.error(f"Error reading image {file_id}: {e}")
        return None


def prepare_image_for_llm(file_id: str, mime_type: Optional[str] = None) -> Optional[dict]:
    """
    Prepare an image for inclusion in LLM messages.

    Args:
        file_id: The file ID of the image.
        mime_type: Optional MIME type hint.

    Returns:
        Dictionary with image content for LLM, or None if failed.
    """
    if not is_image_processing_enabled():
        return None

    result = read_image_as_base64(file_id)
    if not result:
        return None

    base64_data, detected_mime = result
    final_mime = mime_type if mime_type and is_supported_image(mime_type) else detected_mime

    return {
        'type': 'image_url',
        'image_url': {
            'url': f"data:{final_mime};base64,{base64_data}"
        }
    }


def extract_image_attachments(content: dict | str) -> list[dict]:
    """
    Extract image attachment information from message content.

    Args:
        content: Message content (JSON object or string).

    Returns:
        List of image attachment dictionaries with fileId and mimeType.
    """
    if isinstance(content, str):
        return []

    attachments = content.get('attachments', [])
    images = []

    for attachment in attachments:
        file_type = attachment.get('type', '')
        mime_type = attachment.get('mimeType', '')

        # Check if it's an image (FileType.IMAGE or image/* mime type)
        if file_type == 'image' or (mime_type and mime_type.startswith('image/')):
            images.append({
                'fileId': attachment.get('id', ''),
                'mimeType': mime_type,
                'name': attachment.get('name', 'Unknown')
            })

    return images
