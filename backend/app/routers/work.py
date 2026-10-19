"""Handed-in work and manual grading (F-73, F-74, F-76, F-77).

A student saves a draft (text, a link, one file), turns it in and may unsubmit it until the instructor has graded it.
The instructor opens the work on one page, scores it, writes feedback and returns it. A student sees the score and the
feedback only once it is returned. A file is stored in the database, checked by its content, and only ever served back
as a download; nothing in it is opened, unpacked or run. Every view, grade and return is written to the audit trail.
"""
import base64
import binascii
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import Connection, text

from app import audit, notifications, ratelimit
from app.auth import Conn, CurrentUser, can_access_course, require_role
from app.grading_book import label
from app.routers.grading import rubric_out
from app.routers.people import teacher_ids
from app.schemas import (
    CommentIn,
    CommentOut,
    GradeIn,
    MyWork,
    ResultCount,
    ReviewGroup,
    TheirWork,
    WorkDraftIn,
    WorkList,
    WorkRow,
)
from app.synthetic import is_synthetic

router = APIRouter(prefix="/courses/{course_id}/assignments/{assignment_id}/work", tags=["work"])
queue_router = APIRouter(prefix="/instructor", tags=["work"])
Student = Annotated[CurrentUser, Depends(require_role("student"))]
Teacher = Annotated[CurrentUser, Depends(require_role("instructor"))]
MAX_FILE_BYTES = 4_500_000
UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]")
ZIP_STARTS = (b"PK\x03\x04", b"PK\x05\x06")
EXTENSIONS = (".pdf", ".txt", ".py", ".zip")


def _check_course(conn: Connection, user: CurrentUser, course_id: int) -> None:
    if not can_access_course(conn, user, course_id):
        raise HTTPException(403, "you have no access to this course")


def _work(conn: Connection, course_id: int, assignment_id: int):
    row = conn.execute(
        text(
            "SELECT a.id, a.title, a.due_at, w.instructions, w.points, w.allow_file, w.allow_link, w.allow_text,"
            " w.rubric_id, a.due_at < now() AS past_due FROM assignments a"
            " JOIN assignment_work w ON w.assignment_id = a.id"
            " WHERE a.id = :a AND a.course_id = :c"
        ),
        {"a": assignment_id, "c": course_id},
    ).first()
    if row is None:
        raise HTTPException(404, "this assignment asks for no handed-in work")
    return row


_COLUMNS = (
    "id, status, body, link, file_name, octet_length(file_data) AS file_size, turned_in_at, score, feedback,"
    " graded_at, returned_at"
)


def _submission(conn: Connection, assignment_id: int, user_id: int):
    return conn.execute(
        text(f"SELECT {_COLUMNS} FROM work_submissions WHERE assignment_id = :a AND user_id = :u"),
        {"a": assignment_id, "u": user_id},
    ).first()


def _ensure(conn: Connection, assignment_id: int, user_id: int):
    conn.execute(
        text("INSERT INTO work_submissions (assignment_id, user_id) VALUES (:a, :u) ON CONFLICT DO NOTHING"),
        {"a": assignment_id, "u": user_id},
    )
    return _submission(conn, assignment_id, user_id)


def _late(work, sub) -> bool:
    return sub is not None and sub.turned_in_at is not None and sub.turned_in_at > work.due_at


def _comments(conn: Connection, submission_id: int | None, viewer: int) -> list[CommentOut]:
    if submission_id is None:
        return []
    rows = conn.execute(
        text(
            "SELECT c.id, c.author_id, c.body, c.created_at, u.role FROM work_comments c"
            " JOIN users u ON u.id = c.author_id WHERE c.submission_id = :s ORDER BY c.id"
        ),
        {"s": submission_id},
    ).all()
    return [
        CommentOut(id=r.id, from_teacher=r.role != "student", mine=r.author_id == viewer, body=r.body,
                   created_at=r.created_at)
        for r in rows
    ]


def _chosen_levels(conn: Connection, submission_id: int | None) -> dict[int, int]:
    if submission_id is None:
        return {}
    return dict(conn.execute(
        text("SELECT criterion_id, level_id FROM work_rubric_scores WHERE submission_id = :s"), {"s": submission_id}
    ).all())


