# backend/services/vision_helper.py
"""
Vision Helper service for image and document analysis.

Used when the primary model is text-only and we need to analyze
images or visual content from documents.
"""

import os
import logging
import base64
from typing import Optional, Union

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Lazy-loaded singleton
_vision_helper: Optional["VisionHelper"] = None


def get_vision_helper() -> "VisionHelper":
    """Get or create the VisionHelper singleton instance."""
    global _vision_helper
    if _vision_helper is None:
        _vision_helper = VisionHelper()
    return _vision_helper


class VisionHelper:
    """
    Helper service for vision tasks using the dedicated vision model.

    Used when the primary model is text-only and we need to analyze
    images or visual content from documents.
    """

    def __init__(self):
        """Initialize the Vision Helper with configuration from environment."""
        # Load vision-specific config (separate from primary LLM)
        # This allows using a different provider for vision tasks (e.g., OpenAI gpt-4o)
        # while the primary agent uses a text-only model on a custom deployment
        primary_key = os.getenv("OPENAI_API_KEY", "")
        primary_base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

        # Vision-specific overrides (fall back to primary OpenAI config)
        from ..config import VISION_BASE_URL, VISION_MODEL, VISION_TIMEOUT

        self.api_key = os.getenv("VISION_API_KEY", primary_key)
        self.api_base = os.getenv("VISION_BASE_URL", VISION_BASE_URL)
        self.model = VISION_MODEL
        self.timeout = VISION_TIMEOUT

        if not self.api_key:
            logger.warning("No VISION_API_KEY or OPENAI_API_KEY configured - vision tasks will fail")

        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.api_base,
            timeout=self.timeout
        )

        # Log configuration (hiding API key)
        key_source = "VISION_API_KEY" if os.getenv("VISION_API_KEY") else "OPENAI_API_KEY"
        base_source = "VISION_BASE_URL" if os.getenv("VISION_BASE_URL") else "OPENAI_BASE_URL"
        logger.info(f"VisionHelper initialized: model={self.model}, base_url={self.api_base} (from {base_source}), timeout={self.timeout}s, api_key from {key_source}")

    async def describe_image(
        self,
        image_data: Union[bytes, str],
        mime_type: str = "image/jpeg",
        prompt: Optional[str] = None
    ) -> str:
        """
        Generate a description of an image.

        Args:
            image_data: Base64-encoded image string or raw bytes
            mime_type: MIME type of the image (e.g., "image/jpeg", "image/png")
            prompt: Optional specific question about the image

        Returns:
            Text description of the image
        """
        if isinstance(image_data, bytes):
            image_data = base64.b64encode(image_data).decode("utf-8")

        default_prompt = (
            "Describe this image in detail, including all visible text, "
            "objects, colors, layout, and any other relevant information."
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt or default_prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{image_data}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=1000
            )

            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error in describe_image: {e}", exc_info=True)
            return f"[Error analyzing image: {str(e)}]"

    async def analyze_document_page(
        self,
        page_image: Union[bytes, str],
        mime_type: str = "image/png",
        query: Optional[str] = None
    ) -> str:
        """
        Analyze a document page image (e.g., rendered PDF page).

        Args:
            page_image: Base64-encoded page image or raw bytes
            mime_type: MIME type of the image (default: "image/png" for PDF pages)
            query: Optional specific question about the page

        Returns:
            Analysis or answer to the query
        """
        if isinstance(page_image, bytes):
            page_image = base64.b64encode(page_image).decode("utf-8")

        default_prompt = (
            "Analyze this document page. Extract and describe:\n"
            "1. All text content\n"
            "2. Any tables or structured data\n"
            "3. Charts, graphs, or images\n"
            "4. Overall layout and structure"
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": query or default_prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{page_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=2000
            )

            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error in analyze_document_page: {e}", exc_info=True)
            return f"[Error analyzing document page: {str(e)}]"
