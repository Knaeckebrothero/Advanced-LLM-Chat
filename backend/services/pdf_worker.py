"""
The process a PDF is read in (document_handler.process_pdf_safely() starts it):

    python -m backend.services.pdf_worker <pdf> <file ID> <output directory> <memory bytes> <CPU seconds>

A PDF comes from anybody, and a crafted one can keep pdfminer or poppler busy for minutes or make
them ask for gigabytes. In the server that stops every chat; here it stops only this process. It
limits itself before it opens the file, the pdftoppm it starts inherits the limits, and the server
kills both when they take too long.

It writes the text and the page images into the output directory, then RESULT_FILE: only a run
that got that far and exits with 0 counts. It prints nothing: a PDF could make it print without end.
"""
import json
import os
import sys
from pathlib import Path

# Written last, as {"error": what could not be done, or null}
RESULT_FILE = "result.json"

# Exit code when the memory limit was not enough
OUT_OF_MEMORY = 3

# Address space allowed on top of the memory limit, for what is mapped but costs no memory:
# libraries, fonts, the locale archive (220 MB on Fedora)
MAPPED_FILES_ROOM = 1024 * 1024 * 1024


def limit_resources(memory_limit: int, cpu_seconds: int) -> None:
    """
    Limit what this process may use, and each process it starts. Without the resource module
    (Windows) nothing is limited; a limit the platform does not take is skipped.

    Args:
        memory_limit: Bytes it may allocate.
        cpu_seconds: CPU time it may use.
    """
    try:
        import resource
    except ImportError:
        return
    limits = (
        # What it may allocate: heap and anonymous memory, the memory that counts against the
        # server's own limit (mmap counts since Linux 4.7)
        ("RLIMIT_DATA", memory_limit),
        # Everything mapped. It can't be the limit itself: how much is mapped without costing
        # memory differs from system to system. It stops what RLIMIT_DATA doesn't count
        ("RLIMIT_AS", memory_limit + MAPPED_FILES_ROOM),
        # The server stops this process by the clock; this is for when the server is gone
        ("RLIMIT_CPU", cpu_seconds),
        # No core file of a renderer that crashed
        ("RLIMIT_CORE", 0),
    )
    for name, value in limits:
        kind = getattr(resource, name, None)
        if kind is None:
            continue
        try:
            resource.setrlimit(kind, (value, value))
        except (ValueError, OSError):
            pass  # A lower limit is set already, or the platform refuses: go on without


def main(arguments: list[str]) -> int:
    if len(arguments) != 5:
        return 2
    pdf, file_id, output_dir = Path(arguments[0]), arguments[1], Path(arguments[2])
    limit_resources(int(arguments[3]), int(arguments[4]))
    try:
        # Imported under the limits: what it loads counts too
        from backend.services.document_handler import process_pdf
        result = process_pdf(pdf, file_id, output_dir)
        (output_dir / RESULT_FILE).write_text(json.dumps({"error": result["error"]}), encoding="utf-8")
    except MemoryError:
        # At once: with no memory left, even the interpreter's shutdown can fail (and abort)
        os._exit(OUT_OF_MEMORY)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
