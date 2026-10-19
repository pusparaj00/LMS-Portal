"""Course announcements (F-05). Plain text only: the page shows it as text, so nothing in it can run."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import Connection, text

from app import notifications
from app.auth import Conn, CurrentUser, can_access_course, current_user, require_role
from app.schemas import Announcement, AnnouncementIn

router = APIRouter(prefix="/courses/{course_id}/announcements", tags=["announcements"])
Instructor = Annotated[CurrentUser, Depends(require_role("instructor"))]
Member = Annotated[CurrentUser, Depends(current_user)]

_COLUMNS = "id, course_id, title, body, created_at, edited_at"


def _check(conn: Connection, user: CurrentUser, course_id: int) -> None:
    if not can_access_course(conn, user, course_id):
        raise HTTPException(403, "you have no access to this course")


def _one(conn: Connection, course_id: int, announcement_id: int) -> Announcement:
    row = conn.execute(
        text(f"SELECT {_COLUMNS} FROM announcements WHERE id = :a AND course_id = :c"),
        {"a": announcement_id, "c": course_id},
    ).mappings().first()
    if row is None:
        raise HTTPException(404, "announcement not found")
    return Announcement(**row)


@router.get("", response_model=list[Announcement])
def list_announcements(course_id: int, user: Member, conn: Conn):
    """Newest first."""
    _check(conn, user, course_id)
    rows = conn.execute(
        text(f"SELECT {_COLUMNS} FROM announcements WHERE course_id = :c ORDER BY created_at DESC, id DESC"),
        {"c": course_id},
    ).mappings()
    return [Announcement(**r) for r in rows]


@router.post("", response_model=Announcement, status_code=201)
def post_announcement(course_id: int, body: AnnouncementIn, user: Instructor, conn: Conn):
    _check(conn, user, course_id)
    announcement_id = conn.execute(
        text("INSERT INTO announcements (course_id, author_id, title, body) VALUES (:c, :u, :t, :b) RETURNING id"),
        {"c": course_id, "u": user.id, "t": body.title, "b": body.body},
    ).scalar_one()
    course = conn.execute(text("SELECT title FROM courses WHERE id = :c"), {"c": course_id}).scalar_one()
    notifications.notify_students(
        conn, course_id, "announcement", f"New announcement in {course}: {body.title}", f"#/course/{course_id}"
    )
    return _one(conn, course_id, announcement_id)


@router.put("/{announcement_id}", response_model=Announcement)
def edit_announcement(course_id: int, announcement_id: int, body: AnnouncementIn, user: Instructor, conn: Conn):
    _check(conn, user, course_id)
    _one(conn, course_id, announcement_id)
    conn.execute(
        text("UPDATE announcements SET title = :t, body = :b, edited_at = now() WHERE id = :a"),
        {"t": body.title, "b": body.body, "a": announcement_id},
    )
    return _one(conn, course_id, announcement_id)


@router.delete("/{announcement_id}", status_code=204)
def delete_announcement(course_id: int, announcement_id: int, user: Instructor, conn: Conn):
    _check(conn, user, course_id)
    _one(conn, course_id, announcement_id)
    conn.execute(text("DELETE FROM announcements WHERE id = :a"), {"a": announcement_id})
    return Response(status_code=204)
