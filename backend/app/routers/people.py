"""People in a course (F-82): who teaches it, who is in it, co-teachers and muting.

A teacher sees every student. A student sees the teachers and how many classmates there are, never a classmate's name
(the privacy notice promises that other students cannot see their work or identity). Adding or removing a co-teacher is
for the course's owner; muting a student's private comments is for any of its teachers.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import Connection, text

from app import audit
from app.auth import Conn, CurrentUser, can_access_course, current_user, require_role
from app.grading_book import label
from app.schemas import Classmate, CoTeacherIn, MuteIn, People, Teacher

router = APIRouter(prefix="/courses/{course_id}", tags=["people"])
Member = Annotated[CurrentUser, Depends(current_user)]
Instructor = Annotated[CurrentUser, Depends(require_role("instructor"))]


def _check(conn: Connection, user: CurrentUser, course_id: int) -> None:
    if not can_access_course(conn, user, course_id):
        raise HTTPException(403, "you have no access to this course")


def _owner_only(conn: Connection, user: CurrentUser, course_id: int) -> None:
    _check(conn, user, course_id)
    if conn.execute(
        text("SELECT 1 FROM courses WHERE id = :c AND instructor_id = :u"), {"c": course_id, "u": user.id}
    ).first() is None:
        raise HTTPException(403, "only the course's owner can change who teaches it")


def teacher_ids(conn: Connection, course_id: int) -> list[int]:
    return list(conn.execute(
        text("SELECT user_id FROM course_teachers WHERE course_id = :c ORDER BY user_id"), {"c": course_id}
    ).scalars())


def _teachers(conn: Connection, course_id: int) -> list[Teacher]:
    rows = conn.execute(
        text(
            "SELECT u.id, u.email, u.display_name, u.id = c.instructor_id AS owner FROM course_teachers t"
            " JOIN users u ON u.id = t.user_id JOIN courses c ON c.id = t.course_id WHERE t.course_id = :c"
            " ORDER BY owner DESC, t.added_at, u.id"
        ),
        {"c": course_id},
    ).all()
    return [Teacher(user_id=r.id, label=label(r.email, r.display_name), owner=r.owner) for r in rows]


@router.get("/people", response_model=People)
def read_people(course_id: int, user: Member, conn: Conn):
    _check(conn, user, course_id)
    owner = conn.execute(text("SELECT instructor_id FROM courses WHERE id = :c"), {"c": course_id}).scalar()
    if owner is None:
        raise HTTPException(404, "course not found")
    students = conn.execute(
        text(
            "SELECT u.id, u.email, u.display_name, e.comments_muted, e.enrolled_at FROM enrollments e"
            " JOIN users u ON u.id = e.user_id AND u.role = 'student' WHERE e.course_id = :c"
            " ORDER BY COALESCE(u.display_name, u.email)"
        ),
        {"c": course_id},
    ).all()
    return People(
        teachers=_teachers(conn, course_id), student_count=len(students),
        can_manage_teachers=owner == user.id,
        students=None if user.role == "student" else [
            Classmate(user_id=r.id, label=label(r.email, r.display_name), muted=r.comments_muted,
                      joined_at=r.enrolled_at)
            for r in students
        ],
    )


@router.post("/teachers", response_model=People, status_code=201)
def add_co_teacher(course_id: int, body: CoTeacherIn, user: Instructor, conn: Conn):
    """Adds an existing instructor account as a co-teacher. They can then teach the course like its owner, except for
    archiving it and changing who teaches it."""
    _owner_only(conn, user, course_id)
    found = conn.execute(
        text("SELECT id FROM users WHERE lower(email) = lower(:e) AND role = 'instructor' AND disabled_at IS NULL"),
        {"e": body.email.strip()},
    ).first()
    if found is None:
        raise HTTPException(404, "there is no active instructor account with that email address")
    added = conn.execute(
        text("INSERT INTO course_teachers (course_id, user_id) VALUES (:c, :u) ON CONFLICT DO NOTHING RETURNING 1"),
        {"c": course_id, "u": found.id},
    ).first()
    if added is None:
        raise HTTPException(409, "that instructor already teaches this course")
    audit.record("course.co_teacher_added", user_id=user.id, status=201, conn=conn,
                 detail={"course_id": course_id, "teacher_id": found.id})
    return read_people(course_id, user, conn)


@router.delete("/teachers/{teacher_id}", status_code=204)
def remove_co_teacher(course_id: int, teacher_id: int, user: Instructor, conn: Conn):
    _owner_only(conn, user, course_id)
    removed = conn.execute(
        text(
            "DELETE FROM course_teachers WHERE course_id = :c AND user_id = :t"
            " AND user_id <> (SELECT instructor_id FROM courses WHERE id = :c) RETURNING 1"
        ),
        {"c": course_id, "t": teacher_id},
    ).first()
    if removed is None:
        raise HTTPException(404, "that person is not a co-teacher of this course")
    audit.record("course.co_teacher_removed", user_id=user.id, status=204, conn=conn,
                 detail={"course_id": course_id, "teacher_id": teacher_id})
    return Response(status_code=204)


@router.put("/students/{student_id}/mute", response_model=People)
def mute_student(course_id: int, student_id: int, body: MuteIn, user: Instructor, conn: Conn):
    """A muted student can still read their comments but cannot send new private comments in this course."""
    _check(conn, user, course_id)
    changed = conn.execute(
        text(
            "UPDATE enrollments SET comments_muted = :m WHERE course_id = :c AND user_id = :s"
            " AND user_id IN (SELECT id FROM users WHERE role = 'student') RETURNING 1"
        ),
        {"m": body.muted, "c": course_id, "s": student_id},
    ).first()
    if changed is None:
        raise HTTPException(404, "that student is not in this course")
    audit.record("course.student_muted", user_id=user.id, status=200, conn=conn,
                 detail={"course_id": course_id, "student_id": student_id, "muted": body.muted})
    return read_people(course_id, user, conn)
