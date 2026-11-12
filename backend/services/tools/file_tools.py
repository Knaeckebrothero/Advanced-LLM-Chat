# backend/services/tools/file_tools.py
"""
File tools for the agent: list, read and show the files of the conversation it answers in
(docs/files.md): what the user attached and what tools created, e.g. generated images.

The schemas the model sees are defined in backend/llm/tools.py, which binds the user and the
conversation (not arguments the model sees), so the model can't reach the files of another
conversation or user: those are "not found", like missing ones. A refused request raises
ToolInputError with a message for the model, so the step shows as failed.

- list_files: the conversation's files with name, type, size and origin.
- read_file: a file's content as text. A vision model gets an image itself (ToolText.images);
  a text-only model gets what the vision helper says about it, or its answer to a query.
- show_file: puts files into the answer for the user. The result carries them as
  {"shownFiles": [...]} (file_store.file_ref()), which the chat shows above the answer's text.
"""
import asyncio
import base64
import logging
from typing import List, Optional, Union

from backend.llm.tools import ToolInputError, ToolText
from backend.services import file_store
from backend.services.file_store import FileStoreError

logger = logging.getLogger(__name__)


def _origin(row: dict) -> str:
    """Where a file comes from, for the model."""
    if row.get("source") == file_store.SOURCE_TOOL:
        return f"created by {row['origin']}" if row.get("origin") else "created by a tool"
    return "uploaded by the user"


def _describe(row: dict, with_id: bool = False) -> str:
    """One file for the model: name (type, pixels, size): origin, date."""
    facts = [file_store.file_type(row)]
    if row.get("width") and row.get("height"):
        facts.append(f"{row['width']}×{row['height']} px")
    facts.append(file_store.format_size(file_store.file_size(row)))
    line = f"{file_store.file_name(row)} ({', '.join(facts)}): {_origin(row)}"
    if row.get("created_at"):
        line += f", {row['created_at']:%Y-%m-%d %H:%M}"
    if with_id:
        line += f" [fileId: {row['file_id']}]"
    return line


def _find(conversation_id: Optional[str], user_id: Optional[int], reference: str) -> dict:
    try:
        return file_store.find_file(conversation_id, user_id, reference)
    except FileStoreError as e:
        raise ToolInputError(str(e))


def list_files(*, user_id: Optional[int] = None, conversation_id: Optional[str] = None) -> str:
    """
    The files of the conversation, oldest first.

    Args:
        user_id: The user the agent answers for, bound by the tool registry.
        conversation_id: The conversation it answers in, bound by the tool registry.
    """
    files = file_store.conversation_files(conversation_id, user_id)
    if not files:
        return "This conversation has no files."
    names = [file_store.file_name(row).lower() for row in files]
    lines = [f"{number}. {_describe(row, with_id=names.count(file_store.file_name(row).lower()) > 1)}"
             for number, row in enumerate(files, 1)]
    count = "1 file" if len(files) == 1 else f"{len(files)} files"
    return f"{count} in this conversation, oldest first:\n" + "\n".join(lines)


async def read_file(
    file: str,
    query: Optional[str] = None,
    pages: Optional[List[int]] = None,
    *,
    user_id: Optional[int] = None,
    conversation_id: Optional[str] = None,
    vision: bool = False
) -> str:
    """
    The content of a file of the conversation.

    - Text files: the content.
    - Images: the image itself for a vision model, which needs nobody to answer a query for
      it; else a description, or the answer to the query, by the vision helper (cached).
    - PDFs: the extracted text plus descriptions of the pages; with a query, the answer.
    - Audio: the transcript.

    Args:
        file: The file's name or file ID.
        query: Optional question about an image or PDF, answered by the vision helper.
        pages: For PDFs, the pages to read (1-indexed).
        user_id: The user the agent answers for, bound by the tool registry.
        conversation_id: The conversation it answers in, bound by the tool registry.
        vision: The model that reads takes images (ModelConfig.supports_vision), bound by the registry.

    Returns:
        The content as text; for an image a vision model reads, a ToolText with the image.
    """
    from ..file_retrieval_service import get_file_retrieval_service

    logger.info(f"read_file called: file={file}, query={query}, pages={pages}")
    row = await asyncio.to_thread(_find, conversation_id, user_id, file)
    file_id = row["file_id"]
    made_with = f"\n[Made with these arguments: {row['details']}]" if row.get("details") else ""

    if file_store.file_type(row).startswith("image/") and vision:
        prepared = await asyncio.to_thread(file_store.image_for_model, file_id)
        if prepared:
            data, mime_type = prepared
            image = {"type": "image_url",
                     "image_url": {"url": f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"}}
            return ToolText(f"{_describe(row)}. The image follows.{made_with}", images=[image])

    service = get_file_retrieval_service()
    # Text mode: the image itself went above; anything else the model gets as text
    result = await service.get_content(file_id=file_id, query=query, pages=pages, model_receives_images=False)
    if result.error:
        logger.warning(f"File retrieval error for {file_id}: {result.error}")
        raise ToolInputError(result.error.replace(file_id, file_store.file_name(row)))

    parts = []
    if result.text:
        parts.append(result.text)
    # The visual description, if it is not the text itself (PDFs have both)
    if result.description and result.description != result.text:
        parts.append(f"\n[Visual Description]\n{result.description}")
    if not parts:
        return f"[No content found in {file_store.file_name(row)}]"
    return "\n".join(parts) + made_with


def show_file(files: Union[str, List[str]], *, user_id: Optional[int] = None,
              conversation_id: Optional[str] = None) -> ToolText:
    """
    Show files of the conversation to the user, above the text of the answer.

    Args:
        files: The files' names or file IDs (one, or a list).
        user_id: The user the agent answers for, bound by the tool registry.
        conversation_id: The conversation it answers in, bound by the tool registry.

    Returns:
        What is shown, with {"shownFiles": [file_store.file_ref(), ...]} for the chat.
    """
    references = [files] if isinstance(files, str) else [name for name in files if isinstance(name, str)]
    if not references:
        raise ToolInputError("Give the names of the files to show")
    shown, missing = [], []
    for reference in references:
        try:
            row = file_store.find_file(conversation_id, user_id, reference)
        except FileStoreError as e:
            missing.append(str(e))
            continue
        if all(row["file_id"] != other["file_id"] for other in shown):
            shown.append(row)
    if not shown:
        raise ToolInputError(" ".join(missing))
    text = (f"Shown to the user above your answer: {', '.join(file_store.file_name(row) for row in shown)}. "
            f"Refer to them by what they show; don't add links or file names for them.")
    if missing:
        text += "\nNot shown: " + " ".join(missing)
    return ToolText(text, {"shownFiles": [file_store.file_ref(row) for row in shown]})
