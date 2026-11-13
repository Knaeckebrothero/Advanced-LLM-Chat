"""
Offline test of the tool web_fetch (docs/files.md, "Web addresses"): no API keys, no database,
no internet. A web server on 127.0.0.1 plays the web, a fake file table and a temporary
FILES_DIR take the files.

    python -m backend.llm.tests.test_web_fetch

Covers: which addresses are fetched at all (http and https, public ones only, also when a
name resolves to a private address next to a public one), the connection going to the address
that was checked under the host's name, redirects and their limit, error statuses, the limits
on size and time, the type of a file by its content, a page as text (its main part, links,
images, what is left out), and the tool itself: an image saved to the conversation under its
name and given to a vision model, described for a text-only one, pages and text with reading
on, and what the tool refuses.
"""
import asyncio
import base64
import io
import json
import sys
import tempfile
import threading
import time
import traceback
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from backend.llm.tools import ToolError, ToolText, tools_for_groups
from backend.services import file_store, file_utils, web_fetch as web
from backend.services.file_retrieval_service import get_file_retrieval_service
from backend.services.tools import web_fetch_tools as tool


def png(width: int = 640, height: int = 480) -> bytes:
    return image("PNG", width, height)


def image(kind: str, width: int = 640, height: int = 480, frames: int = 1) -> bytes:
    """An image in a format Pillow writes ("PNG", "WEBP", "AVIF"); with frames, an animation."""
    from PIL import Image
    output = io.BytesIO()
    pictures = [Image.new("RGB", (width, height), (200, 40 * frame, 40)) for frame in range(frames)]
    pictures[0].save(output, kind, **({"save_all": True, "append_images": pictures[1:]} if frames > 1 else {}))
    return output.getvalue()


