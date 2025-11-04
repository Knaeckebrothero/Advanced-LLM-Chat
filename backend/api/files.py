"""
File upload API endpoints.
"""
import secrets
import time
from typing import List
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from backend.models.common import ErrorResponse
from backend.security.auth import get_current_user

router = APIRouter(prefix="/api/files", tags=["Files"])


@router.post("/upload",
             response_model=List[str],
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
    and saves them to a local directory. It returns a list of unique file identifiers
    of successfully uploaded files. If no files are provided or a file exceeds the
    maximum allowed size of 10 MB, an appropriate HTTP response is returned.

    :param files: The list of files to be uploaded
    :type files: List[UploadFile]
    :param current_user: The currently authenticated user making the request
    :type current_user: dict
    :return: A list of unique file IDs representing the uploaded files
    :rtype: List[str]
    :raises HTTPException: Raised on validation errors like missing files, files
        exceeding the size limit, or on internal server errors
    """
    print(f"File upload called with {len(files)} files")

    try:
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")

        file_ids = []
        max_file_size = 10 * 1024 * 1024  # 10MB limit per file
        files_dir = Path("./files")

        # Ensure files directory exists
        files_dir.mkdir(exist_ok=True)

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
            file_path = files_dir / stored_filename
            with open(file_path, "wb") as f:
                f.write(contents)

            file_ids.append(file_id)
            print(f"Uploaded file: {file.filename} -> {file_id} (size: {len(contents)} bytes) saved to {file_path}")

            # Reset file position (not needed after saving, but good practice)
            await file.seek(0)

        return file_ids

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error uploading files: {str(e)}")
        raise HTTPException(status_code=500, detail="Error uploading files")
