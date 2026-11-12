"""
The stored files of conversations (docs/files.md).

One store for every file: what users upload (backend/api/files.py) and what tools create, e.g.
the images in an MCP server's result (backend/services/mcp/tools.py). A file is stored in
FILES_DIR as <file ID><extension> and has a row in uploaded_files: its owner, and the
conversation it belongs to. The owner reads it through the files API; the conversation's agent
through the file tools (backend/services/tools/file_tools.py), which find files here.

Also here: the previews of images for the chat (thumbnail()) and the scaled copy a vision model
gets (image_for_model()).
"""
import io
import json
import logging
import re
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Optional

from backend.database import db
from backend.services import file_utils
from backend.services.file_utils import get_file_path, is_file_id

log = logging.getLogger(__name__)

# Largest file the store takes, for uploads and for tools' files
MAX_FILE_SIZE = 10 * 1024 * 1024

# Longest edge of an image a vision model gets; larger ones only cost tokens and upload time
MODEL_IMAGE_EDGE = 1568
MODEL_IMAGE_MAX_BYTES = 3 * 1024 * 1024  # As it is only below this (the APIs limit an image's size)

# Longest edge of the previews the chat shows
THUMBNAIL_EDGES = {"small": 256, "large": 1024}

# Longest details of a tool's file (the call's arguments)
MAX_DETAILS_CHARS = 2000

SOURCE_UPLOAD = "upload"
SOURCE_TOOL = "tool"

# The extension a tool's file gets by its type
EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/svg+xml": ".svg",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/ogg": ".ogg",
    "audio/webm": ".webm",
    "audio/mp4": ".m4a",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "application/pdf": ".pdf",
    "application/json": ".json",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/csv": ".csv",
}
TYPES_BY_EXTENSION = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif",
    ".svg": "image/svg+xml", ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg", ".m4a": "audio/mp4",
    ".mp4": "video/mp4", ".pdf": "application/pdf", ".json": "application/json", ".txt": "text/plain",
    ".md": "text/markdown", ".csv": "text/csv",
}

_SAFE_EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,10}")

# Names of tools' files are unique in their conversation: one at a time picks its name
_naming = threading.Lock()


class FileStoreError(Exception):
    """A file can't be stored or found; the message says why (it goes to the model)."""


# =========================================================================
# Storing
# =========================================================================

def new_file_id() -> str:
    """A new file ID: file_<milliseconds>_<hex> (FILE_ID_PATTERN)."""
    return f"file_{int(time.time() * 1000)}_{secrets.token_hex(8)}"


def base_type(mime_type: Optional[str]) -> str:
    """A MIME type without its parameters, lowercase ('audio/webm;codecs=opus' -> 'audio/webm')."""
    return (mime_type or "").split(";")[0].strip().lower()


def extension_for(mime_type: Optional[str], name: Optional[str] = None) -> str:
    """The extension a file is stored with: its name's, else the one of its type, else none."""
    suffix = Path(name).suffix if name else ""
    if suffix and _SAFE_EXTENSION.fullmatch(suffix):
        return suffix
    return EXTENSIONS.get(base_type(mime_type), "")


def image_size(data: bytes) -> Optional[tuple[int, int]]:
    """An image's width and height in pixels as it is shown (EXIF rotation applied), or None."""
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            if image.getexif().get(0x0112) in (5, 6, 7, 8):  # Rotated by a quarter turn
                width, height = height, width
            return width, height
    except Exception:
        return None


def store(data: bytes, user_id: int, *, name: Optional[str], mime_type: Optional[str], **values) -> dict:
    """
    Store a file and record it for its owner.

    Args:
        data: The file's content, at most MAX_FILE_SIZE.
        user_id: The owner.
        name: The file's name; its extension becomes the stored file's.
        mime_type: The file's type.
        values: Further columns of uploaded_files (conversation_id, message_id, source, origin, details).

    Returns:
        The file's row, with "path" (where it is stored).

    Raises:
        FileStoreError: The file is too large.
    """
    if len(data) > MAX_FILE_SIZE:
        raise FileStoreError(f"larger than {format_size(MAX_FILE_SIZE)}")
    file_id = new_file_id()
    mime_type = base_type(mime_type) or None
    width, height = (image_size(data) or (None, None)) if (mime_type or "").startswith("image/") else (None, None)

    # The owner is recorded before the file exists: nobody else can read it
    db.register_uploaded_file(file_id, user_id, name=name, mime_type=mime_type, size_bytes=len(data),
                              width=width, height=height, **values)
    files_dir = Path(file_utils.FILES_DIR)
    files_dir.mkdir(parents=True, exist_ok=True)
    path = files_dir / f"{file_id}{extension_for(mime_type, name)}"
    try:
        path.write_bytes(data)
    except OSError:
        db.delete_uploaded_file(file_id)
        raise
    row = db.get_file(file_id) or {"file_id": file_id, "user_id": user_id, "name": name, "mime_type": mime_type,
                                   "size_bytes": len(data)}
    row["path"] = path
    return row