PAGE = """<!doctype html>
<html><head>
<meta charset="utf-8">
<title>Foxes  of the
 north</title>
<meta name="description" content="All about foxes.">
<meta property="og:image" content="/media/cover.jpg">
<style>body { color: red }</style>
<script>var hidden = "not text";</script>
</head><body>
<nav><a href="/home">Home menu</a></nav>
<div class="banner">Banner words</div>
<main>
<h1>Red fox</h1>
<p>The red fox is <a href="/wiki/Vulpes">a   fox</a> and lives <a href="https://other.example/north">up north</a>.
See <a href="#habitat">below</a> and <a href="javascript:void(0)">here</a>.</p>
<ul>
<li><a href="https://de.example/Rotfuchs" hreflang="de">Deutsch</a></li>
<li>First point
<li>Second <b>point</b></li>
</ul>
<p><img src="media/fox.jpg" alt="A fox [in snow]"><img src="data:image/png;base64,AAAA" alt="inline">
<img src="/pixel.gif" width="1" height="1"><img data-src="//cdn.example/lazy.webp" alt="Lazy">
<img srcset="small.jpg 480w, large.jpg 1200w"><img src="media/fox.jpg" alt="again"></p>
<a href="/gallery"><img src="/thumb.png" alt="Thumb"><h3>Gallery</h3></a>
<pre>def fox():
    return  1</pre>
<table><tr><th>Name</th><th>Size</th></tr><tr><td>Fox</td><td>70 cm</td></tr></table>
<p>""" + ("Long text about foxes. " * 40) + """</p>
</main>
<footer>Footer words</footer>
<noscript><img src="/tracker.gif"></noscript>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    """The web of the test."""

    def log_message(self, *args):
        pass

    def send(self, status: int, mime_type: str = "", body: bytes = b"", **headers):
        self.send_response(status)
        if mime_type:
            self.send_header("Content-Type", mime_type)
        for name, value in headers.items():
            self.send_header(name.replace("_", "-"), value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/page":
            self.send(200, "text/html; charset=utf-8", PAGE.encode())
        elif path == "/latin":
            self.send(200, "text/html", "<html><head><meta charset='iso-8859-1'><title>Füchse</title></head>"
                                        "<body><p>Grüße</p></body></html>".encode("iso-8859-1"))
        elif path == "/empty-page":
            self.send(200, "text/html", b"<html><head><title>App</title><meta property='og:description' "
                                        b"content='An app'></head><body><div id='root'></div>"
                                        b"<script>render()</script></body></html>")
        elif path == "/media/fox.jpeg":
            # A PNG under a JPEG's name and type, as image services send WebP for .jpeg addresses
            self.send(200, "image/jpeg", png())
        elif path == "/optimized/fox.jpeg":
            self.send(200, "image/jpeg", image("WEBP", 2000, 3000))
        elif path == "/moving.webp":
            self.send(200, "image/webp", image("WEBP", 320, 240, frames=3))
        elif path == "/new.avif":
            self.send(200, "application/octet-stream", image("AVIF", 320, 240))
        elif path == "/other/fox.png":
            self.send(200, "image/png", png(320, 200))
        elif path == "/download":
            self.send(200, "application/octet-stream", png(32, 32))
        elif path == "/photo.png":
            self.send(200, "application/octet-stream", png(32, 32))
        elif path == "/login.png":
            self.send(200, "image/png", b"<html><body>Sign in</body></html>")
        elif path == "/paper.pdf":
            self.send(200, "application/octet-stream", b"%PDF-1.4 not really")
        elif path == "/fake.pdf":
            self.send(200, "application/pdf", b"<html>no pdf</html>")
        elif path == "/sound":
            self.send(200, "audio/mpeg", b"ID3 not really sound")
        elif path == "/clip":
            self.send(200, "video/mp4", b"\x00" * 64)
        elif path == "/data.json":
            self.send(200, "application/json", json.dumps({"host": self.headers.get("Host"),
                                                           "agent": self.headers.get("User-Agent"),
                                                           "cookie": self.headers.get("Cookie")}).encode())
        elif path == "/notes.txt":
            self.send(200, "text/plain; charset=utf-8", ("0123456789" * 9000).encode())
        elif path == "/huge.txt":
            self.send(200, "text/plain", b"x" * (web.MAX_TEXT_BYTES + 5000))
        elif path == "/huge.png":
            self.send(200, "image/png", b"\x89PNG" + b"\x00" * (file_store.MAX_TOOL_FILE_SIZE + 10))
        elif path == "/redirect":
            self.send(302, Location="/media/fox.jpeg", Set_Cookie="seen=1")
        elif path == "/redirect-far":
            self.send(307, Location=f"http://localhost:{self.server.server_port}/data.json")
        elif path == "/loop":
            self.send(301, Location="/loop")
        elif path == "/to-file":
            self.send(302, Location="file:///etc/passwd")
        elif path == "/slow":
            time.sleep(3)
            self.send(200, "text/plain", b"late")
        elif path == "/secret":
            self.send(403, "text/html", b"no")
        elif path == "/broken":
            self.send(500, "text/html", b"oops")
        else:
            self.send(404, "text/html", b"nothing")


class FakeFiles:
    """The table uploaded_files, as the file store uses it."""

    def __init__(self):
        self.rows: dict[str, dict] = {}

    def register_uploaded_file(self, file_id, user_id, **values):
        self.rows[file_id] = {"file_id": file_id, "user_id": user_id, **values}

    def get_file(self, file_id):
        return self.rows.get(file_id)

    def delete_uploaded_file(self, file_id):
        self.rows.pop(file_id, None)

    def get_conversation_files(self, conversation_id, user_id):
        return [row for row in self.rows.values()
                if row.get("conversation_id") == conversation_id and row["user_id"] == user_id]


@contextmanager
def local_web(private: bool = True):
    """The test's web server and file store; with private, addresses on this machine may be fetched."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    files = FakeFiles()
    saved = web.ALLOW_PRIVATE_ADDRESSES, file_utils.FILES_DIR, file_store.db
    web.ALLOW_PRIVATE_ADDRESSES = private
    file_utils.FILES_DIR = tempfile.mkdtemp(prefix="web-fetch-test-")
    file_store.db = files
    try:
        yield f"http://127.0.0.1:{server.server_port}", files
    finally:
        web.ALLOW_PRIVATE_ADDRESSES, file_utils.FILES_DIR, file_store.db = saved
        server.shutdown()
        server.server_close()


