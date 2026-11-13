#!/usr/bin/env python3
"""
Test that a hostile upload can't take the server down (docs/files.md, "Limits"). Offline: no
database, no API key, no model; the files directory is a temporary one.

It builds its files itself: PDFs written by hand (normal pages, pages of 89 and 200 inches,
pages of curves that take poppler minutes, a page of characters that takes pdfminer gigabytes),
PNGs that claim millions of pixels in a few hundred KB, JPEGs made with Pillow. Covers:

- PDFs (document_handler.process_pdf_safely(), pdf_worker.py): a normal PDF gets its text and
  its pages as before, at 150 dpi; at most 20 pages and a bounded text, with a note; a PDF that
  only the renderer fails on keeps its text; pages of any size on paper cost what an A4 page
  costs, in time, in pixels and in the memory of this process and of the worker; a PDF over
  its time or memory limit ends in an error, quickly, with nothing left behind and no process
  left running, and the next PDF works; the limits reach the renderer the worker starts; the
  event loop keeps running while a PDF is processed in a thread; at most two PDFs are
  processed at once, the next ones wait, and beyond that they are refused; a tool's PDF takes
  the same way (file_store.save_tool_file()).
- Images (file_store.py): image_size() reads only the header; an image over the pixel cap gets
  no preview and no copy for a model, at once and without being decoded; a camera's JPEG of 50
  megapixels gets both, decoded at a fraction of its size, but a progressive one does not;
  normal images come out as before, turned by their EXIF data; decodes at once are limited.
- Local Whisper (audio_handler.py): with WHISPER_LOCAL_FALLBACK=false no model is loaded,
  unless USE_LOCAL_WHISPER forces it; the local model is loaded and run off the event loop,
  one transcription at a time (a fake whisper module: nothing is downloaded).

    python backend/services/tests/upload_safety_test.py

Exit code 0 if every check passed.
"""
import asyncio
import io
import json
import logging
import os
import re
import resource
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import types
import warnings
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Every module reads FILES_DIR from the configuration when it is imported: set before that
FILES_DIR = Path(tempfile.mkdtemp(prefix="upload-safety-test-"))
os.environ["FILES_DIR"] = str(FILES_DIR)

from PIL import Image  # noqa: E402

from backend import config  # noqa: E402
from backend.services import audio_handler, document_handler, file_store  # noqa: E402
from backend.services.document_handler import (MAX_PDF_PAGES, MAX_PDF_WAITING, MAX_PDF_WORKERS,  # noqa: E402
                                               PDF_PAGE_EDGE, process_pdf_safely)

MB = 1024 * 1024
A4 = (595, 842)


# =========================================================================
# Test files
# =========================================================================

def make_pdf(pages: list[tuple[float, float, str]]) -> bytes:
    """A PDF with one page per (width, height, content stream), sizes in points; streams are compressed."""
    objects = {1: b"<< /Type /Catalog /Pages 2 0 R >>",
               3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"}
    kids = []
    for index, (width, height, content) in enumerate(pages):
        number = 4 + 2 * index  # The page, then its content
        data = zlib.compress(content.encode("latin-1"))
        kids.append(number)
        objects[number] = (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] "
                           f"/Resources << /Font << /F1 3 0 R >> >> /Contents {number + 1} 0 R >>").encode()
        objects[number + 1] = (f"<< /Length {len(data)} /Filter /FlateDecode >>\nstream\n".encode()
                               + data + b"\nendstream")
    objects[2] = f"<< /Type /Pages /Count {len(kids)} /Kids [{' '.join(f'{kid} 0 R' for kid in kids)}] >>".encode()
    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number in sorted(objects):
        offsets.append(len(pdf))
        pdf += f"{number} 0 obj\n".encode() + objects[number] + b"\nendobj\n"
    xref = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    pdf += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    pdf += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(pdf)


def text_page(number: int, size: tuple[float, float] = A4, lines: int = 40) -> tuple[float, float, str]:
    rows = "\n".join(f"(Page {number} line {line}: the quick brown fox jumps over the lazy dog.) Tj T*"
                     for line in range(1, lines + 1))
    return (*size, f"BT /F1 11 Tf 14 TL 56 {size[1] - 60} Td\n{rows}\nET")


def huge_page(number: int, inches: int) -> tuple[float, float, str]:
    """A page of inches x inches: at 150 dpi, 89 inches are 178 megapixels."""
    side = inches * 72
    return (side, side, f"0.2 0.4 0.8 rg 0 0 {side} {side} re f\n"
                        f"BT /F1 {side // 8} Tf {side // 10} {side // 2} Td (Huge page {number}) Tj ET")


def slow_pdf() -> bytes:
    """220 KB that poppler renders for minutes: 20,000 curves on each page."""
    curves = "\n".join(f"{i % 595} 0 m {i * 7 % 595} 300 {i * 13 % 595} 600 {i * 3 % 595} 842 c S"
                       for i in range(20000))
    return make_pdf([(*A4, f"0.3 w\n{curves}")] * 3)


def hungry_pdf() -> bytes:
    """3 KB that pdfminer needs hundreds of MB for: 150,000 characters on one page, each its own object."""
    characters = "\n".join("(a) Tj" if i % 140 else "T* (a) Tj" for i in range(150_000))
    return make_pdf([(*A4, f"BT /F1 4 Tf 3 TL 10 830 Td\n{characters}\nET")])


