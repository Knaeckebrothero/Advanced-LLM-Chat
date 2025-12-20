# backend/services/file_retrieval_service.py
"""
Service for retrieving and processing file content on-demand.

Uses existing document_handler.py and audio_handler.py for file processing,
and Vision Helper for image analysis when the primary model is text-only.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List

from ..config import MODEL_RECEIVE_IMAGES
from .document_handler import (
    get_file_path,
    get_extracted_text,
    get_pdf_page_paths,
)
from .audio_handler import get_transcript

logger = logging.getLogger(__name__)


@dataclass
class FileContentResult:
    """Result from file content retrieval."""
    text: Optional[str] = None
    images: Optional[List[bytes]] = None
    description: Optional[str] = None
    error: Optional[str] = None


class FileRetrievalService:
    """
    Service for retrieving and processing file content on-demand.

    Uses the Vision Helper LLM for image analysis when the primary model
    is text-only or when a specific query needs visual analysis.

    Leverages existing document_handler.py for PDF text extraction and
    page rendering (already stores extracted text and page images on upload).
    """

    def __init__(self, description_cache=None):
        """
        Initialize the file retrieval service.
        
        Args:
            description_cache: Optional cache for storing generated descriptions.
        """
        self.description_cache = description_cache

    async def get_content(
        self,
        file_id: str,
        query: Optional[str] = None,
        pages: Optional[List[int]] = None,
        model_receives_images: Optional[bool] = None
    ) -> FileContentResult:
        """
        Retrieve file content, adapting output based on model capabilities.

        Args:
            file_id: The unique identifier of the file
            query: Optional question to ask about the file
            pages: For PDFs, specific pages to retrieve (1-indexed)
            model_receives_images: Override for model capability check.
                If None, uses MODEL_RECEIVE_IMAGES config.
                
        Returns:
            FileContentResult with text, images, or description.
        """
        if model_receives_images is None:
            model_receives_images = MODEL_RECEIVE_IMAGES

        file_path = get_file_path(file_id)
        if not file_path:
            logger.warning(f"File not found: {file_id}")
            return FileContentResult(
                error=f"File '{file_id}' not found or has been deleted"
            )

        try:
            mime_type = self._get_mime_type(file_path)

            if mime_type.startswith("image/"):
                return await self._handle_image(
                    file_id, file_path, mime_type, query, model_receives_images
                )
            elif mime_type == "application/pdf":
                return await self._handle_pdf(
                    file_id, file_path, query, pages, model_receives_images
                )
            elif mime_type.startswith("audio/"):
                return await self._handle_audio(file_id)
            else:
                return await self._handle_generic(file_path)
        except Exception as e:
            logger.error(f"Error retrieving file {file_id}: {e}", exc_info=True)
            return FileContentResult(
                error=f"Could not retrieve file content: {str(e)}"
            )

    def _get_mime_type(self, file_path: Path) -> str:
        """Determine MIME type from file extension."""
        extension_map = {
            '.pdf': 'application/pdf',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.mp3': 'audio/mpeg',
            '.wav': 'audio/wav',
            '.m4a': 'audio/mp4',
            '.ogg': 'audio/ogg',
            '.webm': 'audio/webm',
            '.txt': 'text/plain',
            '.md': 'text/markdown',
        }
        suffix = file_path.suffix.lower()
        return extension_map.get(suffix, 'application/octet-stream')

    async def _handle_image(
        self,
        file_id: str,
        file_path: Path,
        mime_type: str,
        query: Optional[str],
        model_receives_images: bool
    ) -> FileContentResult:
        """Process image file request."""
        if model_receives_images and not query:
            # Return actual image bytes for multimodal model
            try:
                image_data = file_path.read_bytes()
                return FileContentResult(images=[image_data])
            except Exception as e:
                logger.error(f"Error reading image {file_path}: {e}")
                return FileContentResult(error=f"Could not read image: {str(e)}")
        else:
            # Use Vision Helper to analyze the image
            description = await self._get_image_description(
                file_id, file_path, mime_type, query
            )
            return FileContentResult(text=description, description=description)

    async def _handle_pdf(
        self,
        file_id: str,
        file_path: Path,
        query: Optional[str],
        pages: Optional[List[int]],
        model_receives_images: bool
    ) -> FileContentResult:
        """Process PDF file request."""
        # Get pre-extracted text (from document_handler on upload)
        extracted_text = get_extracted_text(file_id)

        if model_receives_images and not query:
            # Return text + pre-rendered page images for multimodal model
            page_images = self._load_pdf_page_images(file_id, pages)
            return FileContentResult(text=extracted_text, images=page_images)
        elif query:
            # Use Vision Helper to answer specific query about the PDF
            answer = await self._answer_pdf_query(file_id, query, pages)
            return FileContentResult(text=answer)
        else:
            # Text-only model, no query: return extracted text + visual descriptions
            descriptions = await self._get_pdf_page_descriptions(file_id, pages)
            combined_text = extracted_text or ""
            if descriptions:
                combined_text += f"\n\n--- Visual Descriptions ---\n{descriptions}"
            return FileContentResult(text=combined_text, description=descriptions)

    def _load_pdf_page_images(
        self, file_id: str, pages: Optional[List[int]] = None
    ) -> List[bytes]:
        """Load pre-rendered PDF page images from disk."""
        page_paths = get_pdf_page_paths(file_id)
        if pages:
            # Filter to requested pages (1-indexed)
            page_paths = [p for i, p in enumerate(page_paths, 1) if i in pages]
        
        images = []
        for page_path in page_paths:
            try:
                images.append(page_path.read_bytes())
            except Exception as e:
                logger.warning(f"Could not read page image {page_path}: {e}")
        return images

    async def _get_image_description(
        self,
        file_id: str,
        file_path: Path,
        mime_type: str,
        query: Optional[str] = None
    ) -> str:
        """Get or generate image description using Vision Helper."""
        # Check cache first
        if self.description_cache:
            cached = await self.description_cache.get(file_id, query)
            if cached:
                logger.info(f"Using cached description for {file_id}")
                return cached

        # Use Vision Helper LLM to analyze the image
        try:
            from .vision_helper import get_vision_helper
            vision_helper = get_vision_helper()
            image_data = file_path.read_bytes()
            description = await vision_helper.describe_image(
                image_data=image_data,
                mime_type=mime_type,
                prompt=query
            )

            # Store in cache
            if self.description_cache:
                await self.description_cache.set(file_id, description, query)

            return description
        except Exception as e:
            logger.error(f"Error getting image description: {e}", exc_info=True)
            return f"[Could not analyze image: {str(e)}]"

    async def _answer_pdf_query(
        self,
        file_id: str,
        query: str,
        pages: Optional[List[int]] = None
    ) -> str:
        """Answer a specific query about a PDF using Vision Helper."""
        page_images = self._load_pdf_page_images(file_id, pages)
        page_paths = get_pdf_page_paths(file_id)
        
        if pages:
            page_nums = pages
        else:
            page_nums = list(range(1, len(page_paths) + 1))

        if not page_images:
            # Fall back to text extraction if no images available
            extracted_text = get_extracted_text(file_id)
            if extracted_text:
                return f"[Based on extracted text]\n{extracted_text}"
            return "[No content available for this PDF]"

        try:
            from .vision_helper import get_vision_helper
            vision_helper = get_vision_helper()
            answers = []
            
            for page_num, page_image in zip(page_nums, page_images):
                answer = await vision_helper.analyze_document_page(
                    page_image=page_image,
                    query=query
                )
                answers.append(f"Page {page_num}: {answer}")

            return "\n\n".join(answers)
        except Exception as e:
            logger.error(f"Error answering PDF query: {e}", exc_info=True)
            return f"[Could not analyze PDF: {str(e)}]"

    async def _get_pdf_page_descriptions(
        self,
        file_id: str,
        pages: Optional[List[int]] = None
    ) -> str:
        """Generate descriptions for PDF pages using Vision Helper."""
        page_images = self._load_pdf_page_images(file_id, pages)
        page_paths = get_pdf_page_paths(file_id)
        
        if pages:
            page_nums = pages
        else:
            page_nums = list(range(1, len(page_paths) + 1))

        if not page_images:
            return ""

        try:
            from .vision_helper import get_vision_helper
            vision_helper = get_vision_helper()
            descriptions = []

            for page_num, page_image in zip(page_nums, page_images):
                cache_key_query = f"page_{page_num}"

                # Check cache
                if self.description_cache:
                    cached = await self.description_cache.get(file_id, cache_key_query)
                    if cached:
                        descriptions.append(f"--- Page {page_num} ---\n{cached}")
                        continue

                description = await vision_helper.analyze_document_page(
                    page_image=page_image
                )

                # Store in cache
                if self.description_cache:
                    await self.description_cache.set(file_id, description, cache_key_query)

                descriptions.append(f"--- Page {page_num} ---\n{description}")

            return "\n\n".join(descriptions)
        except Exception as e:
            logger.error(f"Error generating PDF descriptions: {e}", exc_info=True)
            return ""

    async def _handle_audio(self, file_id: str) -> FileContentResult:
        """Handle audio file - return pre-computed transcription."""
        transcript = get_transcript(file_id)
        if transcript:
            return FileContentResult(text=transcript)
        return FileContentResult(
            text="[Audio transcription not available]",
            error="Audio transcription not available"
        )

    async def _handle_generic(self, file_path: Path) -> FileContentResult:
        """Handle generic text-based files."""
        try:
            text = file_path.read_text(encoding='utf-8')
            return FileContentResult(text=text)
        except UnicodeDecodeError:
            return FileContentResult(
                text=f"[Binary file: {file_path.name}, {file_path.stat().st_size} bytes]"
            )
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return FileContentResult(error=f"Could not read file: {str(e)}")


# Singleton instance
_file_retrieval_service: Optional[FileRetrievalService] = None


def get_file_retrieval_service() -> FileRetrievalService:
    """Get or create the FileRetrievalService singleton."""
    global _file_retrieval_service
    if _file_retrieval_service is None:
        from .cache.description_cache import get_description_cache
        cache = get_description_cache()
        _file_retrieval_service = FileRetrievalService(description_cache=cache)
    return _file_retrieval_service
