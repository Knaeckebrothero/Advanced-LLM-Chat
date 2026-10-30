# backend/services/conversation_history.py
"""
Conversation history builder with placeholder support for file attachments.

Builds LLM-ready conversation history in the OpenAI Chat Completions message
format (see backend/llm). Past attachments are replaced with descriptive
placeholders, while the latest user message includes the full content.
"""

import json
import logging
from typing import List, Optional, Tuple, Union

from ..models.attachments import (
    AttachmentPlaceholder,
    AttachmentType,
    get_attachment_type
)
from .document_handler import get_pdf_page_paths
from .image_handler import (
    prepare_image_for_llm,
    prepare_document_for_llm,
    is_document,
    is_pdf_page_images_enabled
)
from .audio_handler import prepare_audio_for_llm

logger = logging.getLogger(__name__)


class ConversationHistoryBuilder:
    """
    Builds LLM-ready conversation history with placeholder support.

    - Latest user message: full file content included (images only for vision models)
    - Previous messages: file content replaced with placeholders
    """

    def __init__(self, db):
        """
        Initialize the conversation history builder.

        Args:
            db: Database interface for retrieving messages.
        """
        self.db = db
        logger.debug("ConversationHistoryBuilder initialized")

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
        file_id = attachment.get('fileId', attachment.get('id', ''))
        file_name = attachment.get('name', attachment.get('fileName', 'Unknown'))
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
        attachments: List[dict],
        supports_vision: bool
    ) -> Union[str, List[dict]]:
        """
        Build the content of the latest user message with its attachments.

        Documents and audio transcripts are added as text. Images (and PDF page
        images with MODEL_RECEIVE_IMAGES_PDF) become image_url parts for vision
        models; text-only models get the attachment placeholder instead, so they
        can call get_file_content. Returns a string when there are no images.
        """
        logger.debug(f"Building multimodal content with {len(attachments)} attachments (vision={supports_vision})")
        image_parts = []
        text_parts = [text]
        include_page_images = supports_vision and is_pdf_page_images_enabled()

        for att in attachments:
            file_id = att.get('fileId', att.get('id', ''))
            mime_type = att.get('mimeType', '')
            name = att.get('name', att.get('fileName', 'Unknown'))

            if not file_id:
                continue

            loaded = False
            if mime_type.startswith('image/'):
                if supports_vision:
                    image_content = prepare_image_for_llm(file_id, mime_type)
                    if image_content:
                        image_parts.append(image_content)
                        loaded = True

            elif mime_type == 'application/pdf' or is_document(mime_type):
                doc_content = prepare_document_for_llm(file_id, mime_type, name, include_page_images)
                if doc_content:
                    if doc_content.get('text'):
                        text_parts.append(
                            f"\n\n--- Document: {name} ---\n{doc_content['text']}\n--- End ---"
                        )
                    image_parts.extend(doc_content.get('images', []))
                    loaded = True

            elif mime_type.startswith('audio/'):
                audio_content = prepare_audio_for_llm(file_id, name)
                if audio_content and audio_content.get('text'):
                    text_parts.append(
                        f"\n\n--- Audio: {name} ---\n{audio_content['text']}\n--- End ---"
                    )
                    loaded = True

            if not loaded:
                # Not sent as content: the placeholder tells the model to use get_file_content
                text_parts.append(f"\n\n{self._create_placeholder(att).to_placeholder_string()}")
                logger.debug(f"Attachment {name} ({file_id}) sent as placeholder")

        full_text = "".join(text_parts)

        if image_parts:
            # Multimodal: text first, then images
            parts = [{"type": "text", "text": full_text}] if full_text.strip() else []
            return parts + image_parts
        return full_text

    async def build_history(
        self,
        conversation_id: str,
        limit: int = 20,
        include_latest_attachments: bool = True,
        supports_vision: bool = False,
        before_message: Optional[dict] = None
    ) -> Tuple[List[dict], List[AttachmentPlaceholder]]:
        """
        Build conversation history with placeholders for past attachments.

        Args:
            conversation_id: The conversation to build history for
            limit: Maximum number of messages to include
            include_latest_attachments: If True, include full content for latest user message
            supports_vision: Whether the model accepts images (ModelConfig.supports_vision)
            before_message: Only include messages before this one (a message row, when regenerating it)

        Returns:
            Tuple of (messages in the OpenAI message format, available_attachments)
        """
        before_timestamp = None
        if before_message is not None:
            # Times have second resolution, so the question and its answer often share one;
            # fetch that second too and cut at the message id (a millisecond timestamp)
            before_timestamp = before_message['time'] + 1
        raw_messages = self.db.get_messages_by_conversation(
            conversation_id,
            before_timestamp=before_timestamp,
            limit=limit + 1 if before_message is not None else limit
        )
        if before_message is not None:
            raw_messages = [msg for msg in raw_messages if msg['id'] < before_message['id']][:limit]

        # Chronological order. Times have second resolution, so a question and its answer
        # often tie; the id (a millisecond timestamp) breaks the tie.
        raw_messages = sorted(raw_messages, key=lambda msg: (msg.get('time') or 0, msg.get('id') or 0))
        logger.debug(f"Building history for conversation {conversation_id}: {len(raw_messages)} messages")

        messages = []
        available_attachments = []
        latest_user_idx = self._find_latest_user_message_idx(raw_messages)

        for idx, msg in enumerate(raw_messages):
            is_latest_user = (idx == latest_user_idx)

            if msg.get('roleName') == 'user':
                content, attachments = await self._process_user_message(
                    msg,
                    include_full_content=is_latest_user and include_latest_attachments,
                    supports_vision=supports_vision
                )
                messages.append({"role": "user", "content": content})
                available_attachments.extend(attachments)
            else:
                # AI/assistant message - extract text only; skip empty ones (failed answers)
                text = self._extract_text(msg)
                if text and text.strip():
                    messages.append({"role": "assistant", "content": text})

        logger.debug(f"Built history: {len(messages)} messages, {len(available_attachments)} attachments")
        return messages, available_attachments

    async def _process_user_message(
        self,
        msg: dict,
        include_full_content: bool,
        supports_vision: bool = False
    ) -> Tuple[Union[str, List[dict]], List[AttachmentPlaceholder]]:
        """Process a user message, optionally including full attachment content."""
        content_obj = self._parse_content(msg.get('content', ''))
        text = content_obj.get('content', '')
        attachments = content_obj.get('attachments', [])

        if not attachments:
            return text, []

        placeholders = [self._create_placeholder(att) for att in attachments]

        if include_full_content:
            # Build multimodal content with actual files
            content = await self._build_multimodal_content(text, attachments, supports_vision)
            return content, placeholders
        else:
            # Build text content with placeholders
            placeholder_text = "\n".join([p.to_placeholder_string() for p in placeholders])
            return f"{text}\n\n{placeholder_text}", placeholders