def _my_view(conn: Connection, work, user_id: int) -> MyWork:
    sub = _submission(conn, work.id, user_id)
    returned = sub is not None and sub.returned_at is not None
    if returned:
        state = "returned"
    elif sub is not None and sub.status == "turned_in":
        state = "turned_in"
    else:
        state = "missing" if work.past_due else "assigned"
    return MyWork(
        assignment_id=work.id, title=work.title, due_at=work.due_at, instructions=work.instructions,
        points=work.points, allow_file=work.allow_file, allow_link=work.allow_link, allow_text=work.allow_text,
        state=state, late=_late(work, sub),
        text=sub.body if sub else None, link=sub.link if sub else None,
        file_name=sub.file_name if sub else None, file_size=sub.file_size if sub else None,
        turned_in_at=sub.turned_in_at if sub else None,
        score=sub.score if returned else None, feedback=sub.feedback if returned else None,
        returned_at=sub.returned_at if sub else None,
        comments=_comments(conn, sub.id if sub else None, user_id),
        # the rubric is shown from the start; the levels the instructor picked only once the work is returned
        rubric=rubric_out(conn, work.rubric_id, _chosen_levels(conn, sub.id if sub and returned else None))
        if work.rubric_id else None,
    )


def _clean_file(name: str, encoded: str) -> tuple[str, bytes]:
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "the file is not valid base64") from None
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(422, "the file is larger than 4.5 MB")
    cleaned = UNSAFE_NAME.sub("_", re.split(r"[\\/]", name)[-1]).strip(" .") or "file"
    extension = next((e for e in EXTENSIONS if cleaned.lower().endswith(e)), None)
    if extension is None:
        raise HTTPException(422, "a file must be a PDF, text, Python or zip file (.pdf, .txt, .py, .zip)")
    if extension == ".pdf" and not data.startswith(b"%PDF-"):
        raise HTTPException(422, "the file is not a PDF")
    if extension == ".zip" and not data.startswith(ZIP_STARTS):
        raise HTTPException(422, "the file is not a zip file")
    if extension in (".txt", ".py"):
        try:
            if b"\x00" in data or not data.decode("utf-8").strip():
                raise ValueError
        except ValueError:
            raise HTTPException(422, "the file is not readable text") from None
    return cleaned, data


def _download(name: str, data: bytes) -> Response:
    return Response(
        content=bytes(data), media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "X-Content-Type-Options": "nosniff"},
    )


def _notify_teachers(conn: Connection, course_id: int, assignment_id: int, kind: str, title: str) -> None:
    for teacher in teacher_ids(conn, course_id):
        notifications.notify(
            conn, teacher, kind, title, notifications.work_link(course_id, assignment_id, True), course_id,
            assignment_id,
        )


_GIVEN = (
    "(NOT EXISTS (SELECT 1 FROM assignment_students g WHERE g.assignment_id = :a)"
    " OR EXISTS (SELECT 1 FROM assignment_students g WHERE g.assignment_id = :a AND g.user_id = :u))"
)


def _student_work(conn: Connection, course_id: int, assignment_id: int, user: CurrentUser):
    _check_course(conn, user, course_id)
    work = _work(conn, course_id, assignment_id)
    if not conn.execute(text(f"SELECT {_GIVEN}"), {"a": assignment_id, "u": user.id}).scalar_one():
        raise HTTPException(404, "this assignment asks for no handed-in work")
    return work


@router.get("", response_model=MyWork)
def read_my_work(course_id: int, assignment_id: int, user: Student, conn: Conn):
    work = _student_work(conn, course_id, assignment_id, user)
    return _my_view(conn, work, user.id)


