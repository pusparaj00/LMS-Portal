import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from app import ratelimit
from app.auth import Conn, CurrentUser, can_access_course, current_user
from app.consent import consented_student
from app.errors import sandbox_error
from app.grading import Grade, TestSpec, grade
from app.mastery import client as mastery
from app.sandbox import SandboxUnavailable
from app.schemas import SubmissionCreate, SubmissionResult, VisibleTest

log = logging.getLogger("app.submissions")
router = APIRouter(prefix="/submissions", tags=["submissions"])
Student = Annotated[CurrentUser, Depends(consented_student)]


def _load_tests(conn, problem_id: int, user: CurrentUser, visible_only: bool) -> list[TestSpec]:
    problem = conn.execute(
        text("SELECT course_id, kind, archived_at FROM problems WHERE id = :id"), {"id": problem_id}
    ).first()
    if problem is None or problem.archived_at is not None or not can_access_course(conn, user, problem.course_id):
        raise HTTPException(404, "problem not found")
    if problem.kind != "code":
        raise HTTPException(422, "this item is not a coding problem")
    where = "AND NOT hidden" if visible_only else ""
    rows = conn.execute(
        text(
            "SELECT id, input, expected, hidden, category FROM test_cases"
            f" WHERE problem_id = :id {where} ORDER BY id"
        ),
        {"id": problem_id},
    )
    return [TestSpec(r.id, r.input, r.expected, r.hidden, r.category) for r in rows]


def _grade(code: str, tests: list[TestSpec]) -> Grade:
    try:
        return grade(code, tests)
    except SandboxUnavailable as exc:
        raise sandbox_error(exc) from None


def _result(submission_id: int | None, problem_id: int, g: Grade) -> SubmissionResult:
    # Hidden tests contribute only to counts and categories; their input and output never leave.
    visible = [
        VisibleTest(
            input=o.test.input,
            expected=o.test.expected,
            actual=o.run.stdout[:2000],
            passed=o.passed,
            status=o.run.status,
        )
        for o in g.outcomes
        if not o.test.hidden
    ]
    return SubmissionResult(
        submission_id=submission_id,
        problem_id=problem_id,
        status=g.status,
        passed=g.passed,
        failed=g.failed,
        error_type=g.error_type,
        failed_categories=g.failed_categories,
        runtime_ms=g.runtime_ms,
        visible_tests=visible,
        mastery_changes=[],
    )


@router.post("/run", response_model=SubmissionResult)
def run_code(body: SubmissionCreate, user: Student, conn: Conn):
    """Run against the visible examples only; nothing is stored."""
    ratelimit.check("run", user.id)
    tests = _load_tests(conn, body.problem_id, user, visible_only=True)
    return _result(None, body.problem_id, _grade(body.code, tests))


@router.post("", response_model=SubmissionResult)
def submit_code(body: SubmissionCreate, user: Student, conn: Conn):
    ratelimit.check("submit", user.id)
    tests = _load_tests(conn, body.problem_id, user, visible_only=False)
    g = _grade(body.code, tests)
    submission_id = conn.execute(
        text(
            "INSERT INTO submissions (user_id, problem_id, code)"
            " VALUES (:u, :p, :c) RETURNING id"
        ),
        {"u": user.id, "p": body.problem_id, "c": body.code},
    ).scalar_one()
    conn.execute(
        text(
            "INSERT INTO run_results (submission_id, status, passed, failed, error_type, stderr,"
            " runtime_ms, failed_categories, failed_test_ids)"
            " VALUES (:s, :st, :p, :f, :e, :err, :ms, :cats, :ids)"
        ),
        {
            "s": submission_id,
            "st": g.status,
            "p": g.passed,
            "f": g.failed,
            "e": g.error_type,
            "err": g.stderr,
            "ms": g.runtime_ms,
            "cats": g.failed_categories,
            "ids": g.failed_test_ids,
        },
    )
    conn.commit()  # the mastery service reads the stored run result, so it must be visible first
    result = _result(submission_id, body.problem_id, g)
    try:
        result.mastery_changes = mastery.record_submission(submission_id)
    except mastery.MasteryUnavailable:
        # The submission is stored. The evidence call is idempotent, so it can be replayed.
        log.error("mastery update failed", extra={"fields": {"submission_id": submission_id}})
    return result


@router.get("/{submission_id}", response_model=SubmissionResult)
def get_submission(
    submission_id: int, user: Annotated[CurrentUser, Depends(current_user)], conn: Conn
):
    row = conn.execute(
        text(
            "SELECT s.user_id, s.problem_id, p.course_id, r.status, r.passed, r.failed,"
            " r.error_type, r.runtime_ms, r.failed_categories FROM submissions s"
            " JOIN problems p ON p.id = s.problem_id"
            " JOIN run_results r ON r.submission_id = s.id WHERE s.id = :id"
        ),
        {"id": submission_id},
    ).first()
    owner = row is not None and row.user_id == user.id
    staff = (
        row is not None
        and user.role != "student"
        and can_access_course(conn, user, row.course_id)
    )
    if not (owner or staff):
        raise HTTPException(404, "submission not found")
    return SubmissionResult(
        submission_id=submission_id,
        problem_id=row.problem_id,
        status=row.status,
        passed=row.passed,
        failed=row.failed,
        error_type=row.error_type,
        failed_categories=row.failed_categories,
        runtime_ms=row.runtime_ms,
        visible_tests=[],
        mastery_changes=[],
    )
