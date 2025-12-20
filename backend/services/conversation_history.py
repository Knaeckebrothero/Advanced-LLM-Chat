# backend/services/conversation_history.py
"""
Conversation history builder with placeholder support for file attachments.

Builds LLM-ready conversation history where past attachments are replaced
with descriptive placeholders, while the latest message includes full content.
"""

import json
import logging
from typing import List, Tuple, Any

from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

from ..models.attachments import (
    AttachmentPlaceholder,
    AttachmentType,
    get_attachment_type
)
from ..config import MODEL_RECEIVE_IMAGES, MODEL_RECEIVE_IMAGES_PDF
from .document_handler import get_pdf_page_paths
from .image_handler import prepare_image_for_llm, prepare_document_for_llm
from .audio_handler import prepare_audio_for_llm

logger = logging.getLogger(__name__)


class ConversationHistoryBuilder:
    """
    Builds LLM-ready conversation history with placeholder support.
    
    - Latest user message: full file content included
    - Previous messages: file content replaced with placeholders
    """

    def __init__(self, db):
        """
        Initialize the conversation history builder.
        
        Args:
            db: Database interface for retrieving messages.
        """
        self.db = db

    def _find_latest_user_message_idx(self, messages: List[dict]) -> int:
        """Find the index of the most recent user message in the list."""
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get('roleName') == 'user':
                return i
        return -1

    def _parse_content(self, content: str) -> dict:
        """Parse message content JSON string into a dict with 'content' and 'attachments'."""
        if not content:
            return {'content': '', 'attachments': []}
        
        if content.startswith('{'):
            try:
                parsed = json.loads(content)
                return {
                    'content': parsed.get('content', content),
                    'attachments': parsed.get('attachments', [])
                }
            except json.JSONDecodeError:
                pass
        
        return {'content': content, 'attachments': []}

    def _extract_text(self, msg: dict) -> str:
        """Extract plain text content from a message dict."""
        content = msg.get('content', '')
        parsed = self._parse_content(content)
        return parsed.get('content', content)

    def _create_placeholder(self, attachment: dict) -> AttachmentPlaceholder:
        """Create an AttachmentPlaceholder from attachment metadata dict."""
        file_id = attachment.get('fileId', '')
        file_name = attachment.get('name', 'Unknown')
        mime_type = attachment.get('mimeType', 'application/octet-stream')
        
        attachment_type = get_attachment_type(mime_type)
        
        # Get additional metadata
        page_count = None
        dimensions = None
        duration_seconds = None
        
        if attachment_type == AttachmentType.PDF:
            # Count PDF pages if available
            page_paths = get_pdf_page_paths(file_id)
            page_count = len(page_paths) if page_paths else None
        
        return AttachmentPlaceholder(
            file_id=file_id,
            file_name=file_name,
            mime_type=mime_type,
            attachment_type=attachment_type,
            page_count=page_count,
            dimensions=dimensions,
            duration_seconds=duration_seconds
        )

    async def _build_multimodal_content(
        self,
        text: str,
        attachments: List[dict]
    ) -> List[dict]:
        """Build LangChain-compatible multimodal content blocks with text and images."""
        content_blocks = []
        additional_text_parts = [text]
        
        for att in attachments:
            file_id = att.get('fileId', '')
            mime_type = att.get('mimeType', '')
            name = att.get('name', 'Unknown')
            
            if not file_id:
                continue
            
            if mime_type.startswith('image/'):
                if MODEL_RECEIVE_IMAGES:
                    image_content = prepare_image_for_llm(file_id, mime_type)
                    if image_content:
                        content_blocks.append(image_content)
                else:
                    additional_text_parts.append(f"\n[Image attached: {name}]")
                    
            elif mime_type == 'application/pdf':
                doc_content = prepare_document_for_llm(file_id, mime_type, name)
                if doc_content:
                    if doc_content.get('text'):
                        additional_text_parts.append(
                            f"\n\n--- Document: {name} ---\n{doc_content['text']}\n--- End ---"
                        )
                    if MODEL_RECEIVE_IMAGES_PDF:
                        for page_image in doc_content.get('images', []):
                            content_blocks.append(page_image)
                            
            elif mime_type.startswith('audio/'):
                audio_content = prepare_audio_for_llm(file_id, name)
                if audio_content and audio_content.get('text'):
                    additional_text_parts.append(
                        f"\n\n--- Audio: {name} ---\n{audio_content['text']}\n--- End ---"
                    )
        
        # Combine all text parts
        full_text = "".join(additional_text_parts)
        
        # Build final content
        if content_blocks:
            # Multimodal: text first, then images
            return [{"type": "text", "text": full_text}] + content_blocks
        else:
            # Text-only
            return full_text

    async def build_history(
        self,
        conversation_id: str,
        limit: int = 20,
        include_latest_attachments: bool = True
    ) -> Tuple[List[BaseMessage], List[AttachmentPlaceholder]]:
        """
        Build conversation history with placeholders for past attachments.

        Args:
            conversation_id: The conversation to build history for
            limit: Maximum number of messages to include
            include_latest_attachments: If True, include full content for latest user message

        Returns:
            Tuple of (messages, available_attachments)
        """
        raw_messages = self.db.get_messages_by_conversation(conversation_id, limit=limit)
        
        # Messages are returned in reverse chronological order, reverse them
        raw_messages = list(reversed(raw_messages))

        messages = []
        available_attachments = []
        latest_user_idx = self._find_latest_user_message_idx(raw_messages)

        for idx, msg in enumerate(raw_messages):
            is_latest_user = (idx == latest_user_idx)

            if msg.get('roleName') == 'user':
                content, attachments = await self._process_user_message(
                    msg,
                    include_full_content=is_latest_user and include_latest_attachments
                )
                messages.append(HumanMessage(content=content))
                available_attachments.extend(attachments)
            else:
                # AI/assistant message - extract text only
                text = self._extract_text(msg)
                messages.append(AIMessage(content=text))

        return messages, available_attachments

    async def _process_user_message(
        self,
        msg: dict,
        include_full_content: bool
    ) -> Tuple[Any, List[AttachmentPlaceholder]]:
        """Process a user message, optionally including full attachment content."""
        content_obj = self._parse_content(msg.get('content', ''))
        text = content_obj.get('content', '')
        attachments = content_obj.get('attachments', [])

        if not attachments:
            return text, []

        placeholders = [self._create_placeholder(att) for att in attachments]

        if include_full_content:
            # Build multimodal content with actual files
            content = await self._build_multimodal_content(text, attachments)
            return content, placeholders
        else:
            # Build text content with placeholders
            placeholder_text = "\n".join([p.to_placeholder_string() for p in placeholders])
            return f"{text}\n\n{placeholder_text}", placeholders