async def refused(url: str) -> str:
    """The reason an address is not fetched."""
    try:
        found = await web.fetch(url)
    except web.WebFetchError as e:
        return str(e)
    raise AssertionError(f"{url} was fetched: {found.kind} {found.mime_type}")


async def test_only_web_addresses():
    assert web.clean_url("  <https://example.com/a b>".replace(" b", "%20b")) == "https://example.com/a%20b"
    assert web.clean_url("example.com/photo.jpg") == "https://example.com/photo.jpg"
    assert web.clean_url("https://example.com/page#part") == "https://example.com/page"
    assert web.clean_url("'http://example.com:8080/x?y=1'") == "http://example.com:8080/x?y=1"
    for bad in ("", "fox", "ftp://example.com/x", "file:///etc/passwd", "javascript:alert(1)", "https://",
                "https://example.com/a b", "https://user:secret@example.com/", "https://example.com:port/",
                "https://example.com/" + "a" * web.MAX_URL_CHARS):
        try:
            web.clean_url(bad)
        except web.WebFetchError:
            continue
        raise AssertionError(f"accepted: {bad!r}")


async def test_only_public_addresses():
    with local_web(private=False) as (base, _):
        for url in (base + "/page", "http://localhost/", "http://10.0.0.5/", "http://192.168.1.1/x",
                    "http://169.254.169.254/latest/meta-data/", "http://[::1]/", "http://[::ffff:127.0.0.1]/",
                    "http://0.0.0.0/", "http://100.64.0.1/", "http://[fd00::1]/", "http://224.0.0.1/"):
            assert "not a public web address" in await refused(url), url
    assert web._public("93.184.216.34") and web._public("2606:2800:220:1:248:1893:25c8:1946")

    # A name is refused if any of its addresses is private: no picking the one that passes
    loop = asyncio.get_running_loop()
    saved = loop.getaddrinfo

    async def resolve(host, port, **kwargs):
        addresses = {"mixed.test": ["93.184.216.34", "127.0.0.1"], "gone.test": []}.get(host)
        if addresses is None:
            return await saved(host, port, **kwargs)
        return [(2, 1, 6, "", (address, port)) for address in addresses]

    loop.getaddrinfo = resolve
    try:
        assert "not a public web address" in await refused("http://mixed.test/")
        assert "can't be found" in await refused("http://gone.test/")
    finally:
        loop.getaddrinfo = saved


async def test_connects_to_the_checked_address():
    with local_web() as (base, _):
        port = base.rsplit(":", 1)[1]
        loop = asyncio.get_running_loop()
        saved = loop.getaddrinfo
        asked = []

        async def resolve(host, port, **kwargs):
            asked.append(host)
            return [(2, 1, 6, "", ("127.0.0.1", port))] if host == "fox.test" else await saved(host, port, **kwargs)

        loop.getaddrinfo = resolve
        try:
            found = await web.fetch(f"http://fox.test:{port}/data.json")
        finally:
            loop.getaddrinfo = saved
        seen = json.loads(found.as_text())
        # Resolved once, connected to that address, asked for under the host's name; nothing else sent
        assert asked == ["fox.test"], asked
        assert seen == {"host": f"fox.test:{port}", "agent": web.USER_AGENT, "cookie": None}, seen
        assert found.kind == web.TEXT and found.mime_type == "application/json"


async def test_redirects_and_errors():
    with local_web() as (base, _):
        found = await web.fetch(base + "/redirect")
        assert found.url == base + "/media/fox.jpeg" and found.kind == web.FILE, found.url
        # To another host: checked like the first address, and no cookie of the first one goes along
        far = await web.fetch(base + "/redirect-far")
        assert far.url.startswith("http://localhost:") and json.loads(far.as_text())["cookie"] is None
        assert "redirects too often" in await refused(base + "/loop")
        assert "Only http and https" in await refused(base + "/to-file")
        assert "answered 404" in await refused(base + "/missing")
        assert "refused the request (403)" in await refused(base + "/secret")
        assert "answered 500" in await refused(base + "/broken")
        assert "a video" in await refused(base + "/clip")
        assert "can't be reached" in await refused("http://127.0.0.1:9/")
    with local_web(private=False) as (base, _):
        assert "not a public web address" in await refused(base + "/redirect")


