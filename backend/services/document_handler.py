# backend/services/document_handler.py
"""
Document handling utilities for PDF, TXT, and MD files.
Handles text extraction, page rendering, and preparing documents for LLM context.

A PDF comes from anybody, and a crafted one can keep pdfminer or poppler busy for minutes or make
them ask for gigabytes. So the server does not read PDFs itself: process_pdf_safely() starts a
process for each (pdf_worker.py) that is stopped after PDF_TIMEOUT_SECONDS and can't allocate
more than PDF_MEMORY_LIMIT, and takes over its results only when it ended well (docs/files.md,
"Limits").
"""

import errno
import gc
import glob
import json
import logging
import math
import os
import secrets
import shutil
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

try:
    import resource
except ImportError:  # Windows
    resource = None

from ..config import FILES_DIR
from .file_utils import get_file_path
from .pdf_worker import OUT_OF_MEMORY, RESULT_FILE

logger = logging.getLogger(__name__)

# Maximum number of PDF pages to process for AI context
MAX_PDF_PAGES = 20

# Longer edge of a rendered page in pixels: an A4 page at 150 dpi. Every page is scaled to it,
# so a page of 200 x 200 inches costs what an A4 page does
PDF_PAGE_EDGE = 1754

# Most characters of a PDF's text that are kept. 20 dense pages have about 100,000
MAX_PDF_TEXT_CHARS = 500_000

# What the page images of one PDF may take together. Pages of text take a few hundred KB each;
# pages of noise take 7 MB each, 136 MB for a PDF of 6 MB. The pages past this are not kept
MAX_PDF_PAGES_BYTES = 32 * 1024 * 1024

# The limits of the process a PDF is read in (process_pdf_safely())
PDF_TIMEOUT_SECONDS = 60                # By the clock; then it is killed with all it started
PDF_RENDER_SECONDS = 45                 # pdftoppm alone: the worker stops it itself and still has time for the text
PDF_MEMORY_LIMIT = 512 * 1024 * 1024    # What it may allocate, and the pdftoppm it starts
MAX_PDF_WORKERS = 2                     # Running at once; further PDFs wait their turn
MAX_PDF_WAITING = 4                     # Waiting at most; a PDF beyond that is not processed

# The directory the backend package is in: the worker is started as a module of it
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

_pdf_slots = threading.BoundedSemaphore(MAX_PDF_WORKERS)
# Every waiting call holds a thread of its caller's pool, so the line has an end
_pdf_line = threading.BoundedSemaphore(MAX_PDF_WORKERS + MAX_PDF_WAITING)

# Supported document MIME types
SUPPORTED_DOCUMENT_TYPES = {
    'application/pdf': 'pdf',
    'text/plain': 'txt',
    'text/markdown': 'md',
}


def is_document(mime_type: str) -> bool:
    """Check if the MIME type is a supported document format."""
    return mime_type.lower() in SUPPORTED_DOCUMENT_TYPES


def get_document_type(mime_type: str) -> Optional[str]:
    """Get the document type from MIME type."""
    return SUPPORTED_DOCUMENT_TYPES.get(mime_type.lower())


def _is_out_of_memory(error: Optional[BaseException]) -> bool:
    """
    Whether an error is running out of memory, or comes from it.

    Not every such error says so: pdfplumber wraps what pdfminer raises, and an interpreter
    without memory fails in other ways as well (SystemError: "returned NULL without setting an
    exception"). So in a process with a memory limit (pdf_worker.py), any error counts once the
    process has come close to the limit.
    """
    for _ in range(10):
        if error is None:
            break
        if isinstance(error, MemoryError) or (isinstance(error, OSError) and error.errno == errno.ENOMEM):
            return True
        error = error.__cause__ or error.__context__
    if resource is None:
        return False
    try:
        limit = resource.getrlimit(resource.RLIMIT_DATA)[0]
        if limit == resource.RLIM_INFINITY:
            return False
        # The most memory this process ever held, in KB (Linux). Not getrusage(): its peak
        # includes what the server held when it started this process
        with open("/proc/self/status") as status:
            for line in status:
                if line.startswith("VmHWM:"):
                    return int(line.split()[1]) * 1024 >= 0.8 * limit
        return False
    except MemoryError:
        return True
    except (OSError, ValueError, IndexError):
        return False