@router.post("/draft", response_model=MyWork)
def save_draft(course_id: int, assignment_id: int, body: WorkDraftIn, user: Student, conn: Conn):
    ratelimit.check("work_upload", user.id)
    work = _student_work(conn, course_id, assignment_id, user)
    if body.text is not None and not work.allow_text:
        raise HTTPException(422, "this assignment does not take text")
    if body.link is not None and not work.allow_link:
        raise HTTPException(422, "this assignment does not take a link")
    if body.file_base64 is not None and not work.allow_file:
        raise HTTPException(422, "this assignment does not take a file")
    sub = _ensure(conn, assignment_id, user.id)
    if sub.status != "draft":
        raise HTTPException(409, "unsubmit your work before changing it")
    values = {"a": assignment_id, "u": user.id, "t": body.text, "l": body.link}
    sql = "UPDATE work_submissions SET body = :t, link = :l"
    if body.file_base64 is not None:
        values["fn"], values["fd"] = _clean_file(body.file_name, body.file_base64)
        sql += ", file_name = :fn, file_data = :fd"
    elif body.remove_file:
        sql += ", file_name = NULL, file_data = NULL"
    conn.execute(text(sql + " WHERE assignment_id = :a AND user_id = :u"), values)
    return _my_view(conn, work, user.id)


@router.post("/turn-in", response_model=MyWork)
def turn_in(course_id: int, assignment_id: int, user: Student, conn: Conn):
    work = _student_work(conn, course_id, assignment_id, user)
    sub = _ensure(conn, assignment_id, user.id)
    if sub.status != "draft":
        raise HTTPException(409, "this work is already turned in")
    if sub.body is None and sub.link is None and sub.file_name is None:
        raise HTTPException(422, "add some text, a link or a file before turning in")
    conn.execute(
        text("UPDATE work_submissions SET status = 'turned_in', turned_in_at = now()"
             " WHERE assignment_id = :a AND user_id = :u"),
        {"a": assignment_id, "u": user.id},
    )
    _notify_teachers(conn, course_id, assignment_id, "work_turned_in", f"Work turned in: {work.title}")
    return _my_view(conn, work, user.id)


@router.post("/unsubmit", response_model=MyWork)
def unsubmit(course_id: int, assignment_id: int, user: Student, conn: Conn):
    work = _student_work(conn, course_id, assignment_id, user)
    sub = _submission(conn, assignment_id, user.id)
    if sub is None or sub.status != "turned_in":
        raise HTTPException(409, "this work is not turned in")
    if sub.graded_at is not None:
        raise HTTPException(409, "your instructor has already graded this work, so it cannot be unsubmitted")
    conn.execute(
        text("UPDATE work_submissions SET status = 'draft', turned_in_at = NULL"
             " WHERE assignment_id = :a AND user_id = :u"),
        {"a": assignment_id, "u": user.id},
    )
    return _my_view(conn, work, user.id)


@router.get("/file")
def my_file(course_id: int, assignment_id: int, user: Student, conn: Conn):
    _student_work(conn, course_id, assignment_id, user)
    row = conn.execute(
        text("SELECT file_name, file_data FROM work_submissions WHERE assignment_id = :a AND user_id = :u"),
        {"a": assignment_id, "u": user.id},
    ).first()
    if row is None or row.file_name is None:
        raise HTTPException(404, "no file")
    return _download(row.file_name, row.file_data)


@router.post("/comments", response_model=MyWork, status_code=201)
def comment_as_student(course_id: int, assignment_id: int, body: CommentIn, user: Student, conn: Conn):
    ratelimit.check("work_comment", user.id)
    work = _student_work(conn, course_id, assignment_id, user)
    if conn.execute(
        text("SELECT comments_muted FROM enrollments WHERE course_id = :c AND user_id = :u"),
        {"c": course_id, "u": user.id},
    ).scalar():
        raise HTTPException(403, "your instructor has turned off private comments for you in this course")
    sub = _ensure(conn, assignment_id, user.id)
    conn.execute(
        text("INSERT INTO work_comments (submission_id, author_id, body) VALUES (:s, :u, :b)"),
        {"s": sub.id, "u": user.id, "b": body.body.strip()},
    )
    _notify_teachers(conn, course_id, assignment_id, "comment", f"New private comment on {work.title}")
    return _my_view(conn, work, user.id)


def _enrolled_student(conn: Connection, course_id: int, student_id: int):
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