def flat_png(width: int, height: int, alpha: bool = True) -> bytes:
    """A PNG of one colour, written without holding its pixels: any size in a few hundred KB."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    row = b"\x00" * (1 + width * (4 if alpha else 3))
    compressor = zlib.compressobj(6)
    pixels = b"".join(compressor.compress(row * min(64, height - done)) for done in range(0, height, 64))
    header = struct.pack(">IIBBBBB", width, height, 8, 6 if alpha else 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", pixels + compressor.flush())
            + chunk(b"IEND", b""))


ORANGE = (200, 120, 40)


def picture(width: int, height: int, image_format: str, mode: str = "RGB", **options) -> bytes:
    """An image of one colour made with Pillow."""
    output = io.BytesIO()
    colour = {"RGB": ORANGE, "RGBA": (*ORANGE, 128), "L": 128}[mode]
    Image.new(mode, (width, height), colour).save(output, image_format, **options)
    return output.getvalue()


def is_orange(image, position: tuple[int, int]) -> bool:
    """Whether a pixel still has the colour of picture(), give or take what lossy formats change."""
    return all(abs(got - want) <= 6 for got, want in zip(image.convert("RGB").getpixel(position), ORANGE))


def put(data: bytes, extension: str) -> tuple[str, Path]:
    """Store a file as an upload is stored: <file ID><extension> in the files directory."""
    file_id = file_store.new_file_id()
    path = FILES_DIR / f"{file_id}{extension}"
    path.write_bytes(data)
    return file_id, path


def derived(file_id: str) -> list[str]:
    """What is in the files directory for a file besides the file itself."""
    return sorted(path.name[len(file_id):] for path in FILES_DIR.iterdir()
                  if path.name.startswith(file_id) and path.stem != file_id)


def page_sizes(result: dict) -> list[tuple[int, int]]:
    sizes = []
    for path in result["page_paths"]:
        with Image.open(path) as image:
            sizes.append(image.size)
    return sizes


# =========================================================================
# Measuring
# =========================================================================

class OwnMemory:
    """
    How far this process's memory rose in a block, in MB: `with OwnMemory() as memory: ...`,
    then memory.rise. On Linux the peak is reset first, so each block is measured on its own;
    elsewhere it is the rise of the peak of the whole run.
    """

    def __enter__(self):
        try:
            Path("/proc/self/clear_refs").write_text("5")  # Resets the peak (VmHWM) to the current size
            self.start = self._status("VmRSS")
        except OSError:
            self.start = None
            self.before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        return self

    def __exit__(self, *error):
        if self.start is not None:
            self.rise = self._status("VmHWM") - self.start
        else:
            self.rise = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 - self.before

    @staticmethod
    def _status(key: str) -> float:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith(key + ":"):
                return int(line.split()[1]) / 1024
        raise OSError(key)


def largest_child() -> float:
    """
    The most memory a finished child process of this one ever had (a worker, or its renderer),
    in MB. Never less than this process had when it started the child: Linux counts that for a
    child until it has become its own program.
    """
    return resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024


class Ticker:
    """
    Whether the event loop keeps running: a task that sleeps 10 ms at a time and notes by how
    much it woke up late. `async with Ticker() as ticker: ...`, then ticker.worst (seconds).
    """
    STEP = 0.01

    async def __aenter__(self):
        self.worst, self.ticks = 0.0, 0
        self._task = asyncio.create_task(self._tick())
        await asyncio.sleep(0)
        return self

    async def __aexit__(self, *error):
        self._task.cancel()

    async def _tick(self):
        loop = asyncio.get_running_loop()
        while True:
            before = loop.time()
            await asyncio.sleep(self.STEP)
            self.worst = max(self.worst, loop.time() - before - self.STEP)
            self.ticks += 1


def processes_in_files_dir() -> list[str]:
    """The command lines of running processes that name the files directory: workers and renderers (Linux)."""
    found = []
    for entry in Path("/proc").glob("[0-9]*"):
        try:
            command = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            continue
        if str(FILES_DIR) in command and int(entry.name) != os.getpid():
            found.append(command)
    return found


# =========================================================================
# PDFs
# =========================================================================

async def test_normal_pdf():
    """A normal PDF: text and pages as before, a page at 150 dpi."""
    letter = (612, 792)
    file_id, path = put(make_pdf([text_page(n) for n in range(1, 5)] + [text_page(5, letter)]), ".pdf")
    started = time.monotonic()
    result = process_pdf_safely(path, file_id)
    elapsed = time.monotonic() - started
    assert result["error"] is None and result["page_count"] == 5, result
    assert [p.name for p in result["page_paths"]] == [f"{file_id}_page_{n}.png" for n in range(1, 6)], result
    assert result["text_path"] == FILES_DIR / f"{file_id}_text.txt", result
    assert derived(file_id) == sorted([f"_page_{n}.png" for n in range(1, 6)] + ["_text.txt"]), derived(file_id)
    # A4 at 150 dpi is 1240 x 1754; every page has that longer edge (the last pixel is poppler's rounding)
    sizes = page_sizes(result)
    assert sizes[:4] == [(1240, 1754)] * 4, sizes
    assert sizes[4][1] == 1754 and abs(sizes[4][0] - 1754 * 612 / 792) <= 1, sizes
    text = result["text_path"].read_text(encoding="utf-8")
    assert text.startswith("--- Page 1 ---\nPage 1 line 1: the quick brown fox"), text[:200]
    assert "Page 5 line 40:" in text
    assert "[Note" not in text
    # As the rest of the backend finds them
    assert document_handler.get_extracted_text(file_id) == text
    assert document_handler.get_pdf_page_paths(file_id) == result["page_paths"]
    prepared = document_handler.prepare_document_for_llm(file_id, "application/pdf")
    assert prepared["text"] == text and len(prepared["images"]) == 5
    # process_pdf() is what the worker runs: the same result, in this process
    other_id, other = put(path.read_bytes(), ".pdf")
    direct = document_handler.process_pdf(other, other_id)
    assert direct["error"] is None and direct["page_count"] == 5 and page_sizes(direct) == sizes, direct
    assert direct["text_path"].read_text(encoding="utf-8") == text and derived(other_id) == derived(file_id)
    # A path given from the working directory, as FILES_DIR usually is: the outputs are named the same way
    relative_id, absolute = put(make_pdf([text_page(1)]), ".pdf")
    relative = Path(os.path.relpath(absolute))
    result = process_pdf_safely(relative, relative_id)
    assert result["page_paths"] == [relative.parent / f"{relative_id}_page_1.png"], result
    assert result["text_path"] == relative.parent / f"{relative_id}_text.txt" and result["text_path"].is_file()
    # No PDF at all: an error, nothing kept, no exception
    file_id, path = put(b"This is not a PDF.", ".pdf")
    result = process_pdf_safely(path, file_id)
    assert result["error"] and result["page_count"] == 0 and result["text_path"] is None, result
    assert derived(file_id) == []
    return f"5 pages in {elapsed:.1f} s"


async def test_page_and_text_limits():
    """At most MAX_PDF_PAGES pages and MAX_PDF_TEXT_CHARS characters, with a note of what is missing."""
    file_id, path = put(make_pdf([text_page(n, lines=3) for n in range(1, MAX_PDF_PAGES + 6)]), ".pdf")
    result = process_pdf_safely(path, file_id)
    assert result["error"] is None and result["page_count"] == MAX_PDF_PAGES, result
    assert len(derived(file_id)) == MAX_PDF_PAGES + 1
    text = result["text_path"].read_text(encoding="utf-8")
    assert f"Page {MAX_PDF_PAGES} line 3" in text and f"Page {MAX_PDF_PAGES + 1} line" not in text
    note = f"[Note: Document truncated. Showing {MAX_PDF_PAGES} of {MAX_PDF_PAGES + 5} pages]"
    assert text.endswith(note), text[-120:]

    # The text limit, in this process with a small limit (a PDF of 500,000 characters takes a while)
    saved = document_handler.MAX_PDF_TEXT_CHARS
    document_handler.MAX_PDF_TEXT_CHARS = 3000
    try:
        text = document_handler.extract_pdf_text(path)
    finally:
        document_handler.MAX_PDF_TEXT_CHARS = saved
    body, note = text.rsplit("\n\n\n", 1)
    cut = re.fullmatch(r"\[Note: Document truncated\. Showing the first 3000 characters of its text, "
                       rf"up to page (\d+) of {MAX_PDF_PAGES + 5}\]", note)
    assert cut, note
    last = int(cut.group(1))
    assert 1 < last < MAX_PDF_PAGES and f"--- Page {last} ---" in body and f"--- Page {last + 1} ---" not in body
    assert 2900 < len(body) <= 3000 + 2 * last, len(body)  # The pages' texts, joined by blank lines


async def test_pages_take_only_so_much():
    """The page images of one PDF have a size together; the pages past it are not kept."""
    file_id, path = put(make_pdf([text_page(n) for n in range(1, 7)]), ".pdf")
    whole = process_pdf_safely(path, file_id)
    sizes = [page.stat().st_size for page in whole["page_paths"]]
    assert len(sizes) == 6, whole
    original = document_handler.MAX_PDF_PAGES_BYTES
    document_handler.MAX_PDF_PAGES_BYTES = sum(sizes[:3]) + 1  # Room for three pages and a byte
    try:
        other_id, other = put(path.read_bytes(), ".pdf")
        result = process_pdf_safely(other, other_id)
    finally:
        document_handler.MAX_PDF_PAGES_BYTES = original
    assert result["error"] is None and result["page_count"] == 3, result
    assert derived(other_id) == sorted([f"_page_{n}.png" for n in range(1, 4)] + ["_text.txt"]), derived(other_id)
    assert "Page 6 line 40:" in result["text_path"].read_text(encoding="utf-8"), "the text is whole"


async def test_worker_gets_no_settings():
    """The process that opens anybody's PDFs gets none of the server's keys and passwords."""
    secrets_set = {"OPENAI_API_KEY": "sk-test", "POSTGRES_PASSWORD": "pw", "ENCRYPTION_KEY": "key",
                   "MODEL_ROUTER_KEY": "router"}
    before = {name: os.environ.get(name) for name in secrets_set}
    os.environ.update(secrets_set)
    try:
        environment = document_handler._worker_environment()
        assert not set(environment) & set(secrets_set), sorted(environment)
        assert set(environment) <= {*document_handler._WORKER_ENVIRONMENT, "PYTHON_DOTENV_DISABLED"}, sorted(environment)
        assert environment["PATH"] == os.environ["PATH"] and environment["PYTHON_DOTENV_DISABLED"] == "1"
        # And it still does its work with only that
        file_id, path = put(make_pdf([text_page(1)]), ".pdf")
        result = process_pdf_safely(path, file_id)
        assert result["error"] is None and result["page_count"] == 1 and result["text_path"], result
    finally:
        for name, value in before.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


async def test_one_step_fails():
    """A PDF that one of the two steps fails on keeps the other's result: that is not running out of memory."""
    file_id, path = put(make_pdf([text_page(1)]), ".pdf")
    # Without poppler there are no pages. The memory limit is below what this process holds: what
    # counts for a worker is its own memory, not what the server held when it started it
    if sys.platform == "linux":
        assert OwnMemory._status("VmRSS") > 64, "this process is too small to tell"
    saved = os.environ["PATH"]
    os.environ["PATH"] = str(FILES_DIR)
    try:
        result = process_pdf_safely(path, file_id, memory_limit=64 * MB)
    finally:
        os.environ["PATH"] = saved
    assert result["error"] == "pages not rendered: RuntimeError: pdftoppm is not installed (poppler-utils)", result
    assert result["page_count"] == 0 and result["text_path"].read_text(encoding="utf-8").startswith("--- Page 1 ---")
    assert derived(file_id) == ["_text.txt"], derived(file_id)