def _extract_text(file_path: Path) -> Optional[str]:
    """extract_pdf_text(), but raises what goes wrong."""
    import pdfplumber

    text_parts = []
    length = 0
    note = None
    with pdfplumber.open(file_path) as pdf:
        total = len(pdf.pages)
        for i, page in enumerate(pdf.pages[:MAX_PDF_PAGES]):
            page_text = page.extract_text()
            page.close()  # It keeps every character it parsed otherwise, page after page
            if not page_text:
                continue
            part = f"--- Page {i + 1} ---\n{page_text}"
            if length + len(part) > MAX_PDF_TEXT_CHARS:
                text_parts.append(part[:MAX_PDF_TEXT_CHARS - length])
                note = (f"\n[Note: Document truncated. Showing the first {MAX_PDF_TEXT_CHARS} characters "
                        f"of its text, up to page {i + 1} of {total}]")
                break
            text_parts.append(part)
            length += len(part)

        if note is None and total > MAX_PDF_PAGES:
            note = f"\n[Note: Document truncated. Showing {MAX_PDF_PAGES} of {total} pages]"

    if note:
        text_parts.append(note)
    return "\n\n".join(text_parts) if text_parts else None


def extract_pdf_text(file_path: Path) -> Optional[str]:
    """
    Extract text content from a PDF file using pdfplumber: its first MAX_PDF_PAGES pages, at
    most MAX_PDF_TEXT_CHARS characters. A note at the end says what was left out.

    Args:
        file_path: Path to the PDF file.

    Returns:
        Extracted text content or None if extraction fails.

    Raises:
        MemoryError: The PDF needs more memory than this process may have.
    """
    try:
        return _extract_text(file_path)
    except ImportError:
        logger.error("pdfplumber not installed. Run: pip install pdfplumber")
        return None
    except Exception as e:
        if not _is_out_of_memory(e):
            logger.error(f"Error extracting text from PDF {file_path}: {e}")
            return None
    # Outside the handler: the error it caught holds on to the memory the PDF took
    raise MemoryError(f"out of memory in {file_path.name}")


def _exit_reason(code: int) -> str:
    """How a process ended, for a log line: 'exit code 1', 'SIGKILL'."""
    if code >= 0:
        return f"exit code {code}"
    try:
        return signal.Signals(-code).name
    except ValueError:
        return f"signal {-code}"


def _render_pages(file_path: Path, output_dir: Path, file_id: str) -> list[Path]:
    """
    render_pdf_pages(), but says why it failed.

    Raises:
        RuntimeError: pdftoppm is missing, failed or took too long. Nothing it wrote is left.
    """
    # pdftoppm names its files <root>-<page number>.png
    root = output_dir / f"{file_id}_render"
    rendered = f"{glob.escape(root.name)}-*.png"
    command = ["pdftoppm", "-q", "-png", "-f", "1", "-l", str(MAX_PDF_PAGES),
               "-scale-to", str(PDF_PAGE_EDGE), str(file_path), str(root)]
    pages: list[Path] = []
    try:
        try:
            # No output is read: a PDF can make pdftoppm report errors without end
            done = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, timeout=PDF_RENDER_SECONDS)
        except FileNotFoundError:
            raise RuntimeError("pdftoppm is not installed (poppler-utils)")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"pdftoppm took longer than {PDF_RENDER_SECONDS} seconds")
        if done.returncode != 0:
            raise RuntimeError(f"pdftoppm failed ({_exit_reason(done.returncode)})")
        # Numbered from 1 without gaps, whatever pdftoppm wrote: get_pdf_page_paths() stops at a gap
        by_page = sorted(output_dir.glob(rendered), key=lambda path: int(path.stem.rsplit("-", 1)[1]))
        for number, path in enumerate(by_page, start=1):
            page = output_dir / f"{file_id}_page_{number}.png"
            path.replace(page)
            pages.append(page)
        return pages
    except BaseException:
        for path in [*output_dir.glob(rendered), *pages]:
            path.unlink(missing_ok=True)
        raise


