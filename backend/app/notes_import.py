"""Load the course notes in data/notes into a course and queue them for embedding (F-40, TR-A-07).

Usage: python -m app.notes_import data/notes --instructor EMAIL
Notes carry `status: needs human review` in their front matter and stay flagged until a person reviews them.
"""
import argparse
import json
from pathlib import Path

from sqlalchemy import text

from app.db import get_engine, get_redis
from app.retrieval import store
from app.retrieval.chunking import parse_note


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("notes_dir", type=Path)
    parser.add_argument("--instructor", required=True)
    parser.add_argument("--bank", type=Path, default=Path("data/bank"))
    args = parser.parse_args()

    course_title = json.loads((args.bank / "course.json").read_text())["title"]
    queued = []
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
        for path in sorted(args.notes_dir.glob("*.md")):
            fields, body = parse_note(path.read_text(encoding="utf-8"))
            concept_id = conn.execute(
                text("SELECT id FROM concepts WHERE course_id = :c AND name = :n"),
                {"c": course_id, "n": fields.get("concept")},
            ).scalar()
            if concept_id is None:
                raise SystemExit(f"{path.name}: unknown concept '{fields.get('concept')}'")
            queued.append(
                store.save_document(
                    conn, course_id=course_id, title=fields.get("title", path.stem), source_ref=path.name,
                    body=body, concept_id=concept_id,
                )
            )
    for document_id in queued:  # queued after the commit so the worker can see the rows
        get_redis().rpush(store.QUEUE, document_id)
    print(f"queued {len(queued)} notes for embedding: {queued}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
