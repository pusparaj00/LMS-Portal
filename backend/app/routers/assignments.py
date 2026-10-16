"""Assignments with due dates and the gradebook (F-04)."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import Connection, text

from app import audit, grading_book, lti_grades
from app.auth import Conn, CurrentUser, can_access_course, current_user, require_role
from app.schemas import (
    AssignmentIn,
    AssignmentOut,
    AssignmentProblemOut,
    Gradebook,
    GradebookAssignment,
    GradebookCell,
    GradebookRow,
    GradeSendResult,
    MyScore,
)

router = APIRouter(prefix="/courses/{course_id}", tags=["assignments"])
Instructor = Annotated[CurrentUser, Depends(require_role("instructor"))]
Staff = Annotated[CurrentUser, Depends(require_role("instructor", "admin"))]
Member = Annotated[CurrentUser, Depends(current_user)]


def _check(conn: Connection, user: CurrentUser, course_id: int) -> None:
    if not can_access_course(conn, user, course_id):
        raise HTTPException(403, "you have no access to this course")


def _assignments(conn: Connection, course_id: int, assignment_id: int | None = None) -> list[AssignmentOut]:
    rows = conn.execute(
        text(
            "SELECT a.id, a.title, a.due_at, ap.problem_id, p.title AS problem_title, ap.points"
            " FROM assignments a JOIN assignment_problems ap ON ap.assignment_id = a.id"
            " JOIN problems p ON p.id = ap.problem_id"
            " WHERE a.course_id = :c AND (CAST(:a AS integer) IS NULL OR a.id = :a) ORDER BY a.due_at, a.id, p.id"
        ),
        {"c": course_id, "a": assignment_id},
    ).all()
    out: dict[int, AssignmentOut] = {}
    for r in rows:
        item = out.setdefault(r.id, AssignmentOut(
            id=r.id, course_id=course_id, title=r.title, due_at=r.due_at, possible=0, problems=[]
        ))
        item.problems.append(AssignmentProblemOut(problem_id=r.problem_id, title=r.problem_title, points=r.points))
        item.possible += r.points
    return list(out.values())


def _save_problems(conn: Connection, course_id: int, assignment_id: int, body: AssignmentIn) -> None:
    ids = [p.problem_id for p in body.problems]
    usable = set(conn.execute(
        text(
            "SELECT id FROM problems WHERE id = ANY(:ids) AND course_id = :c AND kind = 'code' AND (archived_at IS NULL"
            " OR id IN (SELECT problem_id FROM assignment_problems WHERE assignment_id = :a))"
        ),
        {"ids": ids, "c": course_id, "a": assignment_id},
    ).scalars())
    refused = [i for i in ids if i not in usable]
    if refused:
        raise HTTPException(422, f"not a live coding problem of this course: {', '.join(map(str, refused))}")
    conn.execute(text("DELETE FROM assignment_problems WHERE assignment_id = :a"), {"a": assignment_id})
    for p in body.problems:
        conn.execute(
            text("INSERT INTO assignment_problems (assignment_id, problem_id, points) VALUES (:a, :p, :w)"),
            {"a": assignment_id, "p": p.problem_id, "w": p.points},
        )


def _owned(conn: Connection, course_id: int, assignment_id: int) -> None:
    if conn.execute(
        text("SELECT 1 FROM assignments WHERE id = :a AND course_id = :c"), {"a": assignment_id, "c": course_id}
    ).first() is None:
        raise HTTPException(404, "assignment not found")


@router.get("/assignments", response_model=list[AssignmentOut])
def list_assignments(course_id: int, user: Member, conn: Conn):
    """Every assignment in the course by due date; a student also gets their own score for each."""
    _check(conn, user, course_id)
    items = _assignments(conn, course_id)
    if user.role == "student":
        mine = {s.assignment_id: s for s in grading_book.scores(conn, course_id, only_student=user.id)}
        for item in items:
            s = mine.get(item.id)
            item.mine = MyScore(
                score=s.score if s else 0, with_late=s.with_late if s else 0, possible=item.possible,
                status=s.status if s else "not_started",
            )
    return items


@router.post("/assignments", response_model=AssignmentOut, status_code=201)
def create_assignment(course_id: int, body: AssignmentIn, user: Instructor, conn: Conn):
    _check(conn, user, course_id)
    assignment_id = conn.execute(
        text("INSERT INTO assignments (course_id, title, due_at) VALUES (:c, :t, :d) RETURNING id"),
        {"c": course_id, "t": body.title, "d": body.due_at},
    ).scalar_one()
    _save_problems(conn, course_id, assignment_id, body)
    return _assignments(conn, course_id, assignment_id)[0]


@router.put("/assignments/{assignment_id}", response_model=AssignmentOut)
def update_assignment(course_id: int, assignment_id: int, body: AssignmentIn, user: Instructor, conn: Conn):
    """Changing the problems or the due date changes every score at once: scores are computed, not stored."""
    _check(conn, user, course_id)
    _owned(conn, course_id, assignment_id)
    conn.execute(
        text("UPDATE assignments SET title = :t, due_at = :d WHERE id = :a"),
        {"t": body.title, "d": body.due_at, "a": assignment_id},
    )
    _save_problems(conn, course_id, assignment_id, body)
    return _assignments(conn, course_id, assignment_id)[0]


@router.delete("/assignments/{assignment_id}", status_code=204)
def delete_assignment(course_id: int, assignment_id: int, user: Instructor, conn: Conn):
    """Removes the assignment only; the students' submissions stay."""
    _check(conn, user, course_id)
    _owned(conn, course_id, assignment_id)
    conn.execute(text("DELETE FROM assignments WHERE id = :a"), {"a": assignment_id})
    return Response(status_code=204)


