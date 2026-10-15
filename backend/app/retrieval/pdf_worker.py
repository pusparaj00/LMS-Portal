"""Reads one PDF from stdin and prints {"text": ...} or {"error": ...} as JSON. Run only by app.retrieval.pdf.

It is a separate process because a PDF is untrusted input: this one has no environment variables (so no secrets), a
memory limit and a CPU limit set by its parent, and imports nothing from the application.
"""
import io
import json
import sys

MAX_PAGES = 100
MAX_CHARS = 50_000


def main() -> None:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(sys.stdin.buffer.read()))
        if reader.is_encrypted:
            result = {"error": "the PDF is password protected"}
        elif len(reader.pages) > MAX_PAGES:
            result = {"error": f"the PDF has {len(reader.pages)} pages; at most {MAX_PAGES} are allowed"}
        else:
            parts, size = [], 0
            for page in reader.pages:
                text = (page.extract_text() or "").strip()
                parts.append(text)
                size += len(text)
                if size > MAX_CHARS:
                    break
            joined = "\n\n".join(p for p in parts if p)
            result = {"text": joined[: MAX_CHARS + 1]}
    except MemoryError:
        result = {"error": "the PDF needs too much memory to read"}
    except Exception:
        result = {"error": "the PDF could not be read"}
    sys.stdout.write(json.dumps(result))


main()
