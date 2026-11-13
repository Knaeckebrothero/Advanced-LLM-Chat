"""
What is at a web address, for the agent's tool web_fetch (docs/files.md, "Web addresses"):
fetch() gets a page or a file with limits, page_text() turns a page's HTML into text.

The address comes from a model, which may have it from anywhere (a page, a tool's result, a
planted instruction), so:
- Only http and https, and only public addresses. The host is resolved once, every address it
  resolves to must be public, and the connection goes to an address that was checked: a name
  that resolves to something else a moment later leads nowhere else. Every redirect is checked
  the same way.
- Nothing of the user or the server goes along: no cookies, no credentials, no proxy settings,
  a fixed User-Agent.
- Limits on time, size and redirects. What is read is decided by the type the server names:
  a page or text is cut at MAX_TEXT_BYTES, a file (image, audio, PDF) may be as large as the
  file store takes, video and anything else is not read at all.
"""
import asyncio
import contextvars
import io
import ipaddress
import logging
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import PurePosixPath
from typing import Optional, Union
from urllib.parse import unquote, urljoin, urlsplit

import httpx2

from backend.services import file_store

log = logging.getLogger(__name__)

# Addresses that are not public (loopback, private networks, link-local) are refused. Tests of
# the tool against a local server switch this on; no setting does
ALLOW_PRIVATE_ADDRESSES = False

USER_AGENT = "Mozilla/5.0 (compatible; LLMChat/1.0; web_fetch)"
ACCEPT = "text/html,application/xhtml+xml,image/*,application/pdf,*/*;q=0.8"

MAX_URL_CHARS = 2000
MAX_REDIRECTS = 5
MAX_ADDRESSES = 3               # Addresses of a host that are tried
CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 20.0             # Between two pieces of the answer
TOTAL_TIMEOUT = 60.0            # One fetch, with its redirects
MAX_TEXT_BYTES = 2 * 1024 * 1024    # Of a page or text; the rest is not read

# What an address holds, for the tool: a page (HTML), other text, or a file to keep
PAGE, TEXT, FILE = "page", "text", "file"

_HTML_TYPES = ("text/html", "application/xhtml+xml")
_TEXT_TYPES = ("application/json", "application/xml", "application/javascript", "application/x-javascript",
               "application/x-ndjson", "application/yaml", "application/x-yaml", "application/toml",
               "application/rss+xml", "application/atom+xml", "image/svg+xml")
_TEXT_EXTENSIONS = (".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml", ".svg", ".log", ".rst", ".toml")
_REDIRECTS = (301, 302, 303, 307, 308)
# Image services name an original that is too large next to smaller versions of it
SMALLER_HINT = ("If the site has a smaller version of it (a preview's address, or a width in the address), "
                "fetch that one.")


# The HTTP library logs every request with its whole address. Not for these: an address a user's
# agent opens can carry a signature or a search, and the log line of the tool names the host
_fetching: contextvars.ContextVar[bool] = contextvars.ContextVar("web_fetch", default=False)
logging.getLogger("httpx2").addFilter(lambda record: not _fetching.get())


class WebFetchError(Exception):
    """An address can't be fetched; the message says why (it goes to the model)."""


@dataclass
class Fetched:
    """What an address returned."""
    url: str                    # The address that answered, after redirects
    kind: str                   # PAGE, TEXT or FILE
    mime_type: str              # For a file its real type (an image's by its content), else the one named
    data: bytes
    charset: Optional[str] = None   # The one the server names, for text
    complete: bool = True       # False: text that was cut at MAX_TEXT_BYTES
    requested: str = ""         # The address that was asked for, checked (url, unless it redirected)

    def as_text(self) -> str:
        """The data as text (pages and text)."""
        return decode_text(self.data, self.charset, html=self.kind == PAGE)


# =========================================================================
# Addresses
# =========================================================================

