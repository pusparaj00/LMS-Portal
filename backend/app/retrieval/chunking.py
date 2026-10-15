"""Split a note into overlapping chunks that keep their document and section reference (TR-L-01)."""
import re
from dataclasses import dataclass

CHUNK_WORDS = 120
OVERLAP_WORDS = 30
FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


@dataclass(frozen=True)
class Chunk:
    index: int
    section: str
    text: str


def parse_note(raw: str) -> tuple[dict[str, str], str]:
    """Return the front matter fields and the body of a note."""
    match = FRONT_MATTER.match(raw.replace("\r\n", "\n"))
    if not match:
        return {}, raw.strip()
    fields = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields, raw.replace("\r\n", "\n")[match.end():].strip()


def _sections(body: str) -> list[tuple[str, str]]:
    parts = re.split(r"^## +(.+)$", body, flags=re.MULTILINE)
    if len(parts) == 1:
        return [("", body.strip())]
    intro = [("", parts[0].strip())] if parts[0].strip() else []
    return intro + [(parts[i].strip(), parts[i + 1].strip()) for i in range(1, len(parts), 2)]


def chunk_note(body: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    for heading, text in _sections(body):
        words = text.split()
        start = 0
        while start < len(words):
            window = words[start : start + CHUNK_WORDS]
            chunks.append(Chunk(len(chunks), heading, " ".join(window)))
            if start + CHUNK_WORDS >= len(words):
                break
            start += CHUNK_WORDS - OVERLAP_WORDS
    return chunks