async def test_limits():
    with local_web() as (base, _):
        text = await web.fetch(base + "/huge.txt")
        assert not text.complete and len(text.data) == web.MAX_TEXT_BYTES
        # A file may be as large as a tool's file, which is more than an upload
        assert "larger than 32.0 MB" in await refused(base + "/huge.png")
        saved = web.TOTAL_TIMEOUT
        web.TOTAL_TIMEOUT = 0.5
        try:
            started = time.monotonic()
            assert "didn't answer in time" in await refused(base + "/slow")
            assert time.monotonic() - started < 2
        finally:
            web.TOTAL_TIMEOUT = saved


async def test_a_file_is_what_its_content_says():
    with local_web() as (base, _):
        image = await web.fetch(base + "/media/fox.jpeg")
        assert (image.kind, image.mime_type) == (web.FILE, "image/png")
        # No type worth the name: by the address's ending, then by the content
        assert (await web.fetch(base + "/photo.png")).mime_type == "image/png"
        assert (await web.fetch(base + "/paper.pdf")).mime_type == "application/pdf"
        assert (await web.fetch(base + "/sound")).mime_type == "audio/mpeg"
        assert "a file of the type application/octet-stream" in await refused(base + "/download")
        assert "no image that can be read (a web page" in await refused(base + "/login.png")
        assert "says it is a PDF" in await refused(base + "/fake.pdf")
    assert web.file_stem("https://x.test/a/width=450/8271634.jpeg?sig=1") == "8271634"
    assert web.file_stem("https://x.test/Red%20fox%20(1).JPG") == "Red-fox-1"
    assert web.file_stem("https://x.test/") == "web" and web.file_stem("https://x.test/%E7%8B%90.png") == "web"


async def test_a_page_as_text():
    page = web.page_text(PAGE, "https://foxes.example/wiki/Red_fox")
    text = page.text
    assert page.title == "Foxes of the north" and page.description == "All about foxes."
    assert page.image == "https://foxes.example/media/cover.jpg" and page.origin == "https://foxes.example"
    # The main part only, without what is no text
    for left_out in ("Home menu", "Banner words", "Footer words", "not text", "color: red", "tracker", "Deutsch",
                     "pixel.gif", "data:image", "javascript:"):
        assert left_out not in text, left_out
    assert text.startswith("# Red fox\n\nThe red fox is [a fox](/wiki/Vulpes) and lives "
                           "[up north](https://other.example/north). See below and here."), text[:200]
    assert "\n- First point\n- Second point\n" in text, text
    # Images with their full addresses, each once; a set's largest; one loaded later by a script
    assert "![A fox (in snow)](https://foxes.example/wiki/media/fox.jpg)" in text
    assert text.count("media/fox.jpg") == 1 and "again" not in text
    assert "![Lazy](https://cdn.example/lazy.webp)" in text
    assert "![](https://foxes.example/wiki/large.jpg)" in text and "small.jpg" not in text
    # A link around an image and a heading: its address after them
    assert "![Thumb](https://foxes.example/thumb.png)" in text and "### Gallery\n\n([Link](/gallery))" in text
    assert "```\ndef fox():\n    return  1\n```" in text
    assert "| Name | Size\n| Fox | 70 cm" in text, text

    # Without a main part: all of it; a page that is built by scripts has no text
    plain = web.page_text("<p>One<br>two</p><p>Three &amp; four</p><article>Short</article>", "https://x.test/")
    assert plain.text == "One\ntwo\n\nThree & four\n\nShort" and plain.title == "" and plain.origin is None
    assert web.page_text("<<<not html &&& <p", "https://x.test/").text == "<<"
    assert web.decode_text("Grüße".encode("iso-8859-1"), "iso-8859-1") == "Grüße"
    assert web.decode_text("Grüße".encode(), "no-such-charset") == "Grüße"