def clean_url(url: str) -> str:
    """
    A web address as a model wrote it, checked: http or https with a host, without a fragment.

    Raises:
        WebFetchError: Not a web address this tool fetches.
    """
    url = (url or "").strip().strip("<>\"'`").strip()
    if not url or len(url) > MAX_URL_CHARS or re.search(r"\s", url):
        raise WebFetchError("That is not a web address")
    if "://" not in url and re.match(r"^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+(/|$|:|\?)", url):
        url = "https://" + url
    try:
        parts = urlsplit(url)
        host = parts.hostname
        parts.port  # Raises for a port that is none
    except ValueError:
        raise WebFetchError("That is not a web address")
    if parts.scheme not in ("http", "https") or not host:
        raise WebFetchError("Only http and https addresses can be fetched")
    if parts.username or parts.password:
        raise WebFetchError("Addresses with a user name or password are not fetched")
    return parts._replace(fragment="").geturl()


def _public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


async def _addresses(host: str, port: int) -> list[str]:
    """
    The addresses to connect to for a host, IPv4 first: all of them checked to be public.

    Raises:
        WebFetchError: The host doesn't resolve, or one of its addresses is not public.
    """
    literal = host.strip("[]")
    try:
        ipaddress.ip_address(literal)
        found = [literal]
    except ValueError:
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except (socket.gaierror, UnicodeError):
            raise WebFetchError(f"{host} can't be found")
        found = list(dict.fromkeys(info[4][0].split("%")[0] for info in infos))
    if not found:
        raise WebFetchError(f"{host} can't be found")
    if not ALLOW_PRIVATE_ADDRESSES and not all(_public(address) for address in found):
        raise WebFetchError(f"{host} is not a public web address")
    return sorted(found, key=lambda address: ":" in address)[:MAX_ADDRESSES]


# =========================================================================
# Fetching
# =========================================================================

def _kind(mime_type: str, path: str) -> Optional[str]:
    """What the type a server names holds (PAGE, TEXT, FILE); None for one this tool doesn't read."""
    if mime_type in _HTML_TYPES:
        return PAGE
    if mime_type.startswith("text/") or mime_type in _TEXT_TYPES or mime_type.endswith(("+json", "+xml")):
        return TEXT
    if mime_type.startswith(("image/", "audio/")) or mime_type == "application/pdf":
        return FILE
    if mime_type.startswith("video/"):
        return None
    # No type, or one that says nothing (application/octet-stream): by the address's ending
    suffix = PurePosixPath(path).suffix.lower()
    by_name = file_store.TYPES_BY_EXTENSION.get(suffix, "")
    if suffix in _TEXT_EXTENSIONS:
        return TEXT
    if by_name.startswith(("image/", "audio/")) or by_name == "application/pdf":
        return FILE
    return None


def image_type(data: bytes) -> Optional[str]:
    """The type of an image by its content ('image/webp'), or None for what is no image Pillow reads."""
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            return Image.MIME.get(image.format)
    except Exception:
        return None


def _file_type(mime_type: str, data: bytes, path: str) -> str:
    """
    A fetched file's real type. Servers name images wrongly (a .jpeg address that returns WebP,
    a sign-in page in place of an image), and the type decides how the file is stored and read.

    Raises:
        WebFetchError: The data is not what the type says.
    """
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    found = image_type(data)
    if found:
        return found
    by_name = file_store.TYPES_BY_EXTENSION.get(PurePosixPath(path).suffix.lower(), "")
    if mime_type.startswith("audio/"):
        return mime_type
    if by_name.startswith("audio/") and not mime_type.startswith("image/") and mime_type != "application/pdf":
        return by_name
    if mime_type == "application/pdf" or by_name == "application/pdf":
        raise WebFetchError("The address says it is a PDF, but what it returned is none")
    raise WebFetchError("The address returned no image that can be read"
                        + (" (a web page: the site may want a sign-in)" if data.lstrip()[:1] == b"<" else ""))


