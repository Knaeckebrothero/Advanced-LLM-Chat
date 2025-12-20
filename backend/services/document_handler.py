# backend/services/document_handler.py
"""
Document handling utilities for PDF, TXT, and MD files.
Handles text extraction, page rendering, and preparing documents for LLM context.
"""

import logging
from pathlib import Path
from typing import Optional

from ..config import FILES_DIR
from .file_utils import get_file_path

logger = logging.getLogger(__name__)

# Maximum number of PDF pages to process for AI context
MAX_PDF_PAGES = 20

# Supported document MIME types
SUPPORTED_DOCUMENT_TYPES = {
    'application/pdf': 'pdf',
    'text/plain': 'txt',
    'text/markdown': 'md',
}


def is_document(mime_type: str) -> bool:
    """Check if the MIME type is a supported document format."""
    return mime_type.lower() in SUPPORTED_DOCUMENT_TYPES


def get_document_type(mime_type: str) -> Optional[str]:
    """Get the document type from MIME type."""
    return SUPPORTED_DOCUMENT_TYPES.get(mime_type.lower())


def extract_pdf_text(file_path: Path) -> Optional[str]:
    """
    Extract text content from a PDF file using pdfplumber.

    Args:
        file_path: Path to the PDF file.

    Returns:
        Extracted text content or None if extraction fails.
    """
    try:
        import pdfplumber
    except ImportError:
        logger.error("pdfplumber not installed. Run: pip install pdfplumber")
        return None

    try:
        text_parts = []
        with pdfplumber.open(file_path) as pdf:
            page_count = min(len(pdf.pages), MAX_PDF_PAGES)
            for i, page in enumerate(pdf.pages[:page_count]):
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(f"--- Page {i + 1} ---\n{page_text}")

            if len(pdf.pages) > MAX_PDF_PAGES:
                text_parts.append(f"\n[Note: Document truncated. Showing {MAX_PDF_PAGES} of {len(pdf.pages)} pages]")

        return "\n\n".join(text_parts) if text_parts else None
    except Exception as e:
        logger.error(f"Error extracting text from PDF {file_path}: {e}")
        return None


def render_pdf_pages(file_path: Path, output_dir: Path, file_id: str) -> list[Path]:
    """
    Render PDF pages as PNG images.

    Args:
        file_path: Path to the PDF file.
        output_dir: Directory to save rendered images.
        file_id: File ID for naming output files.

    Returns:
        List of paths to rendered page images.
    """
    try:
        from pdf2image import convert_from_path
    except ImportError:
        logger.error("pdf2image not installed. Run: pip install pdf2image")
        return []

    try:
        # Convert PDF pages to images (limited to MAX_PDF_PAGES)
        images = convert_from_path(
            file_path,
            first_page=1,
            last_page=MAX_PDF_PAGES,
            dpi=150,  # Balance between quality and file size
            fmt='png'
        )

        output_paths = []
        for i, image in enumerate(images, start=1):
            output_path = output_dir / f"{file_id}_page_{i}.png"
            image.save(output_path, 'PNG')
            output_paths.append(output_path)
            logger.info(f"Rendered PDF page {i} to {output_path}")

        return output_paths
    except Exception as e:
        logger.error(f"Error rendering PDF pages from {file_path}: {e}")
        return []


def process_pdf(file_path: Path, file_id: str) -> dict:
    """
    Process a PDF file: extract text and render pages as images.

    Args:
        file_path: Path to the PDF file.
        file_id: File ID for naming output files.

    Returns:
        Dict with 'text_path' and 'page_paths' on success.
    """
    output_dir = file_path.parent
    result = {
        'text_path': None,
        'page_paths': [],
        'page_count': 0,
        'error': None
    }

    # Extract text
    text_content = extract_pdf_text(file_path)
    if text_content:
        text_path = output_dir / f"{file_id}_text.txt"
        try:
            with open(text_path, 'w', encoding='utf-8') as f:
                f.write(text_content)
            result['text_path'] = text_path
            logger.info(f"Saved extracted text to {text_path}")
        except Exception as e:
            logger.error(f"Error saving extracted text: {e}")
            result['error'] = str(e)

    # Render pages as images
    page_paths = render_pdf_pages(file_path, output_dir, file_id)
    result['page_paths'] = page_paths
    result['page_count'] = len(page_paths)

    return result


def read_text_file(file_path: Path) -> Optional[str]:
    """
    Read content from a text file (TXT or MD).

    Args:
        file_path: Path to the text file.

    Returns:
        File content or None if reading fails.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error reading text file {file_path}: {e}")
        return None


def get_extracted_text(file_id: str) -> Optional[str]:
    """
    Get extracted text for a document.

    For PDFs, reads from the _text.txt file.
    For TXT/MD files, reads the original file.

    Args:
        file_id: The file ID.

    Returns:
        Extracted/original text content or None.
    """
    # First, try to find the extracted text file (for PDFs)
    files_dir = Path(FILES_DIR)
    text_file_path = files_dir / f"{file_id}_text.txt"
    if text_file_path.exists():
        return read_text_file(text_file_path)

    # Otherwise, look for the original file (TXT/MD)
    original_path = get_file_path(file_id)
    if original_path and original_path.suffix.lower() in ['.txt', '.md']:
        return read_text_file(original_path)

    return None


def get_pdf_page_paths(file_id: str) -> list[Path]:
    """
    Get paths to rendered PDF page images.

    Args:
        file_id: The file ID.

    Returns:
        List of paths to page images.
    """
    files_dir = Path(FILES_DIR)
    page_paths = []
    page_num = 1

    while True:
        page_path = files_dir / f"{file_id}_page_{page_num}.png"
        if page_path.exists():
            page_paths.append(page_path)
            page_num += 1
        else:
            break

    return page_paths


def prepare_document_for_llm(
    file_id: str,
    mime_type: str,
    include_page_images: bool = True
) -> Optional[dict]:
    """
    Prepare document content for inclusion in LLM context.

    Args:
        file_id: The file ID.
        mime_type: MIME type of the document.
        include_page_images: Whether to include PDF page images (if available).

    Returns:
        Dict with 'text' and optionally 'images' list, or None if failed.
    """
    doc_type = get_document_type(mime_type)
    if not doc_type:
        return None

    result = {
        'text': None,
        'images': []
    }

    # Get text content
    text_content = get_extracted_text(file_id)
    if text_content:
        result['text'] = text_content

    # For PDFs, optionally include page images
    if doc_type == 'pdf' and include_page_images:
        page_paths = get_pdf_page_paths(file_id)
        for page_path in page_paths:
            result['images'].append({
                'path': str(page_path),
                'mime_type': 'image/png'
            })

    return result if result['text'] or result['images'] else None
