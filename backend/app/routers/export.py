"""Export of mastery vectors and the mastery ledger for evaluation and for the instructor (TR-D-07), and of the
gradebook (F-04).

Mastery rows carry the student's numeric ID and a `synthetic` flag, never an email address, so they can be shared for
analysis without naming anyone. The gradebook is the exception: it is for recording grades, so it carries the same
label the class view shows (the part of the email before the @). Every export is read-only and limited to the
course's instructor (or an admin), and is written to the audit trail.
"""
import csv
import io
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text

from app import audit
from app.auth import Conn, CurrentUser, can_access_course, require_role
from app.ratelimit import client_ip
from app.synthetic import SYNTHETIC_NAME

router = APIRouter(prefix="/courses/{course_id}/export", tags=["export"])
Staff = Annotated[CurrentUser, Depends(require_role("instructor", "admin"))]
Format = Annotated[Literal["csv", "json"], Query(description="csv (default) or json")]
FORMULA_START = ("=", "+", "-", "@", "\t", "\r")

MASTERY_COLUMNS = ["student_id", "synthetic", "concept_id", "concept", "p_known", "updated_at"]
GRADEBOOK_COLUMNS = [
    "student_id", "label", "synthetic", "assignment_id", "assignment", "due_at", "score", "possible", "with_late",
    "status",
]
EVENT_COLUMNS = [
    "event_id", "student_id", "synthetic", "concept_id", "concept", "p_before", "p_after", "weight", "correct",
    "evidence_type", "rule_id", "submission_id", "evidence_ref", "created_at",
]


def _cell(value):
    """A spreadsheet runs text that starts with = + - @ as a formula; mark such text as plain text."""
    if isinstance(value, str) and value.startswith(FORMULA_START):
        return "'" + value
    return value


def _value(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _respond(rows: list[dict], columns: list[str], fmt: str, name: str) -> Response:
    """Only the listed columns leave: the query also reads the email (to work out `synthetic`); it must not travel."""
    if fmt == "json":
        return JSONResponse(
            content=[{c: _value(row[c]) for c in columns} for row in rows],
            headers={"Content-Disposition": f'attachment; filename="{name}.json"'},
        )
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_cell(_value(row[c])) for c in columns])
    return Response(
        out.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'},
    )


def _check(conn, user: CurrentUser, course_id: int, request: Request, kind: str, fmt: str) -> None:
    if not can_access_course(conn, user, course_id):
        raise HTTPException(403, "not your course")
    audit.record(
        "export.download", user_id=user.id, ip=client_ip(request), status=200,
        detail={"course_id": course_id, "kind": kind, "format": fmt},
    )


def _is_synthetic(email: str) -> bool:
    return SYNTHETIC_NAME.fullmatch(email) is not None


@router.get("/mastery", response_model=None)
def export_mastery(course_id: int, user: Staff, conn: Conn, request: Request, format: Format = "csv"):
    """The current mastery value of every student for every concept in the course."""
    _check(conn, user, course_id, request, "mastery", format)
    rows = conn.execute(
        text(
            "SELECT m.user_id AS student_id, u.email, m.concept_id, c.name AS concept, m.p_known, m.updated_at"
            " FROM mastery m JOIN concepts c ON c.id = m.concept_id JOIN users u ON u.id = m.user_id"
            " WHERE c.course_id = :c ORDER BY m.user_id, m.concept_id"
        ),
        {"c": course_id},
    ).mappings()
    data = [{**r, "synthetic": _is_synthetic(r["email"])} for r in rows]
    return _respond(data, MASTERY_COLUMNS, format, f"mastery-course-{course_id}")


@router.get("/mastery-events", response_model=None)
def export_mastery_events(course_id: int, user: Staff, conn: Conn, request: Request, format: Format = "csv"):
    """The mastery ledger: every change with its before and after value, the rule and the evidence behind it."""
    _check(conn, user, course_id, request, "mastery_events", format)
    rows = conn.execute(
        text(
            "SELECT e.id AS event_id, e.user_id AS student_id, u.email, e.concept_id, c.name AS concept, e.p_before,"
            " e.p_after, e.weight, e.correct, e.evidence_type, e.rule_id, e.submission_id, e.evidence_ref,"
            " e.created_at FROM mastery_events e JOIN concepts c ON c.id = e.concept_id"
            " JOIN users u ON u.id = e.user_id WHERE c.course_id = :c ORDER BY e.id"
        ),
        {"c": course_id},
    ).mappings()
    data = [{**r, "synthetic": _is_synthetic(r["email"])} for r in rows]
    return _respond(data, EVENT_COLUMNS, format, f"mastery-events-course-{course_id}")


@router.get("/gradebook", response_model=None)
def export_gradebook(course_id: int, user: Staff, conn: Conn, request: Request, format: Format = "csv"):
    """One row per student and assignment: the on-time score, the score with late work, and the status (F-04)."""
    from app.routers.assignments import gradebook

    _check(conn, user, course_id, request, "gradebook", format)
    book = gradebook(conn, course_id)
    assignments = {a.id: a for a in book.assignments}
    data = [
        {
            "student_id": row.student_id, "label": row.label, "synthetic": row.synthetic,
            "assignment_id": cell.assignment_id, "assignment": assignments[cell.assignment_id].title,
            "due_at": assignments[cell.assignment_id].due_at, "score": cell.score,
            "possible": assignments[cell.assignment_id].possible, "with_late": cell.with_late, "status": cell.status,
        }
        for row in book.students
        for cell in row.cells
    ]
    return _respond(data, GRADEBOOK_COLUMNS, format, f"gradebook-course-{course_id}")