async def _read(response, limit: int, cut: bool) -> tuple[bytes, bool]:
    """A response's body up to a limit: (data, complete). Past it, text is cut and a file is refused."""
    declared = response.headers.get("content-length", "")
    if not cut and declared.isdigit() and int(declared) > limit:
        raise WebFetchError(f"The file is larger than {file_store.format_size(limit)} "
                            f"({file_store.format_size(int(declared))}). {SMALLER_HINT}")
    chunks, size = [], 0
    async for chunk in response.aiter_bytes():
        if size + len(chunk) > limit:
            if not cut:
                raise WebFetchError(f"The file is larger than {file_store.format_size(limit)}. {SMALLER_HINT}")
            chunks.append(chunk[:limit - size])
            return b"".join(chunks), False
        size += len(chunk)
        chunks.append(chunk)
    return b"".join(chunks), True


def _status_error(status: int, host: str) -> WebFetchError:
    if status in (401, 403):
        return WebFetchError(f"{host} refused the request ({status}): the address needs a sign-in, or the site "
                             f"blocks automated requests")
    if status == 404:
        return WebFetchError(f"Nothing at this address ({host} answered 404)")
    if status == 429:
        return WebFetchError(f"{host} answered 429: too many requests, try again later")
    return WebFetchError(f"{host} answered {status}")


async def _get(client: httpx2.AsyncClient, url: str) -> Union[Fetched, str]:
    """One request: what the address returned, or the address it redirects to."""
    parts = httpx2.URL(url)
    host = parts.raw_host.decode("ascii")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    headers = {"Host": parts.netloc.decode("ascii")}
    extensions = {"sni_hostname": host} if parts.scheme == "https" else {}
    last_error: Optional[Exception] = None
    for address in await _addresses(host, port):
        try:
            # To the checked address, as the host: its name in the Host header and the certificate check
            async with client.stream("GET", parts.copy_with(host=address), headers=headers,
                                     extensions=extensions) as response:
                status = response.status_code
                if status in _REDIRECTS and response.headers.get("location"):
                    return urljoin(url, response.headers["location"])
                if status != 200:
                    raise _status_error(status, host)
                mime_type = file_store.base_type(response.headers.get("content-type"))
                kind = _kind(mime_type, parts.path)
                if kind is None:
                    what = "a video" if mime_type.startswith("video/") else f"a file of the type {mime_type or 'unknown'}"
                    raise WebFetchError(f"The address is {what}, which can't be fetched")
                if kind == FILE:
                    data, _ = await _read(response, file_store.MAX_TOOL_FILE_SIZE, cut=False)
                    return Fetched(url, FILE, _file_type(mime_type, data, parts.path), data)
                data, complete = await _read(response, MAX_TEXT_BYTES, cut=True)
                return Fetched(url, kind, mime_type, data, response.charset_encoding, complete)
        except (httpx2.ConnectError, httpx2.ConnectTimeout) as e:
            last_error = e  # The host's next address
    log.info(f"Could not connect to {host}: {type(last_error).__name__}: {last_error}")
    raise WebFetchError(f"{host} can't be reached")


async def _fetch(url: str) -> Fetched:
    timeout = httpx2.Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT)
    headers = {"User-Agent": USER_AGENT, "Accept": ACCEPT}
    async with httpx2.AsyncClient(timeout=timeout, headers=headers, follow_redirects=False,
                                  trust_env=False) as client:
        for _ in range(MAX_REDIRECTS + 1):
            found = await _get(client, url)
            if isinstance(found, Fetched):
                return found
            url = clean_url(found)
            client.cookies.clear()
    raise WebFetchError("The address redirects too often")


