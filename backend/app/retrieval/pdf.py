"""Text from an uploaded PDF (F-03). The PDF is untrusted, so it is read in a separate, limited process."""
import json
import resource
import subprocess
import sys
from pathlib import Path

MAX_PDF_BYTES = 4_000_000
MAX_TEXT_CHARS = 50_000  # the same limit as pasted notes
TIMEOUT_SECONDS = 20
MEMORY_BYTES = 1024 * 1024 * 1024
CPU_SECONDS = 15
WORKER = Path(__file__).with_name("pdf_worker.py")


class PdfError(Exception):
    """The PDF cannot be used; the message is safe to show to the instructor."""


def _limit() -> None:
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS + 1))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def extract_text(data: bytes) -> str:
    if len(data) > MAX_PDF_BYTES:
        raise PdfError(f"the PDF is larger than {MAX_PDF_BYTES // 1_000_000} MB")
    if not data.startswith(b"%PDF-"):
        raise PdfError("the file is not a PDF")
    try:
        done = subprocess.run(
            [sys.executable, "-I", str(WORKER)], input=data, capture_output=True, timeout=TIMEOUT_SECONDS,
            env={}, preexec_fn=_limit, close_fds=True,
        )
    except subprocess.TimeoutExpired:
        raise PdfError("reading the PDF took too long") from None
    try:
        result = json.loads(done.stdout)
    except ValueError:
        raise PdfError("the PDF could not be read") from None
    if "error" in result:
        raise PdfError(result["error"])
    text = result["text"].strip()
    if not text:
        raise PdfError("the PDF has no text to read (scanned pages are images, which are not supported)")
    if len(text) > MAX_TEXT_CHARS:
        raise PdfError(f"the PDF has more than {MAX_TEXT_CHARS:,} characters of text; split it into smaller notes")
    return text
