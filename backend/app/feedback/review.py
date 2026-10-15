"""Instructor review of stored explanations (F-62, TR-L-09).

An instructor can approve an entry as it is, approve an edited claim, or reject it. A rejected entry is never reused.
An approved claim must still pass the verifier against the submission the entry came from, so an edit cannot add
solution code, hidden test data or a wrong line.
"""
import json

from sqlalchemy import Connection, text

from app.auth import CurrentUser, can_access_course
from app.feedback.context import load_context
from app.feedback.signature_cache import check_against
from app.feedback.verifier import all_passed
from app.schemas import ExplanationDecision, StoredExplanation


class ReviewError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def _out(row, concepts: dict[int, str]) -> StoredExplanation:
    payload = row.explanation_json
    return StoredExplanation(
        signature=row.signature, problem_id=row.problem_id, problem_title=row.title, claim=payload["claim"],
        line=payload["line"], line_text=payload["line_text"], concept=concepts.get(payload["concept_id"], ""),
        test_category=payload["test_category"], status=row.status, hit_count=row.hit_count,
        approved_by=row.approved_by, updated_at=row.updated_at,
    )


def _concepts(conn: Connection, course_id: int) -> dict[int, str]:
    return dict(conn.execute(text("SELECT id, name FROM concepts WHERE course_id = :c"), {"c": course_id}).all())


SELECT = (
    "SELECT e.signature, e.problem_id, p.title, p.course_id, e.explanation_json, e.status, e.hit_count,"
    " e.approved_by, e.updated_at, e.source_submission_id, s.user_id AS source_user FROM explanation_cache e"
    " JOIN problems p ON p.id = e.problem_id JOIN submissions s ON s.id = e.source_submission_id"
)


def list_entries(conn: Connection, course_id: int) -> list[StoredExplanation]:
    """Most used first, so the explanations students see most often are reviewed first."""
    rows = conn.execute(
        text(SELECT + " WHERE p.course_id = :c ORDER BY e.hit_count DESC, e.id"), {"c": course_id}
    ).all()
    concepts = _concepts(conn, course_id)
    return [_out(r, concepts) for r in rows]


def decide(conn: Connection, user: CurrentUser, signature: str, body: ExplanationDecision) -> StoredExplanation:
    row = conn.execute(text(SELECT + " WHERE e.signature = :s"), {"s": signature}).first()
    if row is None or not can_access_course(conn, user, row.course_id):
        raise ReviewError(404, "stored explanation not found")
    payload = dict(row.explanation_json)
    if body.decision == "reject":
        if body.claim is not None:
            raise ReviewError(422, "an edited claim can only be approved")
        status = "rejected"
    else:
        if body.claim is not None:
            payload["claim"] = body.claim.strip()
        ctx = load_context(conn, row.source_submission_id, row.source_user)
        explanation, checks, _, _ = check_against(conn, ctx, payload)
        if explanation is None or not all_passed(checks):
            failed = ", ".join(f"{c.name} ({c.detail})" if c.detail else c.name for c in checks if not c.passed)
            raise ReviewError(422, f"the explanation does not pass the checks: {failed}")
        status = "instructor_approved"
    updated = conn.execute(
        text(
            "UPDATE explanation_cache SET explanation_json = CAST(:j AS jsonb), status = :st, approved_by = :u,"
            " updated_at = now() WHERE signature = :s RETURNING signature"
        ),
        {"j": json.dumps(payload), "st": status, "u": user.id, "s": signature},
    ).scalar_one()
    return list_entry(conn, updated, row.course_id)


def list_entry(conn: Connection, signature: str, course_id: int) -> StoredExplanation:
    row = conn.execute(text(SELECT + " WHERE e.signature = :s"), {"s": signature}).one()
    return _out(row, _concepts(conn, course_id))