async def fetch(url: str) -> Fetched:
    """
    What is at a web address (see the module's notes on what is fetched and how).

    Args:
        url: The address; clean_url() checks it.

    Raises:
        WebFetchError: The address is none, is not public, can't be reached, answered with an
            error, or holds something this tool doesn't read. The message is for the model.
    """
    url = clean_url(url)
    host = urlsplit(url).hostname or ""
    quiet = _fetching.set(True)
    try:
        found = await asyncio.wait_for(_fetch(url), TOTAL_TIMEOUT)
        found.requested = url
        return found
    except WebFetchError:
        raise
    except (asyncio.TimeoutError, TimeoutError, httpx2.TimeoutException):
        raise WebFetchError(f"{host} didn't answer in time")
    except httpx2.HTTPError as e:
        log.info(f"Fetching from {host} failed: {type(e).__name__}")
        raise WebFetchError(f"The answer of {host} can't be read ({type(e).__name__})")
    finally:
        _fetching.reset(quiet)


# =========================================================================
# Text
# =========================================================================

_META_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?\s*([A-Za-z0-9_.:-]+)""", re.I)


def decode_text(data: bytes, charset: Optional[str] = None, html: bool = False) -> str:
    """Bytes as text: in the charset the server names, else the page's own (meta), else UTF-8."""
    names = [charset]
    if html:
        found = _META_CHARSET.search(data[:4096])
        names.append(found.group(1).decode("ascii", "replace") if found else None)
    for name in names:
        if not name:
            continue
        try:
            return data.decode(name, errors="replace")
        except LookupError:
            continue
    return data.decode("utf-8", errors="replace")


def file_stem(url: str) -> str:
    """The start of the name a fetched file is saved under: the last part of its address, without the ending."""
    name = PurePosixPath(unquote(urlsplit(url).path)).name
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", PurePosixPath(name).stem).strip("-")[:48].strip("-")
    return stem if re.search(r"[A-Za-z0-9]", stem) else "web"


# What a page says is not in these
_SKIPPED = frozenset({"script", "style", "noscript", "template", "svg", "iframe", "canvas", "object", "select",
                      "nav", "footer"})
_BLOCKS = frozenset({"p", "div", "section", "article", "main", "header", "aside", "figure", "figcaption", "form",
                     "blockquote", "ul", "ol", "dl", "table", "details", "summary", "address", "fieldset"})
_LINES = frozenset({"tr", "dt", "dd", "caption", "option"})
_HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
_VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track",
                   "wbr"})
_IMAGE_SOURCES = ("src", "data-src", "data-lazy-src", "data-original")
_NO_ADDRESS = ("#", "data:", "javascript:", "mailto:", "tel:", "blob:", "about:")
# A <main> or the <article>s with less text than this are not taken for the page
MIN_MAIN_CHARS = 500