async def test_the_tool_reads_pages_and_text():
    with local_web() as (base, files):
        scope = {"user_id": 1, "conversation_id": "conv-1", "answer_id": 77}
        page = await tool.web_fetch(base + "/page", **scope)
        assert not isinstance(page, ToolText) and not files.rows
        assert page.startswith(f"Web page: {base}/page\nTitle: Foxes of the north\nDescription: All about foxes.\n"
                               f"Preview image: {base}/media/cover.jpg\nLinks that start with / are on {base}\n\n"
                               f"# Red fox"), page[:300]
        assert f"![A fox (in snow)]({base}/media/fox.jpg)" in page
        assert "Füchse" in await tool.web_fetch(base + "/latin", **scope)
        app = await tool.web_fetch(base + "/empty-page", **scope)
        assert "Title: App" in app and "Description: An app" in app and "built in the browser by scripts" in app

        # A long text in parts
        first = await tool.web_fetch(base + "/notes.txt", **scope)
        assert first.startswith(f"text/plain at {base}/notes.txt:\n\n0123456789")
        assert first.endswith("[... cut off at character 40000 of 90000. To read on, call web_fetch with the same "
                              "address and start=40000.]")
        last = await tool.web_fetch(base + "/notes.txt", start=80000, **scope)
        assert "[From character 80000 of 90000]\n\n0123456789" in last and "cut off" not in last
        assert "Nothing from character 90000 on" in await tool.web_fetch(base + "/notes.txt", start=90000, **scope)
        assert "Only the first 2.0 MB were read" in await tool.web_fetch(base + "/huge.txt", **scope)

        for url, reason in ((base + "/missing", "answered 404"), ("not an address", "not a web address"),
                            (base + "/clip", "a video")):
            try:
                await tool.web_fetch(url, **scope)
            except ToolError as e:
                assert reason in str(e), e
            else:
                raise AssertionError(f"fetched: {url}")


