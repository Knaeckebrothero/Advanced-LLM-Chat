"""
File upload and retrieval API endpoints.
"""
import logging
import secrets
import time
from typing import List, Optional
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel
from backend.models.common import ErrorResponse
from backend.security.auth import get_current_user
from backend.services.document_handler import process_pdf, get_extracted_text
from backend.services.audio_handler import is_audio, process_audio, get_transcript
from backend.config import FILES_DIR as FILES_DIR_STR

router = APIRouter(prefix="/api/files", tags=["Files"])
logger = logging.getLogger(__name__)

# Directory where files are stored (from config, converted to Path)
FILES_DIR = Path(FILES_DIR_STR)

# MIME types that trigger document processing
PDF_MIME_TYPES = {'application/pdf'}


class UploadedFileResponse(BaseModel):
    """Response model for a single uploaded file."""
    fileId: str
    transcript: Optional[str] = None


@router.post("/upload",
             response_model=List[UploadedFileResponse],
             status_code=status.HTTP_201_CREATED,
             responses={
                 status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "No files provided"},
                 # status.HTTP_413_PAYLOAD_TOO_LARGE: {"model": ErrorResponse, "description": "File too large"},
                 # Does not work with the current version of starlette, use ENTITY_TOO_LARGE instead
                 status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: {"model": ErrorResponse, "description": "File too large"},
                 status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Internal server error"}
             })
async def upload_files(
        files: List[UploadFile] = File(...),
        current_user: dict = Depends(get_current_user)
):
    """
    Handles the upload of multiple files via a POST request. This endpoint validates
    the files against a maximum allowed size, generates unique IDs for the files,
    and saves them to a local directory.

    For audio files, transcription is automatically performed using Whisper and
    the transcript is included in the response.

    :param files: The list of files to be uploaded
    :type files: List[UploadFile]
    :param current_user: The currently authenticated user making the request
    :type current_user: dict
    :return: A list of uploaded file responses with fileId and optional transcript
    :rtype: List[UploadedFileResponse]
    :raises HTTPException: Raised on validation errors like missing files, files
        exceeding the size limit, or on internal server errors
    """
    logger.info(f"File upload called with {len(files)} files")

    try:
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")

        uploaded_files = []
        max_file_size = 10 * 1024 * 1024  # 10MB limit per file

        # Ensure files directory exists (including parent directories)
        FILES_DIR.mkdir(parents=True, exist_ok=True)

        for file in files:
            # Read file to check size and content
            contents = await file.read()
            if len(contents) > max_file_size:
                raise HTTPException(status_code=413, detail=f"File {file.filename} exceeds maximum size of 10MB")

            # Generate a unique file ID and preserve original extension
            timestamp = int(time.time() * 1000)
            random_suffix = secrets.token_hex(8)
            file_id = f"file_{timestamp}_{random_suffix}"

            # Preserve file extension if present
            if file.filename and "." in file.filename:
                original_ext = Path(file.filename).suffix
                stored_filename = f"{file_id}{original_ext}"
            else:
                stored_filename = file_id

            # Save file to disk
            file_path = FILES_DIR / stored_filename
            with open(file_path, "wb") as f:
                f.write(contents)

            logger.info(f"Uploaded file: {file.filename} -> {file_id} (size: {len(contents)} bytes) saved to {file_path}")

            # Initialize response for this file
            file_response = UploadedFileResponse(fileId=file_id)

            # Process PDFs to extract text and render pages
            if file.content_type in PDF_MIME_TYPES:
                logger.info(f"Processing PDF: {file_id}")
                try:
                    result = process_pdf(file_path, file_id)
                    if result.get('error'):
                        logger.warning(f"PDF processing had errors: {result['error']}")
                    else:
                        logger.info(f"PDF processed: {result['page_count']} pages extracted")
                except Exception as e:
                    logger.error(f"Error processing PDF {file_id}: {e}")
                    # Continue - file is uploaded, just not processed

            # Process audio files to transcribe
            elif is_audio(file.content_type):
                logger.info(f"Processing audio file: {file_id}")
                try:
                    result = await process_audio(file_path, file_id)
                    if result.get('transcript'):
                        file_response.transcript = result['transcript']
                        logger.info(f"Audio transcribed: {len(result['transcript'])} characters")
                    elif result.get('error'):
                        logger.warning(f"Audio transcription had errors: {result['error']}")
                except Exception as e:
                    logger.error(f"Error processing audio {file_id}: {e}")
                    # Continue - file is uploaded, just not transcribed

            uploaded_files.append(file_response)

            # Reset file position (not needed after saving, but good practice)
            await file.seek(0)

        return uploaded_files

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading files: {str(e)}")
        raise HTTPException(status_code=500, detail="Error uploading files")