def _unique_name(stem: str, extension: str, taken: set[str]) -> str:
    """<stem>-<n><extension> with the first number no file of the conversation has."""
    number = 1
    while f"{stem}-{number}{extension}".lower() in taken:
        number += 1
    return f"{stem}-{number}{extension}"


def save_tool_file(data: bytes, *, user_id: int, conversation_id: str, mime_type: Optional[str], stem: str,
                   origin: str, message_id: Optional[int] = None, arguments: Any = None) -> dict:
    """
    Store a file a tool created in a conversation, e.g. an image an MCP server generated.

    Args:
        data: The file's content.
        user_id: The user the agent answers for: the file's owner.
        conversation_id: The conversation it belongs to.
        mime_type: Its type; decides the extension.
        stem: Start of its name, e.g. the server's slug: the file is named <stem>-<n>.<ext>,
            unique in the conversation.
        origin: The tool's title, shown as where the file comes from.
        message_id: The answer the tool ran in.
        arguments: The tool call's arguments, kept (cut) so a later answer knows how the file was made.

    Returns:
        The file's row, with "path".

    Raises:
        FileStoreError: The file is too large.
    """
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", stem).strip("-") or "file"
    details = None
    if arguments:
        details = json.dumps(arguments, ensure_ascii=False, default=str)
        if len(details) > MAX_DETAILS_CHARS:
            details = details[:MAX_DETAILS_CHARS] + " [...]"
    with _naming:
        taken = {(row.get("name") or "").lower() for row in db.get_conversation_files(conversation_id, user_id)}
        name = _unique_name(stem, extension_for(mime_type), taken)
        row = store(data, user_id, name=name, mime_type=mime_type, conversation_id=conversation_id,
                    message_id=message_id, source=SOURCE_TOOL, origin=origin, details=details)
    if row.get("mime_type") == "application/pdf":
        # Like an uploaded PDF: its text and pages, for read_file and the chat's preview
        try:
            from backend.services.document_handler import process_pdf
            process_pdf(row["path"], row["file_id"])
        except Exception as e:
            log.warning(f"Could not process the PDF {row['file_id']}: {e}")
    return row


# =========================================================================
# Finding
# =========================================================================

def conversation_files(conversation_id: Optional[str], user_id: Optional[int]) -> list[dict]:
    """The files of a conversation, oldest first; none without a conversation or a user."""
    if not conversation_id or user_id is None:
        return []
    return db.get_conversation_files(conversation_id, user_id)


def find_file(conversation_id: Optional[str], user_id: Optional[int], reference: str) -> dict:
    """
    The file of a conversation that a model means: by its file ID or by its name.

    Raises:
        FileStoreError: No such file in the conversation, or several with that name. Files of
            other conversations and other users are "not found", like missing ones.
    """
    reference = (reference or "").strip().strip("\"'")
    files = conversation_files(conversation_id, user_id)
    if is_file_id(reference):
        matches = [row for row in files if row["file_id"] == reference]
    else:
        matches = [row for row in files if (row.get("name") or "") == reference]
        if not matches:
            matches = [row for row in files if (row.get("name") or "").lower() == reference.lower()]
    if len(matches) == 1:
        return matches[0]
    if matches:
        ids = ", ".join(row["file_id"] for row in matches)
        raise FileStoreError(f"Several files of this conversation are named '{reference}'. Use the fileId of "
                             f"the one you mean: {ids}")
    raise FileStoreError(f"No file '{reference}' in this conversation"
                         + (". list_files shows the files it has" if files else ": it has no files"))


