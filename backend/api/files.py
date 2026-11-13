"""
File upload and retrieval API endpoints.

Every stored file belongs to a user (table uploaded_files): the one who uploaded
it, or the one a tool created it for (docs/files.md). The other endpoints answer
404 for files of other users, as for missing files.
"""
import asyncio
import logging
from typing import List, Literal, Optional
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, status
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel
from backend.config import GUEST_FILES_MAX_MB, MAX_UPLOAD_FILES
from backend.models.common import ErrorResponse
from backend.database import db
from backend.security.auth import get_current_user, verify_file_ownership
from backend.security.guest_limits import count_guest_request
from backend.services.document_handler import process_pdf_safely, get_extracted_text
from backend.services.audio_handler import is_audio, process_audio, get_transcript
from backend.services import file_store
from backend.services.hidden_content import family_mode
from backend.services.file_utils import get_file_path, delete_stored_file, stored_bytes

router = APIRouter(prefix="/api/files", tags=["Files"])
logger = logging.getLogger(__name__)

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
                 status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "No files, or too many"},
                 # status.HTTP_413_PAYLOAD_TOO_LARGE: {"model": ErrorResponse, "description": "File too large"},
                 # Does not work with the current version of starlette, use ENTITY_TOO_LARGE instead
                 status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: {"model": ErrorResponse, "description": "File too large"},
                 status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse,
                                                     "description": "A guest has uploaded too many files"},
                 status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Internal server error"},
                 status.HTTP_507_INSUFFICIENT_STORAGE: {"model": ErrorResponse,
                                                        "description": "The guests' files take too much space"}
             })
async def upload_files(
        request: Request,
        files: List[UploadFile] = File(...),
        current_user: dict = Depends(get_current_user)
):
    """
    Handles the upload of multiple files via a POST request. This endpoint validates
    the files against a maximum allowed size, generates unique IDs for the files,
    records the current user as their owner, and saves them to a local directory.

    For audio files, transcription is automatically performed using Whisper and
    the transcript is included in the response.

    Guests' uploads are limited: each file counts against their address's limit
    (backend/security/guest_limits.py), and all guests' files together may take at
    most GUEST_FILES_MAX_MB, so visitors can't fill the volume that everyone's files
    are on. Guests' files are deleted with their session.

    :param request: The HTTP request
    :type request: Request
    :param files: The list of files to be uploaded
    :type files: List[UploadFile]
    :param current_user: The currently authenticated user making the request
    :type current_user: dict
    :return: A list of uploaded file responses with fileId and optional transcript
    :rtype: List[UploadedFileResponse]
    :raises HTTPException: Raised on validation errors like missing files, too many
        files, files exceeding the size limit, a guest over a limit, or on internal
        server errors
    """
    logger.info(f"File upload called with {len(files)} files")

    try:
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")
        if len(files) > MAX_UPLOAD_FILES:
            raise HTTPException(status_code=400, detail=f"At most {MAX_UPLOAD_FILES} files at once")
        # The size the upload declares, before anything is read into memory
        for file in files:
            if file.size is not None and file.size > file_store.MAX_FILE_SIZE:
                raise HTTPException(status_code=413, detail=f"File {file.filename} exceeds maximum size of 10MB")

        if current_user.get("is_guest"):
            await _check_guest_storage()
            count_guest_request(request, current_user, "uploads", amount=len(files))

        uploaded_files = []

        for file in files:
            # Before every file: the one before may have left a lot (a PDF's pages)
            if current_user.get("is_guest") and uploaded_files:
                await _check_guest_storage()

            # Never more in memory than a file may have
            contents = await file.read(file_store.MAX_FILE_SIZE + 1)
            if len(contents) > file_store.MAX_FILE_SIZE:
                raise HTTPException(status_code=413, detail=f"File {file.filename} exceeds maximum size of 10MB")

            # Stored under a new file ID with the original extension, recorded for the uploader. It
            # gets its conversation when the message that attaches it is stored
            stored = await asyncio.to_thread(
                file_store.store, contents, current_user['user_id'],
                name=Path(file.filename).name if file.filename else None, mime_type=file.content_type)
            file_id, file_path = stored['file_id'], stored['path']

            logger.info(f"Uploaded file: {file.filename} -> {file_id} (size: {len(contents)} bytes) saved to {file_path}")

            # Initialize response for this file
            file_response = UploadedFileResponse(fileId=file_id)

            # Process PDFs to extract text and render pages: in a process of its own with limits
            # (a PDF can be made to take any amount of time and memory), off the event loop
            if file.content_type in PDF_MIME_TYPES:
                logger.info(f"Processing PDF: {file_id}")
                try:
                    result = await asyncio.to_thread(process_pdf_safely, file_path, file_id)
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


async def _check_guest_storage() -> None:
    """
    Refuse a guest's upload while all guests' files, with what is made from them, take
    GUEST_FILES_MAX_MB or more.

    :raises HTTPException: 507 until guests' files are deleted (with their sessions).
    """
    taken = await asyncio.to_thread(lambda: stored_bytes(db.get_guest_file_ids()))
    if taken >= GUEST_FILES_MAX_MB * 1024 * 1024:
        logger.warning(f"Guests' files take {taken} bytes, over GUEST_FILES_MAX_MB={GUEST_FILES_MAX_MB}")
        raise HTTPException(status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
                            detail="Guests can't upload files right now. Please try again later.")


