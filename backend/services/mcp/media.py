"""
The media of an MCP tool result (docs/files.md, docs/mcp.md): images, audio and PDFs, as bytes.

A result carries media in three ways:
- In the result itself (image and audio blocks, embedded resources): base64, decoded here.
- As a link to a resource of the server (resource_link): read from the server (resources/read).
- A server may link a resource it can't deliver that way: Civitai's resources/read returns an
  image's bytes as text, which destroys them, and names the image's web address in the result's
  text. So when a linked resource can't be read, or what comes back is no base64, the web
  address in the result that ends in the resource's file name is downloaded instead.

Downloads only follow https, only to public addresses (unless MCP_ALLOW_PRIVATE_URLS), carry
none of the server's headers, and stop at the size the file store takes from a tool.
"""
import asyncio
import base64
import binascii
import json
import logging
import re
from pathlib import PurePosixPath
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import httpx2

from backend.config import MCP_ALLOW_PRIVATE_URLS, MCP_CONNECT_TIMEOUT
from backend.services import file_store
from backend.services.mcp.pool import describe_error, http_client

log = logging.getLogger(__name__)

# The media worth fetching: not text (the result would grow without the model asking) and not
# video (too large to hold in memory)
MEDIA_TYPES = ("image/", "audio/", "application/pdf")

MAX_LINKS = 20            # Linked resources read from one result
MAX_ADDRESSES = 3         # Web addresses tried for one linked resource
MAX_REDIRECTS = 4
READ_TIMEOUT = 60.0       # Reading one resource, or downloading one file

_WEB_ADDRESS = re.compile(r"https://[^\s\"'<>\\]+(?:\\u00[0-9a-fA-F]{2}[^\s\"'<>\\]*)*")


def decode(data: Optional[str]) -> Optional[bytes]:
    """The bytes of base64 content; None for content that is no base64 (or empty)."""
    if not data or not isinstance(data, str):
        return None
    try:
        text = re.sub(r"\s+", "", data)
        if "-" in text or "_" in text:
            return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4)) or None
        return base64.b64decode(text, validate=True) or None
    except (binascii.Error, ValueError):
        return None


def media_type(mime_type: Optional[str], *names: str) -> Optional[str]:
    """The type if it is media worth fetching (MEDIA_TYPES): the given one, else by a name's ending."""
    found = file_store.base_type(mime_type)
    if not found:
        for name in names:
            found = file_store.TYPES_BY_EXTENSION.get(PurePosixPath(name or "").suffix.lower(), "")
            if found:
                break
    return found if found.startswith(MEDIA_TYPES) else None


def link_type(block) -> Optional[str]:
    """The media type of a resource_link block, or None if it links no media."""
    return media_type(getattr(block, "mime_type", None), urlparse(str(block.uri)).path, block.name or "")


def _strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def web_addresses(result) -> list[str]:
    """The https addresses a result names, in its structured content and its text, without repeats."""
    found: list[str] = []
    for text in _strings(getattr(result, "structured_content", None)):
        if text.startswith("https://") and not re.search(r"\s", text):
            found.append(text)
    for block in result.content or []:
        if getattr(block, "type", None) != "text":
            continue
        for match in _WEB_ADDRESS.findall(block.text or ""):
            # Text that is JSON escapes & as &
            if "\\u" in match:
                try:
                    match = json.loads(f'"{match}"')
                except ValueError:
                    continue
            found.append(match.rstrip(".,;)]}"))
    return list(dict.fromkeys(found))


async def download(url: str) -> Optional[tuple[bytes, str]]:
    """
    A media file from a web address: (data, MIME type), or None if it is no media, too large,
    not reachable, or not on a public https address.
    """
    limit = file_store.MAX_TOOL_FILE_SIZE
    timeout = httpx2.Timeout(MCP_CONNECT_TIMEOUT, read=READ_TIMEOUT)
    try:
        async with http_client(guarded=not MCP_ALLOW_PRIVATE_URLS, timeout=timeout) as client:
            for _ in range(MAX_REDIRECTS + 1):
                if urlparse(url).scheme != "https":
                    return None
                async with client.stream("GET", url) as response:
                    if response.status_code in (301, 302, 303, 307, 308) and response.headers.get("location"):
                        url = urljoin(url, response.headers["location"])
                        continue
                    found = media_type(response.headers.get("content-type"))
                    if response.status_code != 200 or not found:
                        log.info(f"No media at {urlparse(url).netloc}: {response.status_code} "
                                 f"{response.headers.get('content-type')}")
                        return None
                    chunks, size = [], 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > limit:
                            log.info(f"Media at {urlparse(url).netloc} is larger than {file_store.format_size(limit)}")
                            return None
                        chunks.append(chunk)
                    return b"".join(chunks), found
    except Exception as e:
        log.warning(f"Could not download media from {urlparse(url).netloc}: {describe_error(e)}")
    return None


async def _read(client, block, result) -> list[tuple[str, bytes]]:
    """The media of one linked resource: from the server, else from its web address in the result."""
    fallback = link_type(block)
    try:
        contents = (await asyncio.wait_for(client.read_resource(str(block.uri)), READ_TIMEOUT)).contents
    except Exception as e:
        log.info(f"Could not read the linked resource {block.uri}: {describe_error(e)}")
        contents = []
    media = [(content.mime_type or fallback, decode(content.blob)) for content in contents
             if getattr(content, "blob", None)]
    if media and all(data for _, data in media):
        return media

    # Not delivered (or destroyed on the way): the same file at a web address the result names
    name = PurePosixPath(urlparse(str(block.uri)).path).name
    addresses = [url for url in web_addresses(result) if name and PurePosixPath(urlparse(url).path).name == name]
    if not addresses:
        return []
    log.info(f"The linked resource {block.uri} can't be read from the server; trying its web address")
    downloads = [found for found in await asyncio.gather(*(download(url) for url in addresses[:MAX_ADDRESSES]))
                 if found]
    if not downloads:
        return []
    # Several addresses of one file are sizes of it (a preview and the original): the largest
    data, found_type = max(downloads, key=lambda found: len(found[0]))
    return [(found_type, data)]


async def read_links(client, result) -> dict[int, list[tuple[str, bytes]]]:
    """
    The media a result links to (resource_link blocks of images, audio and PDFs), fetched:
    {index of the block: [(MIME type, data), ...]}. A link whose media can't be had is left
    out and stays a link for the model.
    """
    links = [(index, block) for index, block in enumerate(result.content or [])
             if getattr(block, "type", None) == "resource_link" and link_type(block)][:MAX_LINKS]
    if not links:
        return {}
    media = await asyncio.gather(*(_read(client, block, result) for _, block in links))
    return {index: found for (index, _), found in zip(links, media) if found}