def render_pdf_pages(file_path: Path, output_dir: Path, file_id: str) -> list[Path]:
    """
    Render PDF pages as PNG images: the first MAX_PDF_PAGES pages, each scaled to PDF_PAGE_EDGE
    pixels on its longer edge.

    pdftoppm (poppler) writes the images itself. So neither a page's size on paper nor the number
    of pages decides what rendering costs, and no image is loaded into this process.

    Args:
        file_path: Path to the PDF file.
        output_dir: Directory to save rendered images.
        file_id: File ID for naming output files.

    Returns:
        List of paths to rendered page images (<file_id>_page_<n>.png); empty if rendering failed.
    """
    try:
        return _render_pages(file_path, output_dir, file_id)
    except Exception as e:
        logger.error(f"Error rendering PDF pages from {file_path}: {e}")
        return []


def process_pdf(file_path: Path, file_id: str, output_dir: Optional[Path] = None) -> dict:
    """
    Process a PDF file in this process: render pages as images and extract text.

    Only for a PDF that is known to be harmless. One from a user or a tool goes through
    process_pdf_safely(), which runs this in a process with limits.

    Args:
        file_path: Path to the PDF file.
        file_id: File ID for naming output files.
        output_dir: Where the outputs go; by default next to the PDF.

    Returns:
        Dict with 'text_path' (<file_id>_text.txt, or None), 'page_paths' and 'page_count'
        (<file_id>_page_<n>.png) and 'error' (what could not be done, or None).

    Raises:
        MemoryError: The PDF needs more memory than this process may have. Nothing is left of it.
    """
    output_dir = Path(output_dir) if output_dir else file_path.parent
    text_path = output_dir / f"{file_id}_text.txt"
    partial = text_path.with_name(f"{text_path.name}.part")
    result = {
        'text_path': None,
        'page_paths': [],
        'page_count': 0,
        'error': None
    }
    errors = []

    def failed(what: str, error: Exception) -> bool:
        """Notes a step that failed; the other's result stays. True if it ran out of memory instead."""
        if _is_out_of_memory(error):
            return True
        logger.error(f"PDF {file_path}: {what}: {error}")
        errors.append(f"{what}: {type(error).__name__}: {error}"[:300])
        return False

    try:
        # Pages first: until the text is extracted this process has loaded no PDF library, so
        # pdftoppm and pdfminer never hold their memory at the same time
        out_of_memory = False
        try:
            result['page_paths'] = _render_pages(file_path, output_dir, file_id)
            result['page_count'] = len(result['page_paths'])
        except Exception as e:
            out_of_memory = failed("pages not rendered", e)

        if not out_of_memory:
            try:
                text_content = _extract_text(file_path)
                if text_content:
                    # Written under another name first: a reader never gets half a file
                    partial.write_text(text_content, encoding='utf-8')
                    partial.replace(text_path)
                    result['text_path'] = text_path
                    logger.info(f"Saved extracted text to {text_path}")
            except Exception as e:
                out_of_memory = failed("text not extracted", e)

        if out_of_memory:
            # This PDF is more than the process may take: nothing of it is kept. Raised here, not
            # where the error was caught: that error holds on to all the PDF took (its traceback
            # and the frames in it), and with the memory still gone the clean-up fails as well
            gc.collect()
            raise MemoryError(f"out of memory in {file_path.name}")
    except BaseException:
        for path in [*result['page_paths'], text_path]:
            path.unlink(missing_ok=True)
        raise
    finally:
        partial.unlink(missing_ok=True)

    result['error'] = "; ".join(errors) or None
    return result


def _failed(error: str) -> dict:
    """The result of a PDF that was not processed."""
    return {'text_path': None, 'page_paths': [], 'page_count': 0, 'error': error}