async def test_the_tool_saves_files_to_the_conversation():
    service = get_file_retrieval_service()
    saved_describe = service._get_image_description

    async def describe(file_id, file_path, mime_type, query=None):
        return "A fox in the snow"

    service._get_image_description = describe
    try:
        with local_web() as (base, files):
            scope = {"user_id": 1, "conversation_id": "conv-1", "answer_id": 77}
            seen = await tool.web_fetch(base + "/media/fox.jpeg", vision=True, **scope)
            assert isinstance(seen, ToolText) and len(files.rows) == 1
            row = next(iter(files.rows.values()))
            # Saved like any file a tool creates, under its own name and with its real type
            assert row["name"] == "fox.png" and row["mime_type"] == "image/png", row
            assert (row["conversation_id"], row["message_id"], row["source"]) == ("conv-1", 77, "tool")
            assert row["origin"] == "Web: 127.0.0.1" and json.loads(row["details"]) == {"url": base + "/media/fox.jpeg"}
            assert (row["width"], row["height"]) == (640, 480)
            assert seen.metadata == {"files": [{"fileId": row["file_id"], "name": "fox.png", "mimeType": "image/png",
                                                "size": row["size_bytes"], "width": 640, "height": 480}]}
            assert seen.startswith(f"Fetched {base}/media/fox.jpeg: \"fox.png\" (image/png, 640×480 px, ")
            assert "The image follows." in seen and "![what it shows](fox.png)" in seen
            # The vision model gets the image itself
            (image,) = seen.images
            data = base64.b64decode(image["image_url"]["url"].split(",", 1)[1])
            assert image["image_url"]["url"].startswith("data:image/jpeg;base64,") and data[:2] == b"\xff\xd8"

            # A text-only model gets a description; a second file of that name gets a number
            told = await tool.web_fetch(base + "/other/fox.png", **scope)
            assert not told.images and "What a vision model says it shows:\nA fox in the snow" in told
            assert sorted(row["name"] for row in files.rows.values()) == ["fox-2.png", "fox.png"]
            assert "![what it shows](fox-2.png)" in told

            # The same file again (here by another address, in a later answer): not saved twice
            again = await tool.web_fetch(base + "/redirect", vision=True, **{**scope, "answer_id": 78})
            assert len(files.rows) == 2 and again.images and again.metadata == seen.metadata
            assert again.startswith(f"Fetched {base}/redirect: \"fox.png\"") and row["message_id"] == 77
            # What is recorded is the address that was asked for, not where it led
            files.rows.clear()
            await tool.web_fetch(base + "/redirect", **scope)
            (led,) = files.rows.values()
            assert json.loads(led["details"]) == {"url": base + "/redirect"} and led["name"] == "fox.png"

            # Every format the store reads: WebP (which image services send under a .jpeg address), one
            # that moves, AVIF. Each is saved under its real type, and the model gets a JPEG of it
            files.rows.clear()
            for path, name, mime_type, sent in (("/optimized/fox.jpeg", "fox.webp", "image/webp", (1045, 1568)),
                                                ("/moving.webp", "moving.webp", "image/webp", (320, 240)),
                                                ("/new.avif", "new.avif", "image/avif", (320, 240))):
                shown = await tool.web_fetch(base + path, vision=True, **scope)
                kept = next(row for row in files.rows.values() if row["name"] == name)
                assert kept["mime_type"] == mime_type and file_utils.get_file_path(kept["file_id"]).suffix == \
                    "." + name.split(".")[1], kept
                from PIL import Image
                with Image.open(io.BytesIO(base64.b64decode(shown.images[0]["image_url"]["url"].split(",", 1)[1]))) as got:
                    assert (got.format, got.size) == ("JPEG", sent), (name, got.format, got.size)
                assert file_store.thumbnail(kept["file_id"], "small"), name
            files.rows.clear()
            await tool.web_fetch(base + "/redirect", **scope)

            sound = await tool.web_fetch(base + "/sound", **scope)
            assert "\"sound.mp3\" (audio/mpeg" in sound and "![what it is](sound.mp3)" in sound and not sound.images

            # Without a conversation there is no place for a file; a page needs none
            for missing in ({"user_id": 1}, {"conversation_id": "conv-1"}):
                try:
                    await tool.web_fetch(base + "/media/fox.jpeg", **missing)
                except ToolError as e:
                    assert "no conversation to save it in" in str(e)
                else:
                    raise AssertionError("saved without a conversation")
                assert "# Red fox" in await tool.web_fetch(base + "/page", **missing)
            assert len(files.rows) == 2
    finally:
        service._get_image_description = saved_describe


async def test_the_tool_is_bound_to_its_answer():
    with local_web() as (base, files):
        registry = tools_for_groups(["web_fetch"], user_id=5, conversation={"id": "conv-9"}, vision=True,
                                    answer_id=1234)
        assert registry.names() == ["web_fetch"] and registry.title("web_fetch") == "Opening Web Address"
        schema = registry.get("web_fetch").parameters
        # The model names the address, nothing else: not the user, the conversation or the answer
        assert set(schema["properties"]) == {"url", "start"} and schema["required"] == ["url"]
        assert "you also get to see yourself" in registry.get("web_fetch").description
        result = await registry.call("web_fetch", {"url": base + "/media/fox.jpeg", "conversation_id": "conv-1"})
        row = next(iter(files.rows.values()))
        assert (row["user_id"], row["conversation_id"], row["message_id"]) == (5, "conv-9", 1234) and result.images
        text_only = tools_for_groups(["web_fetch"], user_id=5, conversation={"id": "conv-9"})
        assert "a description written by a vision model" in text_only.get("web_fetch").description
        page = await registry.call("web_fetch", {"url": base + "/notes.txt", "start": "80000"})
        assert "[From character 80000 of 90000]" in page


TESTS = [
    test_only_web_addresses,
    test_only_public_addresses,
    test_connects_to_the_checked_address,
    test_redirects_and_errors,
    test_limits,
    test_a_file_is_what_its_content_says,
    test_a_page_as_text,
    test_the_tool_reads_pages_and_text,
    test_the_tool_saves_files_to_the_conversation,
    test_the_tool_is_bound_to_its_answer,
]


async def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            await test()
            print(f"PASS  {test.__name__}")
        except Exception:
            failures += 1
            print(f"FAIL  {test.__name__}")
            traceback.print_exc()
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