async def test_huge_pages():
    """The audit's PDF: pages of 89 inches cost what A4 pages cost, here and in the worker."""
    # 15 pages of 89 x 89 inches are 178 megapixels each at 150 dpi: just what Pillow still loads.
    # Rendering them in the server took 53 s and 10 GB
    file_id, path = put(make_pdf([huge_page(n, 89) for n in range(1, 16)]), ".pdf")
    with OwnMemory() as memory:
        started = time.monotonic()
        result = process_pdf_safely(path, file_id)
        elapsed = time.monotonic() - started
    assert result["error"] is None and result["page_count"] == 15, result
    sizes = page_sizes(result)
    assert all(max(size) <= PDF_PAGE_EDGE + 1 and min(size) >= PDF_PAGE_EDGE - 1 for size in sizes), sizes
    assert "Huge page 15" in result["text_path"].read_text(encoding="utf-8")
    assert elapsed < 20, f"{elapsed:.1f} s"
    assert memory.rise < 30, f"this process grew by {memory.rise:.0f} MB"
    assert largest_child() < 200, f"a worker took {largest_child():.0f} MB"
    assert sum(path.stat().st_size for path in result["page_paths"]) < 15 * MB

    # 200 x 200 inches, the largest page a PDF can have: poppler gave up on these at 150 dpi
    file_id, path = put(make_pdf([huge_page(n, 200) for n in range(1, 4)]), ".pdf")
    result = process_pdf_safely(path, file_id)
    assert result["error"] is None and page_sizes(result) == [(PDF_PAGE_EDGE, PDF_PAGE_EDGE)] * 3, result
    return (f"15 pages of 89 inches in {elapsed:.1f} s, this process +{memory.rise:.0f} MB, "
            f"no child above {largest_child():.0f} MB")


