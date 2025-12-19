# backend/models/attachments.py
"""
Attachment models for file handling in conversations.
Provides placeholder generation for file attachments in conversation history.
"""

from dataclasses import dataclass
from typing import Optional
from enum import Enum


class AttachmentType(Enum):
    """Types of attachments supported in conversations."""
    IMAGE = "image"
    PDF = "pdf"
    DOCUMENT = "document"
    AUDIO = "audio"


@dataclass
class AttachmentPlaceholder:
    """
    Represents a file attachment placeholder for conversation history.
    
    Used to replace full file content with descriptive placeholders
    when building conversation history for the LLM.
    """
    file_id: str
    file_name: str
    mime_type: str
    attachment_type: AttachmentType
    size_bytes: int = 0
    # Type-specific metadata
    page_count: Optional[int] = None      # For PDFs
    dimensions: Optional[str] = None       # For images (e.g., "1920x1080")
    duration_seconds: Optional[float] = None  # For audio

    def to_placeholder_string(self) -> str:
        """Generate human-readable placeholder for conversation history."""
        parts = [f"[Attachment: {self.file_name} (fileId: {self.file_id})"]

        if self.attachment_type == AttachmentType.PDF:
            page_info = f"{self.page_count} pages" if self.page_count else "PDF"
            parts.append(f" - {page_info}, PDF document]")
        elif self.attachment_type == AttachmentType.IMAGE:
            dim_info = f", {self.dimensions}" if self.dimensions else ""
            parts.append(f" - Image{dim_info}]")
        elif self.attachment_type == AttachmentType.AUDIO:
            if self.duration_seconds:
                parts.append(f" - Audio, {self.duration_seconds:.1f}s]")
            else:
                parts.append(" - Audio]")
        else:
            parts.append(f" - {self.mime_type}]")

        return "".join(parts)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "fileId": self.file_id,
            "fileName": self.file_name,
            "mimeType": self.mime_type,
            "attachmentType": self.attachment_type.value,
            "sizeBytes": self.size_bytes,
            "pageCount": self.page_count,
            "dimensions": self.dimensions,
            "durationSeconds": self.duration_seconds
        }


def get_attachment_type(mime_type: str) -> AttachmentType:
    """Determine AttachmentType from MIME type."""
    mime_lower = mime_type.lower()
    
    if mime_lower.startswith("image/"):
        return AttachmentType.IMAGE
    elif mime_lower == "application/pdf":
        return AttachmentType.PDF
    elif mime_lower.startswith("audio/"):
        return AttachmentType.AUDIO
    else:
        return AttachmentType.DOCUMENT