def _origin(url: str) -> str:
    """The site of an address: 'https://example.com'."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else ""


class _PageReader(HTMLParser):
    """
    A page's HTML as text in the manner of Markdown: headings, paragraphs, lists, links, and
    images with their addresses, so the model can read the page and fetch an image it names.

    - What a page's <main> holds is the page, if it has one (else its <article>s, else all of
      it): the menus around it are left out.
    - A link to the same site is written as its path ("/wiki/Fox"): on pages full of links,
      their addresses are most of the text.
    - A list item that is nothing but a link to the page in another language (hreflang) is
      left out: a wiki article starts with 150 of them.
    """

    def __init__(self, url: str):
        super().__init__(convert_charrefs=True)
        self.url = url
        self.origin = _origin(url)
        self.short_links = False               # Some links are written as paths
        self.title = ""
        self.meta: dict[str, str] = {}
        self._out: list[str] = []
        self._skipped: list[str] = []          # Open elements whose content is left out
        self._in_title = False
        self._pre = 0                          # Inside <pre>: its text is kept as it is
        self._pre_text: list[str] = []
        self._pres: list[str] = []             # The finished <pre> blocks, put back after the cleanup
        self._lists = 0
        self._items: dict[int, int] = {}       # Per list depth: where its open item starts in _out
        self._links: list[tuple[str, int, bool]] = []   # (address, where its text starts in _out, hreflang)
        self._language_links: set[str] = set()     # Links to other languages, as they were written
        self._images: set[str] = set()
        self._main: Optional[list[int]] = None     # Where the first <main> starts and ends in _out
        self._articles: Optional[list[int]] = None  # From the first <article> to the end of the last

    def _break(self, lines: int = 2) -> None:
        """End the line; with lines=2, the paragraph."""
        self._out.append("\n" * lines)

    def address(self, value: Optional[str]) -> Optional[str]:
        """A link's or image's address as a full web address, or None for what is none."""
        value = (value or "").strip()
        if not value or value.startswith(_NO_ADDRESS):
            return None
        try:
            address = urljoin(self.url, value)
        except ValueError:
            return None
        return address if address.startswith(("http://", "https://")) and len(address) <= MAX_URL_CHARS else None

    def handle_starttag(self, tag: str, attrs: list) -> None:
        values = {name: value or "" for name, value in attrs}
        if tag == "meta":
            key = (values.get("property") or values.get("name") or "").lower()
            if key and values.get("content") and key not in self.meta:
                self.meta[key] = " ".join(values["content"].split())
            return
        if tag == "base":
            if values.get("href"):
                self.url = urljoin(self.url, values["href"])
            return
        if self._skipped:
            if tag not in _VOID:
                self._skipped.append(tag)
            return
        if tag == "main" and self._main is None:
            self._main = [len(self._out), -1]
        elif tag == "article" and self._articles is None:
            self._articles = [len(self._out), -1]
        if tag == "title":
            self._in_title = not self.title
        elif tag in _SKIPPED:
            self._skipped.append(tag)
        elif tag == "pre":
            self._pre += 1
        elif self._pre:
            if tag == "br":
                self._pre_text.append("\n")
        elif tag in _HEADINGS:
            self._break()
            self._out.append("#" * _HEADINGS[tag] + " ")
        elif tag == "li":
            self._end_item()
            self._items[self._lists] = len(self._out)
            self._break(1)
            self._out.append("  " * max(self._lists - 1, 0) + "- ")
        elif tag == "br":
            self._break(1)
        elif tag == "hr":
            self._out.append("\n\n---\n\n")
        elif tag in ("td", "th"):
            self._out.append(" | ")
        elif tag == "img":
            self._image(values)
        elif tag == "a":
            address = self.address(values.get("href"))
            if address:
                self._links.append((address, len(self._out), bool(values.get("hreflang"))))
        elif tag in _BLOCKS:
            if tag in ("ul", "ol"):
                self._lists += 1
            self._break()
        elif tag in _LINES:
            self._break(1)

    def _end_item(self) -> None:
        """End the open list item of this depth; one that holds nothing, or only a link to another language, goes."""
        start = self._items.pop(self._lists, None)
        if start is None:
            return
        held = "".join(self._out[start:]).strip().removeprefix("-").strip()
        if not held or held in self._language_links:
            del self._out[start:]

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if self._skipped:
            # Up to the element that started it; an end tag that fits none is ignored
            if tag in self._skipped:
                del self._skipped[len(self._skipped) - 1 - self._skipped[::-1].index(tag):]
            return
        if tag == "main" and self._main and self._main[1] < 0:
            self._main[1] = len(self._out)
        elif tag == "article" and self._articles:
            self._articles[1] = len(self._out)
        if tag == "title":
            self._in_title = False
        elif self._pre:
            if tag == "pre":
                self._pre -= 1
                if not self._pre:
                    self._pres.append("```\n" + "".join(self._pre_text).strip("\n") + "\n```")
                    self._pre_text = []
                    self._out.append(f"\n\n\x00{len(self._pres) - 1}\x00\n\n")
        elif tag in _HEADINGS:
            self._break()
        elif tag == "a":
            if self._links:
                self._link(*self._links.pop())
        elif tag == "li":
            self._end_item()
        elif tag in _BLOCKS:
            if tag in ("ul", "ol"):
                self._end_item()
                self._lists = max(self._lists - 1, 0)
            self._break()

    def handle_data(self, data: str) -> None:
        if self._skipped:
            return
        if self._in_title:
            self.title += data
        elif self._pre:
            self._pre_text.append(data)
        else:
            self._out.append(re.sub(r"\s+", " ", data).replace("\x00", ""))

    def _image(self, values: dict) -> None:
        if values.get("width", "").strip() in ("0", "1") or values.get("height", "").strip() in ("0", "1"):
            return  # A tracking pixel
        source = next((values[name] for name in _IMAGE_SOURCES
                       if values.get(name) and not values[name].startswith("data:")), "")
        if not source:
            # Of a set, the last candidate is the largest ("a.jpg 480w, b.jpg 1200w")
            candidates = [candidate.split() for candidate in values.get("srcset", "").split(",")]
            source = next((candidate[0] for candidate in reversed(candidates) if candidate), "")
        address = self.address(source)
        if not address or address in self._images:
            return
        self._images.add(address)
        alt = " ".join(values.get("alt", "").split())[:120].replace("[", "(").replace("]", ")")
        self._out.append(f" ![{alt}]({address}) ")

    def _link(self, address: str, start: int, language: bool = False) -> None:
        """What a link holds as a Markdown link; a link around several lines or an image gets its address after it."""
        inner = "".join(self._out[start:])
        text = inner.strip()
        if not text:
            del self._out[start:]
        elif "\n" in text or "![" in text:
            self._out.append(f" ([Link]({self._short(address)})) ")
        elif text != address:
            link = f"[{text}]({self._short(address)})"
            if language:
                self._language_links.add(link)
            self._out[start:] = [f"{' ' if inner[:1].isspace() else ''}{link}{' ' if inner[-1:].isspace() else ''}"]

    def _short(self, address: str) -> str:
        """A link's address as it is written: its path for a link to the page's own site."""
        if self.origin and address.startswith(self.origin + "/"):
            self.short_links = True
            return address[len(self.origin):]
        return address

    def text(self) -> str:
        """The text of the page's main part, or of all of it (see the class)."""
        out = self._out
        for scope in (self._main, self._articles):
            if scope:
                inside = out[scope[0]:scope[1] if scope[1] >= 0 else None]
                if sum(map(len, inside)) >= MIN_MAIN_CHARS:
                    out = inside
                    break
        text = re.sub(r"[ \t\r\f\v]+", " ", "".join(out))
        text = re.sub(r" ?\n ?", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return re.sub(r"\x00(\d+)\x00", lambda found: self._pres[int(found.group(1))], text)


@dataclass
class Page:
    """A web page as text."""
    title: str
    description: str
    image: Optional[str]    # The preview image the page names for itself (og:image)
    text: str
    origin: Optional[str] = None    # Set if links to the page's own site are written as paths: the site


def page_text(html: str, url: str) -> Page:
    """
    A page's HTML as text: its title, its description, and what it says with its links and the
    addresses of its images. Scripts don't run, so a page that builds itself in the browser has
    little text; its title, description and preview image are still there.

    Args:
        html: The page.
        url: Its address, which relative links and images are completed with.
    """
    reader = _PageReader(url)
    try:
        reader.feed(html)
        reader.close()
    except Exception as e:  # Whatever a broken page does to the parser: what was read so far counts
        log.info(f"The page at {urlsplit(url).netloc} could not be read to its end: {type(e).__name__}: {e}")
    meta = reader.meta
    title = " ".join((reader.title or meta.get("og:title") or meta.get("twitter:title") or "").split())
    description = meta.get("description") or meta.get("og:description") or meta.get("twitter:description") or ""
    image = reader.address(meta.get("og:image") or meta.get("og:image:url") or meta.get("twitter:image"))
    text = reader.text()
    return Page(title, description, image, text, reader.origin if reader.short_links else None)