async def test_time_limit():
    """A PDF that takes too long: stopped with its renderer, nothing left, the next one works."""
    file_id, path = put(slow_pdf(), ".pdf")
    started = time.monotonic()
    result = process_pdf_safely(path, file_id, timeout=1.5)
    elapsed = time.monotonic() - started
    assert result == {"text_path": None, "page_paths": [], "page_count": 0,
                      "error": "took longer than 1.5 seconds"}, result
    assert elapsed < 4, f"{elapsed:.1f} s"
    assert derived(file_id) == [], derived(file_id)
    if sys.platform == "linux":
        # The time was up while pdftoppm ran, a child of the worker: both are gone (once the
        # kernel has taken them away)
        deadline = time.monotonic() + 2
        while processes_in_files_dir() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert processes_in_files_dir() == [], processes_in_files_dir()
    file_id, path = put(make_pdf([text_page(1)]), ".pdf")
    assert process_pdf_safely(path, file_id)["page_count"] == 1
    return f"stopped after {elapsed:.1f} s"


def out_of_memory(result: dict, megabytes: int) -> bool:
    """
    Whether a result says that the worker ran out of memory. The worker says so itself when it
    can; Python 3.11 sometimes can't go on without memory and aborts, which ends the same way.
    """
    return result["error"] in (f"needs more than {megabytes} MB of memory", "the worker failed (SIGABRT)")


async def test_memory_limit():
    """A PDF that takes too much memory: the worker ends, nothing is kept, the next one works."""
    file_id, path = put(hungry_pdf(), ".pdf")
    with OwnMemory() as memory:
        started = time.monotonic()
        result = process_pdf_safely(path, file_id, memory_limit=64 * MB)
        elapsed = time.monotonic() - started
    assert result == {"text_path": None, "page_paths": [], "page_count": 0,
                      "error": result["error"]} and out_of_memory(result, 64), result
    assert elapsed < 20, f"{elapsed:.1f} s"
    # Its page was rendered before the text ran out of memory: not kept either
    assert derived(file_id) == [], derived(file_id)
    assert memory.rise < 30, f"this process grew by {memory.rise:.0f} MB"
    # What it allocates is limited, not all it maps: the interpreter and its libraries come on top
    assert largest_child() < 64 + 100, f"the worker took {largest_child():.0f} MB"
    # Wherever the memory runs out, it is the whole PDF that fails, never only its text
    for megabytes in (40, 100):
        file_id, path = put(hungry_pdf(), ".pdf")
        result = process_pdf_safely(path, file_id, memory_limit=megabytes * MB)
        assert out_of_memory(result, megabytes) and result["page_count"] == 0 and derived(file_id) == [], result
    # pdfplumber hands on what pdfminer raises inside an error of its own
    try:
        try:
            raise MemoryError()
        except Exception as inner:
            raise RuntimeError(inner)
    except Exception as wrapped:
        assert document_handler._is_out_of_memory(wrapped)
    assert not document_handler._is_out_of_memory(ValueError("a broken PDF"))
    file_id, path = put(make_pdf([text_page(1)]), ".pdf")
    assert process_pdf_safely(path, file_id)["text_path"] is not None
    return f"ended after {elapsed:.1f} s, no child above {largest_child():.0f} MB"


