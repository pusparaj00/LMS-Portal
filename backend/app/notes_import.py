"""Load the course notes in data/notes into a course and queue them for embedding (F-40, TR-A-07).

Usage: python -m app.notes_import data/notes --instructor EMAIL
Notes carry `status: needs human review` in their front matter and stay flagged until a person reviews them.
A note that is unchanged and already embedded is skipped, so running this twice does no extra work.
"""
import argparse
import hashlib
import json
from pathlib import Path

from sqlalchemy import Connection, text

from app.db import get_engine, get_redis
from app.retrieval import store
from app.retrieval.chunking import parse_note


def stage_notes(conn: Connection, course_id: int, notes_dir: Path) -> tuple[list[int], int]:
    """Save every changed or not-yet-embedded note as pending. Returns (document ids to queue, notes skipped)."""
    to_queue, skipped = [], 0
    for path in sorted(notes_dir.glob("*.md")):
        fields, body = parse_note(path.read_text(encoding="utf-8"))
        concept_id = conn.execute(
            text("SELECT id FROM concepts WHERE course_id = :c AND name = :n"),
            {"c": course_id, "n": fields.get("concept")},
        ).scalar()
        if concept_id is None:
            raise SystemExit(f"{path.name}: unknown concept '{fields.get('concept')}'")
        existing = conn.execute(
            text("SELECT content_hash, status FROM documents WHERE course_id = :c AND source_ref = :s"),
            {"c": course_id, "s": path.name},
        ).first()
        unchanged = existing and existing.content_hash == hashlib.sha256(body.encode()).hexdigest()
        if unchanged and existing.status == "ready":
            skipped += 1
            continue
        to_queue.append(
            store.save_document(
                conn, course_id=course_id, title=fields.get("title", path.stem), source_ref=path.name,
                body=body, concept_id=concept_id,
            )
        )
    return to_queue, skipped


def enqueue(document_ids: list[int]) -> None:
    """Called after the commit, so the worker can see the rows."""
    for document_id in document_ids:
        get_redis().rpush(store.QUEUE, document_id)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("notes_dir", type=Path)
    parser.add_argument("--instructor", required=True)
    parser.add_argument("--bank", type=Path, default=Path("data/bank"))
    args = parser.parse_args()

    course_title = json.loads((args.bank / "course.json").read_text())["title"]
    with get_engine().begin() as conn:
        course_id = conn.execute(
            text(
                "SELECT c.id FROM courses c JOIN users u ON u.id = c.instructor_id"
                " WHERE c.title = :t AND u.email = lower(:e)"
            ),
            {"t": course_title, "e": args.instructor},
        ).scalar()
        if course_id is None:
            raise SystemExit(f"no course '{course_title}' for {args.instructor}; import the question bank first")
        queued, skipped = stage_notes(conn, course_id, args.notes_dir)
    enqueue(queued)
    print(f"queued {len(queued)} notes for embedding: {queued}; skipped {skipped} unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