def _teacher_state(work, sub) -> str:
    if sub is not None and sub.returned_at is not None:
        return "returned"
    if sub is not None and sub.graded_at is not None:
        return "graded"
    if sub is not None and sub.status == "turned_in":
        return "turned_in"
    return "missing" if work.past_due else "assigned"


def _their_view(conn: Connection, work, student, viewer: int) -> TheirWork:
    sub = _submission(conn, work.id, student.id)
    return TheirWork(
        student_id=student.id, label=label(student.email, student.display_name), synthetic=is_synthetic(student.email),
        title=work.title, due_at=work.due_at, instructions=work.instructions, points=work.points,
        state=_teacher_state(work, sub), late=_late(work, sub),
        text=sub.body if sub else None, link=sub.link if sub else None,
        file_name=sub.file_name if sub else None, file_size=sub.file_size if sub else None,
        turned_in_at=sub.turned_in_at if sub else None, score=sub.score if sub else None,
        feedback=sub.feedback if sub else None, graded_at=sub.graded_at if sub else None,
        returned_at=sub.returned_at if sub else None, comments=_comments(conn, sub.id if sub else None, viewer),
        rubric=rubric_out(conn, work.rubric_id, _chosen_levels(conn, sub.id if sub else None))
        if work.rubric_id else None,
    )


def _teacher_work(conn: Connection, course_id: int, assignment_id: int, user: CurrentUser):
    _check_course(conn, user, course_id)
    return _work(conn, course_id, assignment_id)


@router.get("/submissions", response_model=WorkList)
def list_submissions(course_id: int, assignment_id: int, user: Teacher, conn: Conn):
    work = _teacher_work(conn, course_id, assignment_id, user)
    rows = conn.execute(
        text(
            "SELECT u.id, u.email, u.display_name, ws.status, ws.turned_in_at, ws.score, ws.graded_at, ws.returned_at"
            " FROM enrollments e JOIN users u ON u.id = e.user_id AND u.role = 'student'"
            " LEFT JOIN work_submissions ws ON ws.assignment_id = :a AND ws.user_id = u.id"
            " WHERE e.course_id = :c AND (NOT EXISTS (SELECT 1 FROM assignment_students g WHERE g.assignment_id = :a)"
            " OR EXISTS (SELECT 1 FROM assignment_students g WHERE g.assignment_id = :a AND g.user_id = u.id))"
            " ORDER BY COALESCE(u.display_name, u.email)"
        ),
        {"a": assignment_id, "c": course_id},
    ).all()
    return WorkList(
        assignment_id=work.id, title=work.title, due_at=work.due_at, points=work.points,
        rows=[
            WorkRow(
                student_id=r.id, label=label(r.email, r.display_name), synthetic=is_synthetic(r.email),
                state=_teacher_state(work, r if r.status is not None else None),
                late=r.turned_in_at is not None and r.turned_in_at > work.due_at,
                turned_in_at=r.turned_in_at, score=r.score,
            )
            for r in rows
        ],
    )


@router.get("/students/{student_id}", response_model=TheirWork)
def read_their_work(course_id: int, assignment_id: int, student_id: int, user: Teacher, conn: Conn):
    work = _teacher_work(conn, course_id, assignment_id, user)
    student = _enrolled_student(conn, course_id, student_id)
    audit.record("work.viewed", user_id=user.id, status=200, conn=conn,
                 detail={"course_id": course_id, "assignment_id": assignment_id, "student_id": student_id})
    return _their_view(conn, work, student, user.id)


@router.get("/students/{student_id}/file")
def their_file(course_id: int, assignment_id: int, student_id: int, user: Teacher, conn: Conn):
    _teacher_work(conn, course_id, assignment_id, user)
    _enrolled_student(conn, course_id, student_id)
    row = conn.execute(
        text("SELECT file_name, file_data FROM work_submissions WHERE assignment_id = :a AND user_id = :u"),
        {"a": assignment_id, "u": student_id},
    ).first()
    if row is None or row.file_name is None:
        raise HTTPException(404, "no file")
    audit.record("work.file_downloaded", user_id=user.id, status=200, conn=conn,
                 detail={"course_id": course_id, "assignment_id": assignment_id, "student_id": student_id})
    return _download(row.file_name, row.file_data)