def _kill(process: subprocess.Popen) -> None:
    """Kill a worker with every process it started (they are one process group), and wait for its end."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (AttributeError, OSError):
        process.kill()  # No process groups here (Windows), or none left of this one
    process.wait()


# What the worker gets of the server's environment: where programs and libraries are, the
# language of texts, the time zone. Everything else stays with the server
_WORKER_ENVIRONMENT = ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "TMPDIR", "PYTHONPATH",
                       "LD_LIBRARY_PATH")


def _worker_environment() -> dict:
    """The environment a PDF worker runs in: _WORKER_ENVIRONMENT, and no .env file is read."""
    environment = {name: os.environ[name] for name in _WORKER_ENVIRONMENT if name in os.environ}
    # backend.config loads the project's .env (development); the worker is not to have it either
    environment["PYTHON_DOTENV_DISABLED"] = "1"
    return environment


def _run_worker(file_path: Path, file_id: str, work_dir: Path, timeout: float, memory_limit: int) -> Optional[str]:
    """
    Run pdf_worker.py on a PDF and wait for it, at most `timeout` seconds.

    Returns:
        None if the worker finished: its outputs are in work_dir. Else why it didn't.
    """
    # The CPU time is the worker's own limit for when nobody is left to stop it. Twice the
    # timeout: it never comes before the clock here
    command = [sys.executable, "-m", "backend.services.pdf_worker", str(file_path), file_id, str(work_dir),
               str(memory_limit), str(2 * math.ceil(timeout))]
    # A session of its own makes the worker and the pdftoppm it starts one process group. Its
    # output goes nowhere: what it has to say is in its result file. It gets none of the server's
    # settings: the process that opens anybody's PDFs has no use for keys and passwords
    process = subprocess.Popen(command, cwd=_PROJECT_ROOT, env=_worker_environment(), stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        code = None
    except BaseException:
        _kill(process)
        raise
    if code == 0:
        return None
    # Also after a crash: its pdftoppm may still run
    _kill(process)
    if code is None:
        return f"took longer than {timeout:g} seconds"
    if code == OUT_OF_MEMORY:
        return f"needs more than {memory_limit // (1024 * 1024)} MB of memory"
    return f"the worker failed ({_exit_reason(code)})"


def _take_outputs(work_dir: Path, output_dir: Path, file_id: str) -> dict:
    """
    Move what a finished worker wrote to where the outputs of a PDF belong.

    Returns:
        The result as process_pdf() returns it.

    Raises:
        OSError, ValueError: The outputs can't be read or moved; none is left in output_dir.
    """
    with open(work_dir / RESULT_FILE, encoding="utf-8") as file:
        error = json.loads(file.read(10_000))["error"]  # A few words; never read without an end
    pages = []
    pages_bytes = 0
    for number in range(1, MAX_PDF_PAGES + 1):
        name = f"{file_id}_page_{number}.png"
        if not _is_output(work_dir / name):
            break
        pages_bytes += (work_dir / name).stat().st_size
        if pages_bytes > MAX_PDF_PAGES_BYTES:
            # The rest goes with the work directory
            logger.info(f"PDF {file_id}: its pages take more than {MAX_PDF_PAGES_BYTES} bytes, "
                        f"keeping the first {len(pages)}")
            break
        pages.append(name)
    text = f"{file_id}_text.txt"
    has_text = _is_output(work_dir / text)
    moved: list[Path] = []
    try:
        # Page 1 last: get_pdf_page_paths() counts up from it, so a reader finds all pages or none
        for name in [*([text] if has_text else []), *reversed(pages)]:
            (work_dir / name).replace(output_dir / name)
            moved.append(output_dir / name)
    except BaseException:
        for path in moved:
            path.unlink(missing_ok=True)
        raise
    return {
        'text_path': output_dir / text if has_text else None,
        'page_paths': [output_dir / name for name in pages],
        'page_count': len(pages),
        'error': None if error is None else str(error),
    }


def _is_output(path: Path) -> bool:
    """A file the worker wrote, not a link to somewhere else."""
    return path.is_file() and not path.is_symlink()


def process_pdf_safely(file_path: Path, file_id: str, *, timeout: Optional[float] = None,
                       memory_limit: Optional[int] = None) -> dict:
    """
    Process a PDF from a user or a tool: like process_pdf(), but in a process of its own
    (pdf_worker.py), so a PDF that is made to take minutes or gigabytes can't take the server
    with it.

    It blocks until the PDF is done, so call it in a thread (asyncio.to_thread), never on the
    event loop. At most MAX_PDF_WORKERS PDFs are processed at once; a further call waits for
    its turn, and with MAX_PDF_WAITING waiting already it gives up at once.

    Args:
        file_path: Path to the PDF file.
        file_id: File ID for naming output files.
        timeout: Seconds the worker gets, from its start (default: PDF_TIMEOUT_SECONDS).
        memory_limit: Bytes the worker and the pdftoppm it starts may each allocate
            (default: PDF_MEMORY_LIMIT).

    Returns:
        The dict process_pdf() returns. Never raises: when the worker fails, takes too long or
        needs too much memory, 'error' says so, there is no text and no page, and nothing it
        wrote is left behind.
    """
    timeout = PDF_TIMEOUT_SECONDS if timeout is None else timeout
    memory_limit = PDF_MEMORY_LIMIT if memory_limit is None else memory_limit
    if not _pdf_line.acquire(blocking=False):
        logger.warning(f"PDF {file_id} not processed: {MAX_PDF_WAITING} PDFs are waiting already")
        return _failed("too many PDFs are being processed")
    work_dir = None
    try:
        with _pdf_slots:
            output_dir = Path(file_path).parent
            # Next to the PDF, so the outputs are moved, not copied; deleted with the file if the
            # server dies before it is removed (file_utils.delete_stored_file())
            work_dir = output_dir / f"{file_id}_pdf_{secrets.token_hex(4)}"
            work_dir.mkdir()
            # The worker starts in another directory: it gets the paths in full
            failure = _run_worker(Path(file_path).resolve(), file_id, work_dir.resolve(), timeout, memory_limit)
            if failure:
                logger.warning(f"PDF {file_id} not processed: {failure}")
                return _failed(failure)
            return _take_outputs(work_dir, output_dir, file_id)
    except Exception as e:
        logger.error(f"PDF {file_id} not processed: {type(e).__name__}: {e}")
        return _failed(f"{type(e).__name__}: {e}")
    finally:
        if work_dir is not None:
            shutil.rmtree(work_dir, ignore_errors=True)
        _pdf_line.release()


def read_text_file(file_path: Path) -> Optional[str]:
    """
    Read content from a text file (TXT or MD).

    Args:
        file_path: Path to the text file.

    Returns:
        File content or None if reading fails.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error reading text file {file_path}: {e}")
        return None