def file_type(row: dict) -> str:
    """A file's MIME type: the recorded one, else by the stored file's extension."""
    if row.get("mime_type"):
        return row["mime_type"]
    path = get_file_path(row["file_id"])
    return TYPES_BY_EXTENSION.get(path.suffix.lower(), "application/octet-stream") if path else "application/octet-stream"


def file_size(row: dict) -> Optional[int]:
    """A file's size in bytes: the recorded one, else the stored file's."""
    if row.get("size_bytes") is not None:
        return row["size_bytes"]
    path = get_file_path(row["file_id"])
    try:
        return path.stat().st_size if path else None
    except OSError:
        return None


def file_name(row: dict) -> str:
    """A file's name; files without one (old uploads no message attached) go by their ID."""
    return row.get("name") or row["file_id"]


def format_size(size: Optional[int]) -> str:
    """A size for people: 640 B, 12 KB, 1.4 MB."""
    if size is None:
        return "unknown size"
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / 1024 / 1024:.1f} MB"


def file_ref(row: dict) -> dict:
    """A file as the chat shows it (a step's metadata): {fileId, name, mimeType, size, width, height}."""
    ref = {"fileId": row["file_id"], "name": file_name(row), "mimeType": file_type(row)}
    size = file_size(row)
    if size is not None:
        ref["size"] = size
    if row.get("width") and row.get("height"):
        ref["width"], ref["height"] = row["width"], row["height"]
    return ref


# =========================================================================
# Images
# =========================================================================

def _open_image(path: Path) -> tuple[Any, Optional[str]]:
    """An image as shown (the first frame, EXIF rotation applied) and its format ("JPEG", "PNG", ...)."""
    from PIL import Image, ImageOps
    image = Image.open(path)
    image_format = image.format
    image.seek(0)
    return ImageOps.exif_transpose(image), image_format


def _has_alpha(image) -> bool:
    return image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info


def thumbnail(file_id: str, size: str) -> Optional[Path]:
    """
    A preview of an image for the chat: at most THUMBNAIL_EDGES[size] pixels on its longer edge,
    as WebP. Made once and kept next to the file (<file ID>_thumb_<size>.webp, deleted with it).

    Returns:
        The preview's path, or None if the file is missing or no image Pillow can read.
    """
    edge = THUMBNAIL_EDGES[size]
    path = get_file_path(file_id)
    if path is None:
        return None
    preview = path.with_name(f"{file_id}_thumb_{size}.webp")
    if preview.is_file():
        return preview
    try:
        image, _ = _open_image(path)
        image.thumbnail((edge, edge))
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA" if _has_alpha(image) else "RGB")
        # Written under another name first: a reader never gets half a file
        partial = preview.with_name(f"{preview.name}.{secrets.token_hex(4)}.part")
        image.save(partial, "WEBP", quality=82, method=4)
        partial.replace(preview)
        return preview
    except Exception as e:
        log.info(f"No preview of {file_id}: {type(e).__name__}: {e}")
        return None


def image_for_model(file_id: str) -> Optional[tuple[bytes, str]]:
    """
    An image as a vision model gets it: at most MODEL_IMAGE_EDGE pixels on its longer edge, as
    JPEG (PNG with transparency). A JPEG that is small enough goes as it is.

    Returns:
        (data, MIME type), or None if the file is missing or no image Pillow can read.
    """
    path = get_file_path(file_id)
    if path is None:
        return None
    try:
        image, image_format = _open_image(path)
        fits = max(image.size) <= MODEL_IMAGE_EDGE
        if fits and image_format == "JPEG" and path.stat().st_size <= MODEL_IMAGE_MAX_BYTES:
            return path.read_bytes(), "image/jpeg"
        if not fits:
            image.thumbnail((MODEL_IMAGE_EDGE, MODEL_IMAGE_EDGE))
        output = io.BytesIO()
        if _has_alpha(image):
            image.convert("RGBA").save(output, "PNG", optimize=True)
            return output.getvalue(), "image/png"
        image.convert("RGB").save(output, "JPEG", quality=88)
        return output.getvalue(), "image/jpeg"
    except Exception as e:
        log.warning(f"Image {file_id} can't be prepared for the model: {type(e).__name__}: {e}")
        return None