def _levels_with_ids(conn: Connection, work, body: GradeIn) -> dict[int, tuple[int, float]]:
    """criterion id to (chosen level id, its points), checked against the work's rubric."""
    rows = conn.execute(
        text(
            "SELECT c.id AS criterion_id, l.id AS level_id, l.points FROM rubric_criteria c"
            " JOIN rubric_levels l ON l.criterion_id = c.id WHERE c.rubric_id = :r"
        ),
        {"r": work.rubric_id},
    ).all()
    criteria = {r.criterion_id for r in rows}
    chosen = body.levels or {}
    if set(chosen) != criteria:
        raise HTTPException(422, "choose one level for every criterion of the rubric")
    by_level = {(r.criterion_id, r.level_id): r.points for r in rows}
    out = {}
    for criterion_id, level_id in chosen.items():
        if (criterion_id, level_id) not in by_level:
            raise HTTPException(422, "a chosen level does not belong to its criterion")
        out[criterion_id] = (level_id, by_level[(criterion_id, level_id)])
    return out


def _checked_levels(conn: Connection, work, body: GradeIn) -> dict[int, float]:
    """The points of each chosen level for rubric work; for other work, a plain score is required instead."""
    if not work.rubric_id:
        if body.levels:
            raise HTTPException(422, "this work has no rubric; send a score")
        return {}
    if body.score is not None:
        raise HTTPException(422, "this work is graded with a rubric; choose a level for each criterion")
    return {criterion: points for criterion, (_level, points) in _levels_with_ids(conn, work, body).items()}


@router.put("/students/{student_id}/grade", response_model=TheirWork)
def grade(course_id: int, assignment_id: int, student_id: int, body: GradeIn, user: Teacher, conn: Conn):
    work = _teacher_work(conn, course_id, assignment_id, user)
    student = _enrolled_student(conn, course_id, student_id)
    sub = _submission(conn, assignment_id, student_id)
    if sub is None or sub.status != "turned_in":
        raise HTTPException(409, "this student has not turned in work to grade")
    levels = _checked_levels(conn, work, body)
    score = sum(points for points in levels.values()) if work.rubric_id else body.score
    if score > work.points + 1e-9:
        raise HTTPException(422, f"the score cannot be more than the {work.points:g} points the work is worth")
    feedback = body.feedback.strip() if body.feedback and body.feedback.strip() else None
    conn.execute(
        text(
            "UPDATE work_submissions SET score = :s, feedback = :f, graded_at = now(), graded_by = :g"
            " WHERE assignment_id = :a AND user_id = :u"
        ),
        {"s": score, "f": feedback, "g": user.id, "a": assignment_id, "u": student_id},
    )
    if work.rubric_id:
        conn.execute(text("DELETE FROM work_rubric_scores WHERE submission_id = :s"), {"s": sub.id})
        for criterion_id, (level_id, _points) in _levels_with_ids(conn, work, body).items():
            conn.execute(
                text("INSERT INTO work_rubric_scores (submission_id, criterion_id, level_id) VALUES (:s, :c, :l)"),
                {"s": sub.id, "c": criterion_id, "l": level_id},
            )
    audit.record("work.graded", user_id=user.id, status=200, conn=conn, detail={
        "course_id": course_id, "assignment_id": assignment_id, "student_id": student_id, "score": score,
        "was_returned": sub.returned_at is not None})
    return _their_view(conn, work, student, user.id)


@router.post("/students/{student_id}/return", response_model=TheirWork)
def return_work(course_id: int, assignment_id: int, student_id: int, user: Teacher, conn: Conn):
    work = _teacher_work(conn, course_id, assignment_id, user)
    student = _enrolled_student(conn, course_id, student_id)
    sub = _submission(conn, assignment_id, student_id)
    if sub is None or sub.graded_at is None:
        raise HTTPException(409, "grade the work before returning it")
    if sub.returned_at is None:
        conn.execute(
            text("UPDATE work_submissions SET returned_at = now() WHERE assignment_id = :a AND user_id = :u"),
            {"a": assignment_id, "u": student_id},
        )
        audit.record("work.returned", user_id=user.id, status=200, conn=conn,
                     detail={"course_id": course_id, "assignment_id": assignment_id, "student_id": student_id})
        notifications.notify(
            conn, student_id, "work_returned", f"Your work was returned: {work.title}",
            notifications.work_link(course_id, assignment_id, False), course_id, assignment_id,
        )
    return _their_view(conn, work, student, user.id)


