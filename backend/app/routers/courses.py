from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from app.auth import Conn, CurrentUser, can_access_course, current_user, require_role
from app.schemas import Course, CourseConcept, CourseCreate

router = APIRouter(prefix="/courses", tags=["courses"])


@router.get("", response_model=list[Course])
def list_courses(user: Annotated[CurrentUser, Depends(current_user)], conn: Conn):
    rows = conn.execute(
        text(
            "SELECT c.id, c.title, c.instructor_id,"
            " EXISTS (SELECT 1 FROM enrollments e WHERE e.course_id = c.id AND e.user_id = :u)"
            " AS enrolled FROM courses c ORDER BY c.id"
        ),
        {"u": user.id},
    ).mappings()
    return [dict(r) for r in rows]


@router.post("", response_model=Course, status_code=201)
def create_course(
    body: CourseCreate,
    user: Annotated[CurrentUser, Depends(require_role("instructor"))],
    conn: Conn,
):
    row = conn.execute(
        text(
            "INSERT INTO courses (title, instructor_id) VALUES (:t, :u)"
            " RETURNING id, title, instructor_id"
        ),
        {"t": body.title, "u": user.id},
    ).mappings().one()
    return {**row, "enrolled": False}


@router.post("/{course_id}/enroll", status_code=204)
def enroll(
    course_id: int, user: Annotated[CurrentUser, Depends(require_role("student"))], conn: Conn
):
    if conn.execute(text("SELECT 1 FROM courses WHERE id = :c"), {"c": course_id}).first() is None:
        raise HTTPException(404, "course not found")
    conn.execute(
        text("INSERT INTO enrollments (user_id, course_id) VALUES (:u, :c) ON CONFLICT DO NOTHING"),
        {"u": user.id, "c": course_id},
    )


@router.get("/{course_id}/concepts", response_model=list[CourseConcept])
def list_concepts(course_id: int, user: Annotated[CurrentUser, Depends(current_user)], conn: Conn):
    """The concepts problems and notes can be tagged with (F-02)."""
    if not can_access_course(conn, user, course_id):
        raise HTTPException(403, "you have no access to this course")
    rows = conn.execute(
        text("SELECT id AS concept_id, name FROM concepts WHERE course_id = :c ORDER BY id"), {"c": course_id}
    ).mappings()
    return [dict(r) for r in rows]