def _own_file_path(file_id: str, current_user: dict) -> Path:
    """
    The stored file with this ID (without extension), if the current user uploaded it.

    Files of other users are a 404 like missing files, so file IDs can't be probed.

    :raises HTTPException: 404 if the file is missing or not the user's
    """
    if not verify_file_ownership(file_id, current_user['user_id']):
        raise HTTPException(status_code=404, detail="File not found")

    file_path = get_file_path(file_id)
    if file_path is None:
        raise HTTPException(status_code=404, detail="File not found")
    return file_path


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


@router.get("",
            responses={
                status.HTTP_200_OK: {"description": "The conversation's files, oldest first"},
                status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse, "description": "Not authenticated"}
            })
async def list_conversation_files(
        conversationId: str,
        current_user: dict = Depends(get_current_user)
) -> List[dict]:
    """
    The files of a conversation, oldest first: what its messages attach and what tools created
    in it, each as {fileId, name, mimeType, size, width, height, source, origin, createdAt}
    (file_store.file_entry()). The chat finds in it the files an answer places in its text, and
    lists them under "Files of this chat" (docs/files.md, "In the chat").

    Only the user's own files: a conversation of somebody else has none, like a missing one.
    """
    rows = await asyncio.to_thread(file_store.conversation_files, conversationId, current_user['user_id'])
    return [file_store.file_entry(row) for row in rows]


@router.get("/all",
            responses={
                status.HTTP_200_OK: {"description": "The files of all the user's conversations"},
                status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse, "description": "Not authenticated"}
            })
async def list_all_files(
        offset: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=200),
        source: Optional[Literal["upload", "tool"]] = None,
        current_user: dict = Depends(get_current_user),
        hide: bool = Depends(family_mode)
) -> dict:
    """
    The files of all the user's conversations, for "All files" in the settings (docs/files.md):
    the conversations by their newest file, each conversation's files together, newest first.

    Returns {files, counts, size}: `limit` files after `offset`, each as in the list of one
    conversation with `conversationId` and `conversationName`; how many uploads and files of
    tools there are in all (`counts`, whatever `source` asks for); and the bytes they take.
    Files in no conversation (of deleted messages and conversations) are not listed, and a
    device in family mode gets none of hidden conversations.
    """
    found = await asyncio.to_thread(file_store.all_files, current_user['user_id'], source=source,
                                    family_mode=hide, limit=limit, offset=offset)
    return {"files": [file_store.file_entry(row) for row in found["files"]],
            "counts": found["counts"], "size": found["bytes"]}


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
    Content-Type header based on the file extension. Only the uploader gets it.

    :param file_id: The unique identifier of the file (without extension)
    :type file_id: str
    :param current_user: The currently authenticated user making the request
    :type current_user: dict
    :return: The file content with appropriate Content-Type header
    :raises HTTPException: 404 if file not found or not the user's, 401 if not authenticated
    """
    file_path = _own_file_path(file_id, current_user)

    media_type = _get_media_type(file_path)

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=file_path.name
    )


@router.get("/{file_id}/thumbnail",
            responses={
                status.HTTP_200_OK: {"description": "A preview of the image or the PDF's first page (WebP)"},
                status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse, "description": "Not authenticated"},
                status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "File not found, or no image or PDF"}
            })
async def get_file_thumbnail(
        file_id: str,
        size: Literal["small", "large"] = "small",
        current_user: dict = Depends(get_current_user)
):
    """
    A preview of an image, or of a PDF's first page, for the chat: at most 256 (small)
    or 1024 (large) pixels on its longer edge, as WebP. Made on the first request and
    kept with the file. Only the file's owner gets it; any other file is a 404.
    """
    _own_file_path(file_id, current_user)
    preview = await asyncio.to_thread(file_store.thumbnail, file_id, size)
    if preview is None:
        raise HTTPException(status_code=404, detail="No preview for this file")
    # A file's content never changes, so neither does its preview
    return FileResponse(path=preview, media_type="image/webp",
                        headers={"Cache-Control": "private, max-age=31536000, immutable"})


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
    Only the uploader gets it.

    :param file_id: The unique identifier of the file (without extension)
    :type file_id: str
    :param current_user: The currently authenticated user making the request
    :type current_user: dict
    :return: The extracted text content or audio transcript
    :rtype: str
    :raises HTTPException: 404 if file or text not found or not the user's, 401 if not authenticated
    """
    # First check that the original file exists and is the user's
    _own_file_path(file_id, current_user)

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

    Removes the original file, any extracted text/page images, clears the
    description cache and the owner record. Only the uploader can delete it.

    :param file_id: The unique identifier of the file (without extension)
    :type file_id: str
    :param current_user: The currently authenticated user making the request
    :type current_user: dict
    :raises HTTPException: 404 if file not found or not the user's, 401 if not authenticated
    """
    _own_file_path(file_id, current_user)

    try:
        # Delete the file and its associated files (extracted text, page images, transcripts)
        deleted = delete_stored_file(file_id)
        logger.info(f"Deleted file {file_id} ({deleted} file(s) on disk)")

        # Clear the description cache for this file
        try:
            from backend.services.cache.description_cache import get_description_cache
            cache = get_description_cache()
            await cache.delete_by_file(file_id)
        except Exception as e:
            logger.warning(f"Failed to clear cache for {file_id}: {e}")

        db.delete_uploaded_file(file_id)

    except Exception as e:
        logger.error(f"Error deleting file {file_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to delete file"
        )