def gradebook(conn: Connection, course_id: int) -> Gradebook:
    items = _assignments(conn, course_id)
    rows: dict[int, GradebookRow] = {}
    for s in grading_book.scores(conn, course_id):
        row = rows.setdefault(s.student_id, GradebookRow(
            student_id=s.student_id, label=s.label, synthetic=s.synthetic, cells=[], total=0, total_with_late=0
        ))
        row.cells.append(GradebookCell(assignment_id=s.assignment_id, score=s.score, with_late=s.with_late,
                                       status=s.status))
        row.total = round(row.total + s.score, 4)
        row.total_with_late = round(row.total_with_late + s.with_late, 4)
    order = {a.id: n for n, a in enumerate(items)}  # the columns' order (by due date), not the id order of the query
    for row in rows.values():
        row.cells.sort(key=lambda c: order[c.assignment_id])
    return Gradebook(
        assignments=[GradebookAssignment(id=a.id, title=a.title, due_at=a.due_at, possible=a.possible) for a in items],
        students=list(rows.values()),
        possible=sum(a.possible for a in items),
        lms_grades=lti_grades.readiness(lti_grades.link(conn, course_id)),
    )


@router.get("/gradebook", response_model=Gradebook)
def read_gradebook(course_id: int, user: Staff, conn: Conn):
    """Students by assignment: the on-time score, what late work would make it, and a status for each."""
    _check(conn, user, course_id)
    return gradebook(conn, course_id)


@router.post("/gradebook/send", response_model=GradeSendResult)
def send_grades(course_id: int, user: Instructor, conn: Conn):
    """Send every LMS student's on-time score for each assignment to the LMS the course was opened from."""
    _check(conn, user, course_id)
    try:
        result = lti_grades.send(conn, course_id, gradebook(conn, course_id))
    except lti_grades.GradeSyncError as exc:
        audit.record("lti.grades_refused", user_id=user.id, status=exc.status,
                     detail={"course_id": course_id, "reason": str(exc)[:200]})
        raise HTTPException(exc.status, str(exc)) from None
    audit.record("lti.grades_sent", user_id=user.id, status=200, detail={
        "course_id": course_id, "assignments": result.assignments, "scores_sent": result.scores_sent,
        "failures": len(result.failures),
    })
    return GradeSendResult(**vars(result))