async def test_limits_reach_the_renderer():
    """The limits the worker sets on itself hold for the processes it starts."""
    if sys.platform != "linux":
        return "skipped: not Linux"
    # A process that limits itself as the worker does, and asks a child of its own for its limits
    child = ("import json, resource; print(json.dumps({name: resource.getrlimit(getattr(resource, name)) "
             "for name in ('RLIMIT_DATA', 'RLIMIT_AS', 'RLIMIT_CPU', 'RLIMIT_CORE')}))")
    script = ("import subprocess, sys\n"
              "from backend.services.pdf_worker import limit_resources\n"
              "limit_resources(100 * 1024 * 1024, 7)\n"
              f"sys.exit(subprocess.run([sys.executable, '-c', {child!r}]).returncode)\n")
    done = subprocess.run([sys.executable, "-c", script], cwd=PROJECT_ROOT, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    limits = json.loads(done.stdout)
    assert limits["RLIMIT_DATA"] == [100 * MB, 100 * MB] and limits["RLIMIT_CPU"] == [7, 7], limits
    assert limits["RLIMIT_CORE"] == [0, 0], limits
    assert limits["RLIMIT_AS"][0] == limits["RLIMIT_AS"][1] > 100 * MB, limits


async def test_event_loop_stays_free():
    """While a PDF is processed in a thread, the event loop runs."""
    file_id, path = put(make_pdf([huge_page(n, 89) for n in range(1, 16)]), ".pdf")
    async with Ticker() as ticker:
        started = time.monotonic()
        result = await asyncio.to_thread(process_pdf_safely, path, file_id)
        elapsed = time.monotonic() - started
    assert result["page_count"] == 15, result
    assert ticker.ticks > elapsed / Ticker.STEP / 2, f"{ticker.ticks} ticks in {elapsed:.1f} s"
    assert ticker.worst < 0.2, f"the loop stood still for {ticker.worst * 1000:.0f} ms"
    return f"{elapsed:.1f} s of processing, the loop was at most {ticker.worst * 1000:.0f} ms late"


async def test_queue():
    """At most MAX_PDF_WORKERS PDFs at once; the next wait their turn; beyond MAX_PDF_WAITING they are refused."""
    line = MAX_PDF_WORKERS + MAX_PDF_WAITING
    files = [put(make_pdf([text_page(1), text_page(2)]), ".pdf") for _ in range(line + 2)]
    run_worker = document_handler._run_worker
    gate, lock = threading.Event(), threading.Lock()
    running = most = 0

    def counted(*arguments):
        nonlocal running, most
        with lock:
            running += 1
            most = max(most, running)
        try:
            gate.wait(30)  # Nobody finishes before all have asked
            return run_worker(*arguments)
        finally:
            with lock:
                running -= 1

    document_handler._run_worker = counted
    try:
        with ThreadPoolExecutor(len(files)) as threads:
            futures = [threads.submit(process_pdf_safely, path, file_id) for file_id, path in files]
            deadline = time.monotonic() + 10
            while sum(future.done() for future in futures) < 2 and time.monotonic() < deadline:
                time.sleep(0.01)
            # Two are refused at once, two run, the others wait
            refused = [future.result() for future in futures if future.done()]
            assert [result["error"] for result in refused] == ["too many PDFs are being processed"] * 2, refused
            time.sleep(0.2)
            assert (running, most) == (MAX_PDF_WORKERS, MAX_PDF_WORKERS), (running, most)
            gate.set()
            results = [future.result(timeout=60) for future in futures]
    finally:
        gate.set()
        document_handler._run_worker = run_worker
    processed = [result for result in results if result["error"] is None]
    assert len(processed) == line and all(result["page_count"] == 2 for result in processed), results
    assert most == MAX_PDF_WORKERS, f"{most} at once"
    for (file_id, _), result in zip(files, results):
        assert len(derived(file_id)) == (3 if result["error"] is None else 0), derived(file_id)
    return f"{len(files)} at once: {most} ran at a time, {len(processed)} processed, 2 refused"


class FakeFiles:
    """The table uploaded_files, as far as the file store uses it."""

    def __init__(self):
        self.rows = {}

    def register_uploaded_file(self, file_id, user_id, **values):
        self.rows[file_id] = {"file_id": file_id, "user_id": user_id, **values}

    def delete_uploaded_file(self, file_id):
        self.rows.pop(file_id, None)

    def get_file(self, file_id):
        return dict(self.rows[file_id]) if file_id in self.rows else None

    def get_conversation_files(self, conversation_id, user_id):
        return [dict(row) for row in self.rows.values()
                if row.get("conversation_id") == conversation_id and row["user_id"] == user_id]


async def test_tool_pdf():
    """A PDF a tool created is processed the same way, and a hostile one doesn't fail or hold up the tool."""
    saved = file_store.db, document_handler.PDF_TIMEOUT_SECONDS
    file_store.db = FakeFiles()
    try:
        def save(data: bytes) -> dict:
            return file_store.save_tool_file(data, user_id=1, conversation_id="chat", mime_type="application/pdf",
                                             stem="printer", origin="Printer: Print it")
        row = save(make_pdf([text_page(1), text_page(2)]))
        assert row["name"] == "printer-1.pdf" and row["path"].is_file(), row
        assert derived(row["file_id"]) == ["_page_1.png", "_page_2.png", "_text.txt"], derived(row["file_id"])
        assert "Page 2 line 40" in document_handler.get_extracted_text(row["file_id"])

        # As backend/services/mcp/tools.py saves a result's files: in a thread
        document_handler.PDF_TIMEOUT_SECONDS = 1
        async with Ticker() as ticker:
            row = await asyncio.to_thread(save, slow_pdf())
        assert row["name"] == "printer-2.pdf" and row["path"].is_file(), row
        assert derived(row["file_id"]) == [], derived(row["file_id"])
        assert ticker.worst < 0.2, f"the loop stood still for {ticker.worst * 1000:.0f} ms"
    finally:
        file_store.db, document_handler.PDF_TIMEOUT_SECONDS = saved


# =========================================================================
# Images
# =========================================================================

async def test_image_size_reads_the_header():
    """image_size() decodes nothing: it runs for every image that is stored."""
    # 13000 x 13000 pixels in 650 KB, just under what Pillow refuses: decoded, they are 676 MB
    bomb = flat_png(13000, 13000)
    with OwnMemory() as memory:
        started = time.monotonic()
        size = file_store.image_size(bomb)
        elapsed = time.monotonic() - started
    assert size == (13000, 13000), size
    assert elapsed < 0.2 and memory.rise < 20, f"{elapsed * 1000:.0f} ms, +{memory.rise:.0f} MB"
    # Storing it (an upload, a tool's file) asks for its size
    saved = file_store.db
    file_store.db = FakeFiles()
    try:
        with OwnMemory() as stored:
            row = file_store.store(bomb, 1, name="bomb.png", mime_type="image/png")
        assert (row["width"], row["height"]) == (13000, 13000) and stored.rise < 20, (row, stored.rise)
    finally:
        file_store.db = saved
    # As before: a JPEG turned by its EXIF data has the size it is shown with; no image, no size
    exif = Image.Exif()
    exif[0x0112] = 6
    assert file_store.image_size(picture(400, 200, "JPEG", exif=exif)) == (200, 400)
    assert file_store.image_size(picture(400, 200, "PNG")) == (400, 200)
    assert file_store.image_size(b"no image") is None
    return f"{len(bomb) // 1024} KB claiming 169 megapixels: {elapsed * 1000:.0f} ms, +{memory.rise:.0f} MB"


async def test_image_above_the_cap():
    """An image with more pixels than are decoded: no preview, no copy for a model, and no decoding."""
    assert 6000 * 6000 > file_store.MAX_IMAGE_PIXELS
    file_id, _ = put(flat_png(6000, 6000), ".png")
    with OwnMemory() as memory:
        started = time.monotonic()
        preview = file_store.thumbnail(file_id, "small"), file_store.thumbnail(file_id, "large")
        for_model = file_store.image_for_model(file_id)
        elapsed = time.monotonic() - started
    assert preview == (None, None) and for_model is None, (preview, for_model)
    assert elapsed < 0.2 and memory.rise < 20, f"{elapsed * 1000:.0f} ms, +{memory.rise:.0f} MB"
    assert derived(file_id) == [], derived(file_id)
    # A progressive JPEG is read whole whatever size is asked for: its full size counts
    assert 6000 * 4500 > file_store.MAX_IMAGE_PIXELS
    file_id, path = put(picture(6000, 4500, "JPEG", "L", progressive=True), ".jpg")
    assert not file_store._jpeg_in_one_pass(path)
    with OwnMemory() as progressive:
        assert file_store.thumbnail(file_id, "large") is None and file_store.image_for_model(file_id) is None
    assert progressive.rise < 20, f"+{progressive.rise:.0f} MB"
    # At the cap, an image is still decoded
    assert 6250 * 4000 == file_store.MAX_IMAGE_PIXELS
    file_id, _ = put(flat_png(6250, 4000), ".png")
    with Image.open(file_store.thumbnail(file_id, "small")) as image:
        assert image.size == (256, 164) and image.mode == "RGBA", (image.size, image.mode)
    return f"36 megapixels refused in {elapsed * 1000:.0f} ms, +{memory.rise:.0f} MB"


async def test_camera_jpeg():
    """A camera's JPEG of 50 megapixels gets its preview and its copy for a model, decoded at a fraction of its size."""
    exif = Image.Exif()
    exif[0x0112] = 6  # Held upright: turned by a quarter
    file_id, path = put(picture(8160, 6120, "JPEG", quality=85, exif=exif), ".jpg")
    assert 8160 * 6120 > file_store.MAX_IMAGE_PIXELS and file_store._jpeg_in_one_pass(path)
    with OwnMemory() as memory:
        started = time.monotonic()
        preview = file_store.thumbnail(file_id, "large")
        data, mime_type = file_store.image_for_model(file_id)
        elapsed = time.monotonic() - started
    with Image.open(preview) as image:
        assert image.size == (768, 1024) and image.format == "WEBP", (image.size, image.format)
        assert is_orange(image, (384, 512))
    with Image.open(io.BytesIO(data)) as image:
        assert image.size == (1176, 1568) and mime_type == "image/jpeg", (image.size, mime_type)
    # At full size it is 200 MB in Pillow
    assert memory.rise < 70 and elapsed < 3, f"+{memory.rise:.0f} MB, {elapsed:.1f} s"
    return f"50 megapixels: preview and model copy in {elapsed * 1000:.0f} ms, +{memory.rise:.0f} MB"


async def test_images_as_before():
    """Normal images: previews as WebP, a model's copy scaled, transparency kept, a small JPEG as it is."""
    file_id, _ = put(picture(2000, 1000, "PNG"), ".png")
    small, large = file_store.thumbnail(file_id, "small"), file_store.thumbnail(file_id, "large")
    assert (small.name, large.name) == (f"{file_id}_thumb_small.webp", f"{file_id}_thumb_large.webp")
    assert small.read_bytes()[:4] == b"RIFF" and file_store.thumbnail(file_id, "small") == small
    with Image.open(small) as image:
        assert image.size == (256, 128) and image.mode == "RGB", (image.size, image.mode)
    with Image.open(large) as image:
        assert image.size == (1024, 512) and is_orange(image, (500, 250)), image.size
    data, mime_type = file_store.image_for_model(file_id)
    with Image.open(io.BytesIO(data)) as image:
        assert (image.size, mime_type) == ((1568, 784), "image/jpeg") and is_orange(image, (700, 300))
    assert derived(file_id) == ["_thumb_large.webp", "_thumb_small.webp"]

    # Transparency: an RGBA preview, a PNG for the model; smaller than a preview, it keeps its size
    file_id, _ = put(picture(640, 480, "PNG", "RGBA"), ".png")
    with Image.open(file_store.thumbnail(file_id, "large")) as image:
        assert image.size == (640, 480) and image.mode == "RGBA" and image.getpixel((9, 9))[3] == 128
    data, mime_type = file_store.image_for_model(file_id)
    assert mime_type == "image/png" and data[:4] == b"\x89PNG"

    # A JPEG that is small enough goes to the model as it is; a larger one scaled and turned
    jpeg = picture(800, 600, "JPEG")
    file_id, _ = put(jpeg, ".jpg")
    assert file_store.image_for_model(file_id) == (jpeg, "image/jpeg")
    exif = Image.Exif()
    exif[0x0112] = 6
    file_id, _ = put(picture(3000, 1500, "JPEG", exif=exif), ".jpg")
    with Image.open(file_store.thumbnail(file_id, "small")) as image:
        assert image.size == (128, 256), image.size
    data, _ = file_store.image_for_model(file_id)
    with Image.open(io.BytesIO(data)) as image:
        assert image.size == (784, 1568), image.size

    # A file that is no image, and a file that is missing
    file_id, _ = put(b"Some notes", ".txt")
    assert file_store.thumbnail(file_id, "small") is None and file_store.image_for_model(file_id) is None
    assert file_store.thumbnail("file_1_00", "small") is None


async def test_image_decodes_at_once():
    """Previews are asked for in parallel, but only MAX_IMAGE_DECODES images are decoded at once."""
    files = [put(flat_png(3000, 2000), ".png")[0] for _ in range(8)]
    scaled, lock = file_store._scaled, threading.Lock()
    running = most = 0

    def counted(*arguments):
        nonlocal running, most
        with lock:
            running += 1
            most = max(most, running)
        try:
            return scaled(*arguments)
        finally:
            with lock:
                running -= 1

    file_store._scaled = counted
    try:
        async with Ticker() as ticker:
            previews = await asyncio.gather(*(asyncio.to_thread(file_store.thumbnail, file_id, "large")
                                              for file_id in files))
    finally:
        file_store._scaled = scaled
    assert all(preview is not None and preview.is_file() for preview in previews), previews
    assert 1 <= most <= file_store.MAX_IMAGE_DECODES, f"{most} at once"
    assert ticker.worst < 0.2, f"the loop stood still for {ticker.worst * 1000:.0f} ms"


# =========================================================================
# Local Whisper
# =========================================================================

class FakeWhisper(types.ModuleType):
    """Stands in for the whisper package: notes where its model is loaded and run, and transcribes slowly."""

    def __init__(self):
        super().__init__("whisper")
        self.loaded, self.threads = [], []
        self.running = self.most = 0
        self._lock = threading.Lock()

    def load_model(self, name):
        self.loaded.append(name)
        self.threads.append(threading.current_thread())
        time.sleep(0.2)  # Loading blocks its thread, like the real one
        return self

    def transcribe(self, path, **options):
        self.threads.append(threading.current_thread())
        with self._lock:
            self.running += 1
            self.most = max(self.most, self.running)
        time.sleep(0.3)
        with self._lock:
            self.running -= 1
        return {"text": f" Transcript of {Path(path).name} "}


class FailingClient:
    """A Whisper API that is configured but fails."""

    def __init__(self):
        self.calls = 0
        self.audio = types.SimpleNamespace(transcriptions=types.SimpleNamespace(create=self._create))

    async def _create(self, **arguments):
        self.calls += 1
        raise ConnectionError("no route to the Whisper API")


class WhisperSetup:
    """A fake whisper package and chosen settings for a block, the real ones after it."""
    NAMES = ("USE_LOCAL_WHISPER", "WHISPER_LOCAL_FALLBACK", "_get_openai_client", "_whisper_model")

    def __init__(self, client=None, **settings):
        self.client, self.settings = client, settings

    def __enter__(self) -> FakeWhisper:
        self.saved = {name: getattr(audio_handler, name) for name in self.NAMES}
        self.module = sys.modules.get("whisper")
        fake = sys.modules["whisper"] = FakeWhisper()
        audio_handler._whisper_model = None
        audio_handler._get_openai_client = lambda: self.client
        for name, value in self.settings.items():
            setattr(audio_handler, name, value)
        return fake

    def __exit__(self, *error):
        for name, value in self.saved.items():
            setattr(audio_handler, name, value)
        if self.module is None:
            del sys.modules["whisper"]
        else:
            sys.modules["whisper"] = self.module


async def test_whisper_fallback_off():
    """WHISPER_LOCAL_FALLBACK=false: a transcription the API can't do fails, and no model is loaded."""
    failed = {"transcript_path": None, "transcript": None, "error": "Transcription failed or returned empty text"}
    # No API configured
    with WhisperSetup(USE_LOCAL_WHISPER=False, WHISPER_LOCAL_FALLBACK=False) as whisper:
        file_id, path = put(b"RIFF....WAVE", ".wav")
        assert await audio_handler.process_audio(path, file_id) == failed
        assert whisper.loaded == [] and audio_handler._whisper_model is None and derived(file_id) == []
    # An API that fails
    client = FailingClient()
    with WhisperSetup(client, USE_LOCAL_WHISPER=False, WHISPER_LOCAL_FALLBACK=False) as whisper:
        file_id, path = put(b"RIFF....WAVE", ".wav")
        assert await audio_handler.process_audio(path, file_id) == failed
        assert client.calls == 1 and whisper.loaded == []
    # USE_LOCAL_WHISPER still means the local model, and not the API
    client = FailingClient()
    with WhisperSetup(client, USE_LOCAL_WHISPER=True, WHISPER_LOCAL_FALLBACK=False) as whisper:
        file_id, path = put(b"RIFF....WAVE", ".wav")
        result = await audio_handler.process_audio(path, file_id)
        assert result["transcript"] == f"Transcript of {file_id}.wav" and result["error"] is None, result
        assert client.calls == 0 and whisper.loaded == [config.LOCAL_WHISPER_MODEL]


async def test_whisper_off_the_event_loop():
    """The local model is loaded and run in a thread of its own, one transcription at a time."""
    client = FailingClient()
    with WhisperSetup(client, USE_LOCAL_WHISPER=False, WHISPER_LOCAL_FALLBACK=True) as whisper:
        files = [put(b"RIFF....WAVE", ".wav") for _ in range(3)]
        async with Ticker() as ticker:
            started = time.monotonic()
            results = await asyncio.gather(*(audio_handler.process_audio(path, file_id) for file_id, path in files))
            elapsed = time.monotonic() - started
        # As before: the API first, then the local model; the transcript in the result and in its file
        assert client.calls == 3
        for (file_id, path), result in zip(files, results):
            assert result == {"transcript_path": FILES_DIR / f"{file_id}_transcript.txt",
                              "transcript": f"Transcript of {path.name}", "error": None}, result
            assert audio_handler.get_transcript(file_id) == f"Transcript of {path.name}"
        assert whisper.loaded == [config.LOCAL_WHISPER_MODEL], "loaded once"
        assert whisper.most == 1, f"{whisper.most} transcriptions at once"
        assert threading.main_thread() not in whisper.threads and len(set(whisper.threads)) == 1, whisper.threads
        # 0.2 s of loading and 3 x 0.3 s of transcribing, none of it on the loop
        assert elapsed >= 1.1 and ticker.ticks > 50, (elapsed, ticker.ticks)
        assert ticker.worst < 0.2, f"the loop stood still for {ticker.worst * 1000:.0f} ms"
    return f"{elapsed:.1f} s of loading and transcribing, the loop was at most {ticker.worst * 1000:.0f} ms late"


async def test_whisper_setting():
    """WHISPER_LOCAL_FALLBACK is read from the environment, and the audio handler uses it."""
    for value, expected in (("false", "False"), ("true", "True"), ("TRUE", "True")):
        show = "from backend import config; print(config.WHISPER_LOCAL_FALLBACK)"
        done = subprocess.run([sys.executable, "-c", show], cwd=PROJECT_ROOT, capture_output=True, text=True,
                              env={**os.environ, "WHISPER_LOCAL_FALLBACK": value})
        assert done.stdout.strip() == expected, (value, done.stdout, done.stderr)
    assert audio_handler.WHISPER_LOCAL_FALLBACK is config.WHISPER_LOCAL_FALLBACK


# =========================================================================
# Run
# =========================================================================

TESTS = [
    test_normal_pdf,
    test_page_and_text_limits,
    test_pages_take_only_so_much,
    test_worker_gets_no_settings,
    test_one_step_fails,
    test_huge_pages,
    test_time_limit,
    test_memory_limit,
    test_limits_reach_the_renderer,
    test_event_loop_stays_free,
    test_queue,
    test_tool_pdf,
    test_image_size_reads_the_header,
    test_image_above_the_cap,
    test_camera_jpeg,
    test_images_as_before,
    test_image_decodes_at_once,
    test_whisper_fallback_off,
    test_whisper_off_the_event_loop,
    test_whisper_setting,
]


async def run() -> int:
    failures = 0
    for test in TESTS:
        try:
            measured = await test()
            print(f"PASS  {test.__name__}" + (f"  ({measured})" if measured else ""))
        except Exception:
            failures += 1
            print(f"FAIL  {test.__name__}")
            traceback.print_exc()
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} passed")
    return 1 if failures else 0


def main() -> int:
    logging.basicConfig(level=logging.CRITICAL)
    warnings.simplefilter("ignore", Image.DecompressionBombWarning)  # The test images are meant to be large
    try:
        return asyncio.run(run())
    finally:
        shutil.rmtree(FILES_DIR, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
