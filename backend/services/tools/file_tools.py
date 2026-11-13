# backend/services/tools/file_tools.py
"""
File tools for the agent: list and read the files of the conversation it answers in
(docs/files.md): what the user attached and what tools created, e.g. generated images.
The agent shows a file by placing it in the text of its answer, without a tool.

The schemas the model sees are defined in backend/llm/tools.py, which binds the user and the
conversation (not arguments the model sees), so the model can't reach the files of another
conversation or user: those are "not found", like missing ones. A refused request raises
ToolInputError with a message for the model, so the step shows as failed.

- list_files: the conversation's files with name, type, size and origin.
- read_file: a file's content as text. A vision model gets an image itself (ToolText.images);
  a text-only model gets what the vision helper says about it, or its answer to a query. A
  model sees an image scaled down; with region it looks closer at a part, at up to the image's
  own resolution.
"""
import asyncio
import base64
import logging
from typing import List, Optional

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


def _image_content(data: bytes, mime_type: str) -> dict:
    """Image data as a tool result carries it for a vision model: an image_url part (OpenAI format)."""
    return {"type": "image_url",
            "image_url": {"url": f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"}}


async def image_content(file_id: str) -> Optional[dict]:
    """
    A stored image as a vision model gets it in a tool's result: the scaled image as an image_url
    part, or None for one that can't be prepared (file_store.image_for_model()).
    """
    prepared = await asyncio.to_thread(file_store.image_for_model, file_id)
    return _image_content(*prepared) if prepared else None


def seen_scaled(row: dict) -> str:
    """For a model that gets an image: a sentence on the size it sees it at, if that is smaller than the image."""
    width, height = row.get("width") or 0, row.get("height") or 0
    longest = max(width, height)
    if longest <= file_store.MODEL_IMAGE_EDGE:
        return ""
    edge = file_store.MODEL_IMAGE_EDGE
    return f" You see it scaled down to {round(width * edge / longest)}×{round(height * edge / longest)} px."


REGION_EXAMPLE = '{"left": 50, "top": 0, "right": 100, "bottom": 50}'
# The smallest part of an image to look at, in percent of its width and height
MIN_REGION = 1.0


def _percent(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _region(region) -> tuple[float, float, float, float]:
    """
    The part of an image a model names, as percent of its width and height: left, top, right, bottom.

    Raises:
        ToolInputError: Not four edges that enclose a part of the image.
    """
    try:
        edges = [float(region[name]) for name in ("left", "top", "right", "bottom")]
    except (KeyError, TypeError, ValueError):
        raise ToolInputError(f"region needs the four edges left, top, right and bottom in percent of the image, "
                             f"e.g. {REGION_EXAMPLE} for its top right quarter")
    if all(0 <= edge <= 1 for edge in edges):
        edges = [edge * 100 for edge in edges]  # Fractions, meant as shares of the image
    left, top, right, bottom = (min(max(edge, 0.0), 100.0) for edge in edges)
    if right - left < MIN_REGION or bottom - top < MIN_REGION:
        raise ToolInputError("region: right must be greater than left and bottom greater than top, in percent of "
                             f"the image from its top left corner (0 to 100), e.g. {REGION_EXAMPLE}")
    return left, top, right, bottom


async def _read_region(row: dict, region, query: Optional[str], vision: bool) -> str:
    """A part of an image, to look closer: the part itself for a vision model, else what the vision helper says."""
    name = file_store.file_name(row)
    if not file_store.file_type(row).startswith("image/"):
        raise ToolInputError(f"region is for images; {name} is {file_store.file_type(row)}")
    left, top, right, bottom = _region(region)
    part = await asyncio.to_thread(file_store.image_part_for_model, row["file_id"],
                                   (left / 100, top / 100, right / 100, bottom / 100))
    if part is None:
        raise ToolInputError(f"No part of {name} can be shown: it can't be read as an image, or it has too many pixels")
    of = f" of {row['width']}×{row['height']} px" if row.get("width") and row.get("height") else ""
    scale = ("at the image's own resolution" if part.scale >= 0.995
             else f"scaled down to {part.width}×{part.height} px ({part.scale:.0%})")
    where = (f"{name}, the part from {_percent(left)}% to {_percent(right)}% of its width and {_percent(top)}% to "
             f"{_percent(bottom)}% of its height: {part.box[2] - part.box[0]}×{part.box[3] - part.box[1]} px{of}, {scale}.")
    if vision:
        return ToolText(f"{where} It follows.", images=[_image_content(part.data, part.mime_type)])
    from ..file_retrieval_service import get_file_retrieval_service
    label = ",".join(_percent(edge) for edge in (left, top, right, bottom))
    described = await get_file_retrieval_service().describe_image_part(row["file_id"], part.data, part.mime_type,
                                                                       label, query)
    return f"{where}\n{described}"


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
    region: Optional[dict] = None,
    *,
    user_id: Optional[int] = None,
    conversation_id: Optional[str] = None,
    vision: bool = False
) -> str:
    """
    The content of a file of the conversation.

    - Text files: the content.
    - Images: the image itself for a vision model, which needs nobody to answer a query for
      it; else a description, or the answer to the query, by the vision helper (cached). A
      model gets an image scaled down (file_store.MODEL_IMAGE_EDGE); with region, a part of
      it at up to the image's own resolution.
    - PDFs: the extracted text plus descriptions of the pages; with a query, the answer.
    - Audio: the transcript.

    Args:
        file: The file's name or file ID.
        query: Optional question about an image or PDF, answered by the vision helper.
        pages: For PDFs, the pages to read (1-indexed).
        region: For images, the part to look closer at: its edges left, top, right and bottom in
            percent of the image's width and height, from its top left corner.
        user_id: The user the agent answers for, bound by the tool registry.
        conversation_id: The conversation it answers in, bound by the tool registry.
        vision: The model that reads takes images (ModelConfig.supports_vision), bound by the registry.

    Returns:
        The content as text; for an image a vision model reads, a ToolText with the image.
    """
    from ..file_retrieval_service import get_file_retrieval_service

    logger.info(f"read_file called: file={file}, query={query}, pages={pages}, region={region}")
    row = await asyncio.to_thread(_find, conversation_id, user_id, file)
    file_id = row["file_id"]
    made_with = f"\n[Made with these arguments: {row['details']}]" if row.get("details") else ""

    if region is not None:
        return await _read_region(row, region, query, vision)
    if file_store.file_type(row).startswith("image/") and vision:
        image = await image_content(file_id)
        if image:
            closer = seen_scaled(row)
            if closer:
                closer += f" To look closer at a part of it, call read_file with region, e.g. {REGION_EXAMPLE}."
            return ToolText(f"{_describe(row)}. The image follows.{closer}{made_with}", images=[image])

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