def get_extracted_text(file_id: str) -> Optional[str]:
    """
    Get extracted text for a document.

    For PDFs, reads from the _text.txt file.
    For TXT/MD files, reads the original file.

    Args:
        file_id: The file ID.

    Returns:
        Extracted/original text content or None.
    """
    # First, try to find the extracted text file (for PDFs)
    files_dir = Path(FILES_DIR)
    text_file_path = files_dir / f"{file_id}_text.txt"
    if text_file_path.exists():
        return read_text_file(text_file_path)

    # Otherwise, look for the original file (TXT/MD)
    original_path = get_file_path(file_id)
    if original_path and original_path.suffix.lower() in ['.txt', '.md']:
        return read_text_file(original_path)

    return None


def get_pdf_page_paths(file_id: str) -> list[Path]:
    """
    Get paths to rendered PDF page images.

    Args:
        file_id: The file ID.

    Returns:
        List of paths to page images.
    """
    files_dir = Path(FILES_DIR)
    page_paths = []
    page_num = 1

    while True:
        page_path = files_dir / f"{file_id}_page_{page_num}.png"
        if page_path.exists():
            page_paths.append(page_path)
            page_num += 1
        else:
            break

    return page_paths


def prepare_document_for_llm(
    file_id: str,
    mime_type: str,
    include_page_images: bool = True
) -> Optional[dict]:
    """
    Prepare document content for inclusion in LLM context.

    Args:
        file_id: The file ID.
        mime_type: MIME type of the document.
        include_page_images: Whether to include PDF page images (if available).

    Returns:
        Dict with 'text' and optionally 'images' list, or None if failed.
    """
    doc_type = get_document_type(mime_type)
    if not doc_type:
        return None

    result = {
        'text': None,
        'images': []
    }

    # Get text content
    text_content = get_extracted_text(file_id)
    if text_content:
        result['text'] = text_content

    # For PDFs, optionally include page images
    if doc_type == 'pdf' and include_page_images:
        page_paths = get_pdf_page_paths(file_id)
        for page_path in page_paths:
            result['images'].append({
                'path': str(page_path),
                'mime_type': 'image/png'
            })

    return result if result['text'] or result['images'] else None
