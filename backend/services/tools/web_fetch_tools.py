# backend/services/tools/web_fetch_tools.py
"""
The agent's tool web_fetch (docs/files.md, "Web addresses"): what is at a web address.

- A web page comes back as text, with its links and the addresses of its images.
- An image, PDF or audio file is saved to the conversation the agent answers in, like a file
  any other tool creates: the chat shows it, the agent places it in its answer by its name,
  and the file tools list and read it again. A vision model gets an image itself; a text-only
  model gets what the vision helper says about it.

The schema the model sees is in backend/llm/tools.py, which binds the user, the conversation
and the answer (not arguments the model sees). backend/services/web_fetch.py does the fetching,
with its limits: public addresses only, nothing of the user sent along.
"""
import asyncio
import logging
from typing import Optional
from urllib.parse import urlsplit

from backend.llm.tools import ToolError, ToolText
from backend.services import file_store, web_fetch as web
from backend.services.file_store import FileStoreError
from backend.services.file_utils import get_file_path
from backend.services.tools import file_tools

logger = logging.getLogger(__name__)

# Most text of a page, a text file or a PDF that goes to the model (about 10,000 tokens)
MAX_TEXT_CHARS = 40_000
# A page with less text than this probably builds itself in the browser
LITTLE_TEXT_CHARS = 200
# Starts the origin of a fetched file ("Web: example.com"), shown as where it comes from
ORIGIN = "Web: "


def _part(text: str, start: int = 0, read_on: bool = True) -> str:
    """
    The part of a long text the model gets: MAX_TEXT_CHARS characters from start, with where
    it was cut and (read_on) how to get the rest.
    """
    start = max(start, 0)
    if start and start >= len(text):
        return f"[Nothing from character {start} on: the text has {len(text)} characters.]"
    end = start + MAX_TEXT_CHARS
    part = text[start:end]
    if start:
        part = f"[From character {start} of {len(text)}]\n\n{part}"
    if end < len(text):
        how = f" To read on, call web_fetch with the same address and start={end}." if read_on else ""
        part += f"\n\n[... cut off at character {end} of {len(text)}.{how}]"
    return part


def _page(found: web.Fetched, start: int = 0) -> str:
    """A fetched page for the model: its address, title, description and preview image, then its text."""
    page = web.page_text(found.as_text(), found.url)
    lines = [f"Web page: {found.url}"]
    if page.title:
        lines.append(f"Title: {page.title}")
    if page.description:
        lines.append(f"Description: {page.description[:500]}")
    if page.image:
        lines.append(f"Preview image: {page.image}")
    if page.origin:
        lines.append(f"Links that start with / are on {page.origin}")
    notes = []
    if not found.complete:
        notes.append(f"[Only the first {file_store.format_size(web.MAX_TEXT_BYTES)} of the page were read.]")
    if len(page.text) < LITTLE_TEXT_CHARS:
        notes.append("[The page has little text of its own: it is probably built in the browser by scripts, "
                     "which are not run here.]")
    return "\n\n".join(part for part in ("\n".join(lines), _part(page.text, start), *notes) if part)


def _text(found: web.Fetched, start: int = 0) -> str:
    note = ("" if found.complete
            else f"\n\n[Only the first {file_store.format_size(web.MAX_TEXT_BYTES)} were read.]")
    return f"{found.mime_type or 'Text'} at {found.url}:\n\n{_part(found.as_text(), start)}{note}"


def _saved_note(row: dict) -> str:
    """What the model is told about a fetched file: where the user sees it, and how to show it."""
    name = file_store.file_name(row)
    shows = "what it shows" if file_store.file_type(row).startswith("image/") else "what it is"
    return (f"[Saved to this conversation as \"{name}\". The user sees only a small preview of it so far. To show "
            f"it in your answer, write ![{shows}]({name}) on a line of its own where you talk about it.]")


async def _described(row: dict) -> str:
    """What the vision helper says an image shows, for a model that can't see it (cached, as read_file's)."""
    from backend.services.file_retrieval_service import get_file_retrieval_service
    result = await get_file_retrieval_service().get_content(file_id=row["file_id"], model_receives_images=False)
    described = result.text or result.description
    if result.error or not described:
        return f"[The image could not be described: {result.error or 'no description'}]"
    return f"What a vision model says it shows:\n{described}"