def _find_file_by_id(file_id: str) -> Path | None:
    """
    Find a file in the files directory by its ID (without extension).
    Returns the full path if found, None otherwise.
    """
    if not FILES_DIR.exists():
        return None

    # Search for files matching the fileId with any extension
    for file_path in FILES_DIR.iterdir():
        if file_path.is_file() and file_path.stem == file_id:
            return file_path

    return None


def _get_media_type(file_path: Path) -> str:
    """
    Determine the media type based on file extension.
    """
    extension_to_media_type = {
        # Images
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.webp': 'image/webp',
        '.svg': 'image/svg+xml',
        # Documents
        '.pdf': 'application/pdf',
        '.txt': 'text/plain',
        '.md': 'text/markdown',
        '.json': 'application/json',
        # Audio
        '.mp3': 'audio/mpeg',
        '.wav': 'audio/wav',
        '.ogg': 'audio/ogg',
        '.webm': 'audio/webm',
        '.m4a': 'audio/mp4',
        # Fallback
    }
    return extension_to_media_type.get(file_path.suffix.lower(), 'application/octet-stream')


@router.get("/{file_id}",
            responses={
                status.HTTP_200_OK: {"description": "File content"},
                status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse, "description": "Not authenticated"},
                status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "File not found"}
            })
async def get_file(
        file_id: str,
        current_user: dict = Depends(get_current_user)
):
    """
    Retrieves a file by its ID.

    Looks up the file in the files directory and returns it with the appropriate
    Content-Type header based on the file extension.

    :param file_id: The unique identifier of the file (without extension)
    :type file_id: str
    :param current_user: The currently authenticated user making the request
    :type current_user: dict
    :return: The file content with appropriate Content-Type header
    :raises HTTPException: 404 if file not found, 401 if not authenticated
    """
    file_path = _find_file_by_id(file_id)

    if file_path is None:
        raise HTTPException(status_code=404, detail="File not found")

    media_type = _get_media_type(file_path)

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=file_path.name
    )


@router.get("/{file_id}/text",
            response_class=PlainTextResponse,
            responses={
                status.HTTP_200_OK: {"description": "Extracted text content or transcript"},
                status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse, "description": "Not authenticated"},
                status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "File or text not found"}
            })
async def get_file_text(
        file_id: str,
        current_user: dict = Depends(get_current_user)
):
    """
    Retrieves extracted text content for a document or transcript for audio.

    For PDFs, returns the extracted text from the _text.txt file.
    For TXT/MD files, returns the original file content.
    For audio files, returns the transcript from the _transcript.txt file.

    :param file_id: The unique identifier of the file (without extension)
    :type file_id: str
    :param current_user: The currently authenticated user making the request
    :type current_user: dict
    :return: The extracted text content or audio transcript
    :rtype: str
    :raises HTTPException: 404 if file or text not found, 401 if not authenticated
    """
    # First check if the original file exists
    file_path = _find_file_by_id(file_id)
    if file_path is None:
        raise HTTPException(status_code=404, detail="File not found")

    # Try to get document text first
    text_content = get_extracted_text(file_id)

    # If no document text, try to get audio transcript
    if text_content is None:
        text_content = get_transcript(file_id)

    if text_content is None:
        raise HTTPException(
            status_code=404,
            detail="No text content available for this file"
        )

    return PlainTextResponse(content=text_content, media_type="text/plain; charset=utf-8")


@router.delete("/{file_id}",
               status_code=status.HTTP_204_NO_CONTENT,
               responses={
                   status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse, "description": "Not authenticated"},
                   status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "File not found"}
               })
async def delete_file(
        file_id: str,
        current_user: dict = Depends(get_current_user)
):
    """
    Delete a file and its associated data.

    Removes the original file, any extracted text/page images,
    and clears the description cache.

    :param file_id: The unique identifier of the file (without extension)
    :type file_id: str
    :param current_user: The currently authenticated user making the request
    :type current_user: dict
    :raises HTTPException: 404 if file not found, 401 if not authenticated
    """
    import shutil

    file_path = _find_file_by_id(file_id)
    if file_path is None:
        raise HTTPException(status_code=404, detail="File not found")

    try:
        # Delete the main file
        file_path.unlink()
        logger.info(f"Deleted file: {file_path}")

        # Delete associated files (extracted text, page images, transcripts)
        associated_files = list(FILES_DIR.glob(f"{file_id}_*"))
        for assoc_file in associated_files:
            if assoc_file.is_file():
                assoc_file.unlink()
                logger.debug(f"Deleted associated file: {assoc_file}")
            elif assoc_file.is_dir():
                shutil.rmtree(assoc_file)
                logger.debug(f"Deleted associated directory: {assoc_file}")

        # Clear the description cache for this file
        try:
            from backend.services.cache.description_cache import get_description_cache
            cache = get_description_cache()
            await cache.delete_by_file(file_id)
        except Exception as e:
            logger.warning(f"Failed to clear cache for {file_id}: {e}")

    except Exception as e:
        logger.error(f"Error deleting file {file_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete file: {str(e)}"
        )
