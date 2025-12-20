# backend/services/image_handler.py
"""
Image and document handling utilities for AI integration.
Handles reading, encoding, and preparing images/documents for vision-capable LLMs.
"""

import base64
import logging
from pathlib import Path
from typing import Optional

from ..config import FILES_DIR, MODEL_RECEIVE_IMAGES, MODEL_RECEIVE_IMAGES_PDF
from .file_utils import get_file_path, SUPPORTED_AUDIO_TYPES, is_audio

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

    logger.debug(f"Extracting images from {len(attachments)} attachments")

    for attachment in attachments:
        # Frontend sends 'mimeType', check for image/* MIME types
        mime_type = attachment.get('mimeType', '')

        logger.debug(f"Attachment: {attachment}")

        # Check if it's an image based on MIME type
        if mime_type and mime_type.startswith('image/'):
            # Frontend sends 'fileId' and 'fileName', not 'id' and 'name'
            file_id = attachment.get('fileId', attachment.get('id', ''))
            name = attachment.get('fileName', attachment.get('name', 'Unknown'))
            logger.info(f"Found image attachment: fileId={file_id}, mimeType={mime_type}, name={name}")
            images.append({
                'fileId': file_id,
                'mimeType': mime_type,
                'name': name
            })

    return images


# Document handling functions

SUPPORTED_DOCUMENT_TYPES = {
    'application/pdf': 'pdf',
    'text/plain': 'txt',
    'text/markdown': 'md',
}


def is_pdf_page_images_enabled() -> bool:
    """Check if PDF page images should be sent to the model."""
    return MODEL_RECEIVE_IMAGES_PDF and MODEL_RECEIVE_IMAGES


def is_document(mime_type: str) -> bool:
    """Check if the MIME type is a supported document format."""
    return mime_type.lower() in SUPPORTED_DOCUMENT_TYPES


def extract_document_attachments(content: dict | str) -> list[dict]:
    """
    Extract document attachment information from message content.

    Args:
        content: Message content (JSON object or string).

    Returns:
        List of document attachment dictionaries with fileId, mimeType, and name.
    """
    if isinstance(content, str):
        return []

    attachments = content.get('attachments', [])
    documents = []

    logger.debug(f"Extracting documents from {len(attachments)} attachments")

    for attachment in attachments:
        mime_type = attachment.get('mimeType', '')

        # Check if it's a document based on MIME type
        if is_document(mime_type):
            # Frontend sends 'fileId' and 'fileName', not 'id' and 'name'
            file_id = attachment.get('fileId', attachment.get('id', ''))
            name = attachment.get('fileName', attachment.get('name', 'Unknown'))
            logger.info(f"Found document attachment: fileId={file_id}, mimeType={mime_type}, name={name}")
            documents.append({
                'fileId': file_id,
                'mimeType': mime_type,
                'name': name
            })

    return documents


def prepare_document_for_llm(file_id: str, mime_type: str, name: str) -> Optional[dict]:
    """
    Prepare document content for inclusion in LLM messages.

    Args:
        file_id: The file ID of the document.
        mime_type: MIME type of the document.
        name: Filename for context.

    Returns:
        Dictionary with text content and optionally images, or None if failed.
    """
    from .document_handler import get_extracted_text, get_pdf_page_paths

    result = {
        'text': None,
        'images': [],
        'name': name
    }

    # Get text content
    text_content = get_extracted_text(file_id)
    if text_content:
        result['text'] = text_content

    # For PDFs, optionally include page images
    if mime_type.lower() == 'application/pdf' and is_pdf_page_images_enabled():
        page_paths = get_pdf_page_paths(file_id)
        for page_path in page_paths:
            try:
                with open(page_path, 'rb') as f:
                    image_data = f.read()
                base64_data = base64.b64encode(image_data).decode('utf-8')
                result['images'].append({
                    'type': 'image_url',
                    'image_url': {
                        'url': f"data:image/png;base64,{base64_data}"
                    }
                })
            except Exception as e:
                logger.warning(f"Failed to load PDF page image {page_path}: {e}")

    return result if result['text'] or result['images'] else None


# Audio handling functions (SUPPORTED_AUDIO_TYPES and is_audio imported from file_utils)


def extract_audio_attachments(content: dict | str) -> list[dict]:
    """
    Extract audio attachment information from message content.

    Args:
        content: Message content (JSON object or string).

    Returns:
        List of audio attachment dictionaries with fileId, mimeType, and name.
    """
    if isinstance(content, str):
        return []

    attachments = content.get('attachments', [])
    audio_files = []

    for attachment in attachments:
        mime_type = attachment.get('mimeType', '')

        # Check if it's an audio file based on MIME type
        if is_audio(mime_type):
            # Frontend sends 'fileId' and 'fileName', not 'id' and 'name'
            audio_files.append({
                'fileId': attachment.get('fileId', attachment.get('id', '')),
                'mimeType': mime_type,
                'name': attachment.get('fileName', attachment.get('name', 'Unknown'))
            })

    return audio_files


def prepare_audio_for_llm(file_id: str, name: str) -> Optional[dict]:
    """
    Prepare audio content for inclusion in LLM messages.

    For audio files, we pass the transcript as text to the LLM.

    Args:
        file_id: The file ID of the audio.
        name: Filename for context.

    Returns:
        Dictionary with transcript text, or None if no transcript available.
    """
    from .audio_handler import get_transcript

    transcript = get_transcript(file_id)
    if not transcript:
        return None

    return {
        'text': transcript,
        'name': name,
        'type': 'audio_transcript'
    }