def _save(found: web.Fetched, user_id: int, conversation_id: str, answer_id: Optional[int]) -> dict:
    """
    A fetched file as a file of the conversation: saved, unless the conversation has this very
    file from the web already. An agent that opens an address again, to look once more in a
    later turn, gets the same file, not a copy.
    """
    for row in file_store.conversation_files(conversation_id, user_id):
        if (row.get("source") == file_store.SOURCE_TOOL and (row.get("origin") or "").startswith(ORIGIN)
                and row.get("size_bytes") == len(found.data)):
            path = get_file_path(row["file_id"])
            if path and path.read_bytes() == found.data:
                return row
    host = urlsplit(found.requested or found.url).hostname or "the web"
    return file_store.save_tool_file(
        found.data, user_id=user_id, conversation_id=conversation_id, mime_type=found.mime_type,
        stem=web.file_stem(found.url), origin=f"{ORIGIN}{host}", message_id=answer_id,
        arguments={"url": found.requested or found.url}, numbered=False)


async def _file(found: web.Fetched, *, user_id: int, conversation_id: str, answer_id: Optional[int],
                vision: bool) -> ToolText:
    """Save a fetched file to the conversation and give the model what it holds."""
    try:
        # In a thread: storing reads the database, and a PDF is processed before this returns
        row = await asyncio.to_thread(_save, found, user_id, conversation_id, answer_id)
    except FileStoreError as e:
        raise ToolError(f"The file can't be kept: {e}")
    name, mime_type = file_store.file_name(row), file_store.file_type(row)
    facts = [mime_type]
    if row.get("width") and row.get("height"):
        facts.append(f"{row['width']}×{row['height']} px")
    facts.append(file_store.format_size(file_store.file_size(row)))
    head = f"Fetched {found.requested or found.url}: \"{name}\" ({', '.join(facts)})."
    images: list[dict] = []

    if mime_type.startswith("image/"):
        image = await file_tools.image_content(row["file_id"]) if vision else None
        if image:
            images.append(image)
            body = "The image follows." + file_tools.seen_scaled(row)
        else:
            body = await _described(row)
    elif mime_type == "application/pdf":
        from backend.services.document_handler import get_extracted_text
        text = await asyncio.to_thread(get_extracted_text, row["file_id"])
        body = _part(text, read_on=False) if text and text.strip() else "[No text could be read from the PDF.]"
    else:
        body = "[Audio: it is saved, not transcribed.]"
    return ToolText(f"{head}\n\n{body}\n\n{_saved_note(row)}", {"files": [file_store.file_ref(row)]}, images)


async def web_fetch(
    url: str,
    start: int = 0,
    *,
    user_id: Optional[int] = None,
    conversation_id: Optional[str] = None,
    answer_id: Optional[int] = None,
    vision: bool = False
) -> str:
    """
    What is at a web address.

    Args:
        url: The address (http or https).
        start: For a long page or text, the character to read from (the note under a cut-off result names it).
        user_id: The user the agent answers for, bound by the tool registry: the owner of a fetched file.
        conversation_id: The conversation it answers in, bound by the registry: where a fetched file goes.
        answer_id: The id of the message being written, recorded with a fetched file.
        vision: The model that reads takes images (ModelConfig.supports_vision), bound by the registry.

    Returns:
        A page or text as text; for a file, a ToolText with the file for the chat and, for a
        vision model, the image.

    Raises:
        ToolError: The address can't be fetched, or its file can't be kept; the message says why.
    """
    try:
        found = await web.fetch(url)
    except web.WebFetchError as e:
        logger.info(f"web_fetch failed: {e}")
        raise ToolError(str(e))
    logger.info(f"web_fetch: {found.kind} ({found.mime_type}, {len(found.data)} bytes) from "
                f"{urlsplit(found.url).hostname}")
    if found.kind == web.PAGE:
        return await asyncio.to_thread(_page, found, start)
    if found.kind == web.TEXT:
        return _text(found, start)
    if user_id is None or not conversation_id:
        raise ToolError("The address is a file, and there is no conversation to save it in")
    return await _file(found, user_id=user_id, conversation_id=conversation_id, answer_id=answer_id, vision=vision)
