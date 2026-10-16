"""A teacher's view of one student's work (F-61, F-34; PRD: "student and instructor can see why a mastery value
changed", and student code visible only to the student and their instructors).

Only the course's own teacher, and only for a student enrolled in that course. Every opening of a student's code is
written to the audit trail (TR-S-08). Hidden test inputs are never shown, and neither is the student's chat.
"""
import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import Connection, text

from app import audit, ratelimit
from app.auth import Conn, CurrentUser, can_access_course, require_role
from app.db import get_redis
from app.grading_book import label
from app.routers.diagnostic import _mastery_vector, top_misconceptions
from app.routers.students import ledger
from app.schemas import (
    ExplanationRecord,
    LedgerEntry,
    StudentSubmission,
    StudentWork,
    SubmissionDetail,
    VisibleTestResult,
)
from app.synthetic import is_synthetic

router = APIRouter(prefix="/courses/{course_id}/students/{student_id}", tags=["student work"])
Teacher = Annotated[CurrentUser, Depends(require_role("instructor"))]
SUBMISSION_LIMIT = 100


def _student(conn: Connection, user: CurrentUser, course_id: int, student_id: int):
    if not can_access_course(conn, user, course_id):
        raise HTTPException(403, "not your course")
    row = conn.execute(
        text(
            "SELECT u.id, u.email, u.display_name FROM enrollments e JOIN users u ON u.id = e.user_id"
            " WHERE e.course_id = :c AND e.user_id = :s AND u.role = 'student'"
        ),
        {"c": course_id, "s": student_id},
    ).first()
    if row is None:
        raise HTTPException(404, "no such student in this course")
    return row


@router.get("", response_model=StudentWork)
def student_work(course_id: int, student_id: int, user: Teacher, conn: Conn):
    """Mastery, suspected misconceptions and submissions in this course, newest first (at most 100)."""
    row = _student(conn, user, course_id, student_id)
    submissions = conn.execute(
        text(
            "SELECT s.id AS submission_id, s.problem_id, p.title AS problem_title, s.created_at, r.status, r.passed,"
            " r.failed FROM submissions s JOIN problems p ON p.id = s.problem_id"
            " JOIN run_results r ON r.submission_id = s.id"
            " WHERE s.user_id = :s AND p.course_id = :c ORDER BY s.id DESC LIMIT :n"
        ),
        {"s": student_id, "c": course_id, "n": SUBMISSION_LIMIT},
    ).mappings()
    return StudentWork(
        student_id=student_id, label=label(row.email, row.display_name), synthetic=is_synthetic(row.email),
        concepts=_mastery_vector(conn, student_id, course_id),
        misconceptions=top_misconceptions(conn, student_id, course_id),
        submissions=[StudentSubmission(**s) for s in submissions],
    )


@router.get("/mastery/{concept_id}/history", response_model=list[LedgerEntry])
def student_history(course_id: int, student_id: int, concept_id: int, user: Teacher, conn: Conn):
    """The same ledger the student sees: each change with the test, error and rule behind it (F-34)."""
    _student(conn, user, course_id, student_id)
    if conn.execute(
        text("SELECT 1 FROM concepts WHERE id = :k AND course_id = :c"), {"k": concept_id, "c": course_id}
    ).first() is None:
        raise HTTPException(404, "concept not found")
    return ledger(conn, student_id, concept_id)


def _explanation(conn: Connection, submission_id: int) -> ExplanationRecord:
    finals = conn.execute(
        text("SELECT passed, model FROM explanation_checks WHERE submission_id = :s AND check_name = 'final'"
             " ORDER BY id"),
        {"s": submission_id},
    ).all()
    if not finals:
        return ExplanationRecord(requested=False, attempts=0, outcome=None, from_cache=False, text=None)
    last = finals[-1]
    shown = None
    try:
        cached = get_redis().get(f"explain:{submission_id}")
    except Exception:  # the record above is complete without the text
        cached = None
    if cached:
        body = json.loads(cached)
        shown = (body.get("explanation") or {}).get("claim") or body.get("fallback_text")
    return ExplanationRecord(
        requested=True,
        attempts=conn.execute(
            text("SELECT count(DISTINCT attempt) FROM explanation_checks WHERE submission_id = :s AND attempt > 0"),
            {"s": submission_id},
        ).scalar_one(),
        outcome="verified" if last.passed else "template", from_cache=last.model == "cache", text=shown,
    )


@router.get("/submissions/{submission_id}", response_model=SubmissionDetail)
def submission(course_id: int, student_id: int, submission_id: int, request: Request, user: Teacher, conn: Conn):
    """The code as submitted and its result. Opening it is audited: a student's code is their personal data."""
    _student(conn, user, course_id, student_id)
    row = conn.execute(
        text(
            "SELECT s.id AS submission_id, s.problem_id, p.title AS problem_title, s.created_at, s.code, r.status,"
            " r.passed, r.failed, r.error_type, r.failed_categories, r.failed_test_ids"
            " FROM submissions s JOIN problems p ON p.id = s.problem_id JOIN run_results r ON r.submission_id = s.id"
            " WHERE s.id = :id AND s.user_id = :s AND p.course_id = :c"
        ),
        {"id": submission_id, "s": student_id, "c": course_id},
    ).mappings().first()
    if row is None:
        raise HTTPException(404, "submission not found")
    tests = conn.execute(
        text("SELECT id, input, expected, hidden FROM test_cases WHERE problem_id = :p ORDER BY id"),
        {"p": row["problem_id"]},
    ).all()
    failed = set(row["failed_test_ids"] or [])
    current = {t.id for t in tests}
    # If the tests were edited after this submission its failed ids name tests that no longer exist; say so.
    unchanged = failed <= current and len(tests) == row["passed"] + row["failed"]
    audit.record("student_work.viewed", user_id=user.id, ip=ratelimit.client_ip(request), conn=conn,
                 detail={"course_id": course_id, "student_id": student_id, "submission_id": submission_id})
    return SubmissionDetail(
        **{k: row[k] for k in ("submission_id", "problem_id", "problem_title", "created_at", "code", "status",
                               "passed", "failed", "error_type")},
        failed_categories=list(row["failed_categories"] or []),
        visible_tests=[
            VisibleTestResult(input=t.input, expected=t.expected, passed=t.id not in failed)
            for t in tests if not t.hidden
        ] if unchanged else None,
        hidden_failed=sum(1 for t in tests if t.hidden and t.id in failed) if unchanged else None,
        explanation=_explanation(conn, submission_id),
    )
