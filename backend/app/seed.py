"""Seed a clean system with a demo (TR-D-06). Safe to run twice.

Creates the demo instructor and student, imports the validated question bank and the notes, enrols the student, seeds
the labelled synthetic class, and waits for the notes to be embedded. Passwords come from DEMO_STUDENT_PASSWORD and
DEMO_INSTRUCTOR_PASSWORD; if one is not set a random password is generated and printed ONCE when the account is created.
An account that already exists is left untouched, so running the seed again never changes a password.

Usage: python -m app.seed [--synthetic 20] [--no-wait]
"""
import argparse
import os
import secrets
import time
from pathlib import Path

from sqlalchemy import Connection, text

from app import notes_import, synthetic
from app.auth import hash_password
from app.bank_import import import_bank, load_bank, validate_bank
from app.db import get_engine
from app.retrieval import store
from app.schemas import MAX_PASSWORD_BYTES

STUDENT = "student@demo.local"
INSTRUCTOR = "instructor@demo.local"
MIN_PASSWORD = 8
WAIT_SECONDS = 180


def ensure_user(conn: Connection, email: str, role: str, password: str | None) -> tuple[int, str | None]:
    """The user's id, and the generated password if this call created the account with one."""
    existing = conn.execute(text("SELECT id FROM users WHERE email = :e"), {"e": email}).scalar()
    if existing is not None:
        return existing, None
    generated = None
    if not password:
        generated = password = secrets.token_urlsafe(12)
    if not MIN_PASSWORD <= len(password.encode()) <= MAX_PASSWORD_BYTES:
        raise SystemExit(f"the password for {email} must be {MIN_PASSWORD} to {MAX_PASSWORD_BYTES} bytes")
    user_id = conn.execute(
        text("INSERT INTO users (email, password_hash, role) VALUES (:e, :h, :r) RETURNING id"),
        {"e": email, "h": hash_password(password), "r": role},
    ).scalar_one()
    return user_id, generated


def _find_data_dir() -> Path:
    for candidate in (Path("data"), Path("/srv/data"), Path(__file__).resolve().parents[2] / "data"):
        if (candidate / "bank").exists():
            return candidate
    raise SystemExit("cannot find the data folder (expected data/bank and data/notes)")


def seed(synthetic_students: int = 20, wait: bool = True) -> dict:
    data = _find_data_dir()
    with get_engine().begin() as conn:
        _, instructor_pw = ensure_user(conn, INSTRUCTOR, "instructor", os.environ.get("DEMO_INSTRUCTOR_PASSWORD"))
        student_id, student_pw = ensure_user(conn, STUDENT, "student", os.environ.get("DEMO_STUDENT_PASSWORD"))

    bank = load_bank(data / "bank")
    verdicts = validate_bank(bank)
    rejected = [v for v in verdicts if v.errors]
    if rejected:
        details = "; ".join(f"{v.title}: {v.errors}" for v in rejected)
        raise SystemExit(f"the question bank has invalid items: {details}")
    with get_engine().begin() as conn:
        summary = import_bank(conn, bank, {v.title for v in verdicts}, INSTRUCTOR)
        course_id = summary["course_id"]
        conn.execute(
            text("INSERT INTO enrollments (user_id, course_id) VALUES (:u, :c) ON CONFLICT DO NOTHING"),
            {"u": student_id, "c": course_id},
        )
        queued, skipped = notes_import.stage_notes(conn, course_id, data / "notes")
        for document_id in queued:  # F-93: demo notes are shown to students unless they copy a reference solution
            body = conn.execute(text("SELECT body FROM documents WHERE id = :d"), {"d": document_id}).scalar_one()
            if not store.problems_copied_by(conn, course_id, body):
                conn.execute(text("UPDATE documents SET visible_to_students = true WHERE id = :d"), {"d": document_id})
    notes_import.enqueue(queued)

    seeded = synthetic.seed(course_id, synthetic_students)
    if wait:
        _wait_for_notes(course_id)
    return {
        "course_id": course_id, "bank": summary, "notes_queued": len(queued), "notes_unchanged": skipped,
        "synthetic": seeded, "new_passwords": {INSTRUCTOR: instructor_pw, STUDENT: student_pw},
    }


def _wait_for_notes(course_id: int) -> None:
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        with get_engine().connect() as conn:
            states = conn.execute(
                text("SELECT status, count(*) FROM documents WHERE course_id = :c GROUP BY status"), {"c": course_id}
            ).all()
        counts = dict(states)
        if counts.get("failed"):
            raise SystemExit(f"{counts['failed']} notes failed to embed; see the worker log")
        if counts and set(counts) == {"ready"}:
            return
        time.sleep(2)
    raise SystemExit("the notes were not embedded in time; is the worker running?")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--synthetic", type=int, default=20)
    parser.add_argument("--no-wait", action="store_true")
    args = parser.parse_args()
    result = seed(args.synthetic, wait=not args.no_wait)
    print(f"course {result['course_id']}: bank {result['bank']}")
    print(f"notes: {result['notes_queued']} embedded now, {result['notes_unchanged']} already up to date")
    print(f"synthetic class: {result['synthetic']}")
    for email, password in result["new_passwords"].items():
        if password:
            print(f"created {email} with the generated password: {password}  (shown only once)")
    print("done. Log in with the demo accounts above; the synthetic students cannot log in.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