@router.post("/return-all", response_model=ResultCount)
def return_all(course_id: int, assignment_id: int, user: Teacher, conn: Conn):
    """Returns every graded piece of work that has not been returned yet."""
    work = _teacher_work(conn, course_id, assignment_id, user)
    returned = conn.execute(
        text(
            "UPDATE work_submissions SET returned_at = now() WHERE assignment_id = :a AND graded_at IS NOT NULL"
            " AND returned_at IS NULL AND user_id IN (SELECT user_id FROM enrollments WHERE course_id = :c)"
            " RETURNING user_id"
        ),
        {"a": assignment_id, "c": course_id},
    ).scalars().all()
    count = len(returned)
    for student_id in returned:
        notifications.notify(
            conn, student_id, "work_returned", f"Your work was returned: {work.title}",
            notifications.work_link(course_id, assignment_id, False), course_id, assignment_id,
        )
    if count:
        audit.record("work.returned_all", user_id=user.id, status=200, conn=conn,
                     detail={"course_id": course_id, "assignment_id": assignment_id, "count": count})
    return ResultCount(count=count)


@router.post("/students/{student_id}/comments", response_model=TheirWork, status_code=201)
def comment_as_teacher(
    course_id: int, assignment_id: int, student_id: int, body: CommentIn, user: Teacher, conn: Conn
):
    ratelimit.check("work_comment", user.id)
    work = _teacher_work(conn, course_id, assignment_id, user)
    student = _enrolled_student(conn, course_id, student_id)
    sub = _ensure(conn, assignment_id, student_id)
    conn.execute(
        text("INSERT INTO work_comments (submission_id, author_id, body) VALUES (:s, :u, :b)"),
        {"s": sub.id, "u": user.id, "b": body.body.strip()},
    )
    notifications.notify(
        conn, student_id, "comment", f"New private comment on {work.title}",
        notifications.work_link(course_id, assignment_id, False), course_id, assignment_id,
    )
    return _their_view(conn, work, student, user.id)


@queue_router.get("/to-review", response_model=list[ReviewGroup])
def to_review(user: Teacher, conn: Conn):
    """F-76: every assignment with handed-in work across the instructor's own live courses, with how many pieces wait
    for a score, how many are scored and how many of those are not yet returned."""
    rows = conn.execute(
        text(
            "SELECT c.id AS course_id, c.title AS course_title, a.id AS assignment_id, a.title, a.due_at,"
            " count(*) FILTER (WHERE ws.status = 'turned_in' AND ws.graded_at IS NULL) AS waiting,"
            " count(*) FILTER (WHERE ws.graded_at IS NOT NULL) AS graded,"
            " count(*) FILTER (WHERE ws.graded_at IS NOT NULL AND ws.returned_at IS NULL) AS not_returned"
            " FROM courses c JOIN assignments a ON a.course_id = c.id"
            " JOIN assignment_work aw ON aw.assignment_id = a.id"
            " LEFT JOIN work_submissions ws ON ws.assignment_id = a.id"
            " AND ws.user_id IN (SELECT user_id FROM enrollments WHERE course_id = c.id)"
            " WHERE c.archived_at IS NULL AND EXISTS ("
            "  SELECT 1 FROM course_teachers t WHERE t.course_id = c.id AND t.user_id = :u)"
            " GROUP BY c.id, a.id"
            " ORDER BY (count(*) FILTER (WHERE ws.status = 'turned_in' AND ws.graded_at IS NULL)) DESC,"
            " a.due_at DESC, a.id"
        ),
        {"u": user.id},
    ).all()
    return [ReviewGroup(**r._mapping) for r in rows]
