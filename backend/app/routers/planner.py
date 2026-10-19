"""To-do (F-78) and calendar (F-79): a person's own deadlines, from the assignments of their own courses only."""
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from app import todo
from app.auth import Conn, CurrentUser, require_role
from app.schemas import CalendarItem, TodoOut

router = APIRouter(tags=["planner"])
Student = Annotated[CurrentUser, Depends(require_role("student"))]
Planner = Annotated[CurrentUser, Depends(require_role("student", "instructor"))]
MAX_SPAN = timedelta(days=100)


@router.get("/students/me/todo", response_model=list[TodoOut])
def my_todo(user: Student, conn: Conn):
    """Every assignment of the student's live courses, soonest first, each marked assigned, missing or done."""
    return [TodoOut(**vars(i)) for i in todo.items(conn, user.id)]


@router.get("/calendar", response_model=list[CalendarItem])
def calendar(
    user: Planner, conn: Conn, start: Annotated[datetime, Query()], end: Annotated[datetime, Query()],
    course_id: int | None = None,
):
    """Due dates between `start` and `end` (at most 100 days) for the courses the caller is in or teaches."""
    if start.tzinfo is None or end.tzinfo is None:
        raise HTTPException(422, "give start and end with a time zone, for example 2026-11-01T00:00:00+05:30")
    if end <= start or end - start > MAX_SPAN:
        raise HTTPException(422, "end must be after start, and at most 100 days later")
    if user.role == "student":
        state = {(i.course_id, i.assignment_id): i for i in todo.items(conn, user.id, course_id)}
        return [
            CalendarItem(assignment_id=i.assignment_id, course_id=i.course_id, course_title=i.course_title,
                         title=i.title, due_at=i.due_at, state=i.state, has_work=i.has_work)
            for i in state.values() if start <= i.due_at < end
        ]
    rows = conn.execute(
        text(
            "SELECT a.id, a.course_id, c.title AS course_title, a.title, a.due_at,"
            " EXISTS (SELECT 1 FROM assignment_work w WHERE w.assignment_id = a.id) AS has_work"
            " FROM assignments a JOIN courses c ON c.id = a.course_id"
            " WHERE c.instructor_id = :u AND c.archived_at IS NULL AND a.due_at >= :s AND a.due_at < :e"
            " AND (CAST(:c AS integer) IS NULL OR c.id = :c) ORDER BY a.due_at, a.id"
        ),
        {"u": user.id, "s": start, "e": end, "c": course_id},
    ).all()
    return [
        CalendarItem(assignment_id=r.id, course_id=r.course_id, course_title=r.course_title, title=r.title,
                     due_at=r.due_at, has_work=r.has_work)
        for r in rows
    ]
