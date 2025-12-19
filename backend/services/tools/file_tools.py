# backend/services/tools/file_tools.py
"""
File retrieval tool for the LangGraph agent.
Allows the agent to retrieve content from files shared earlier in the conversation.
"""

import logging
from typing import Optional, List

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
async def get_file_content(
    file_id: str,
    query: Optional[str] = None,
    pages: Optional[List[int]] = None
) -> str:
    """
    Retrieve content from a previously shared file in this conversation.

    Use this tool when you need to:
    - Answer questions about files shared earlier in the conversation
    - Look up specific information from a document
    - Analyze images that were shared previously

    The tool always returns text content:
    - For text files: Returns the file content directly
    - For images: Returns a visual description (cached, or generated on demand)
    - For PDFs: Returns extracted text plus visual descriptions of pages
    - For audio: Returns the transcript

    Use the 'query' parameter to ask specific questions about visual content.
    This passes your question to a vision model for targeted analysis.

    Args:
        file_id: The file identifier shown in the attachment placeholder (e.g., "abc123")
        query: Optional question about the file (e.g., "What is the total revenue?")
               For images/PDFs, this enables targeted visual analysis.
        pages: For PDFs, specific pages to retrieve as a list (e.g., [1, 3, 5])

    Returns:
        File content as text. For images and PDFs, includes extracted text
        and/or visual descriptions.
    """
    from ..file_retrieval_service import get_file_retrieval_service

    logger.info(f"get_file_content called: file_id={file_id}, query={query}, pages={pages}")

    service = get_file_retrieval_service()
    # Always force text mode - tools return strings, not raw images
    result = await service.get_content(
        file_id=file_id,
        query=query,
        pages=pages,
        model_receives_images=False  # Force text descriptions for tool output
    )
    
    if result.error:
        logger.warning(f"File retrieval error for {file_id}: {result.error}")
        return f"[Error: {result.error}]"
    
    # Build response - always text since we force model_receives_images=False
    response_parts = []

    if result.text:
        response_parts.append(result.text)

    # Add visual description if different from main text (e.g., for PDFs with both)
    if result.description and result.description != result.text:
        response_parts.append(f"\n[Visual Description]\n{result.description}")
    
    if not response_parts:
        return "[No content found for this file]"
    
    return "\n".join(response_parts)
