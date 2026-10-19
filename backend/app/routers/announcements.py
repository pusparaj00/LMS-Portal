"""Course announcements (F-05, F-85). Plain text only: the page shows it as text, so nothing in it can run.

A teacher can post at once, save a draft, or schedule a post for later. Students see an announcement only once it is
published; drafts and scheduled posts are visible to the course's teachers alone. The students are notified once, when
the post becomes visible (see notifications.publish_due_announcements)."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import Connection, text

from app import notifications
from app.auth import Conn, CurrentUser, can_access_course, current_user, require_role
from app.schemas import Announcement, AnnouncementIn

router = APIRouter(prefix="/courses/{course_id}/announcements", tags=["announcements"])
Instructor = Annotated[CurrentUser, Depends(require_role("instructor"))]
Member = Annotated[CurrentUser, Depends(current_user)]

_COLUMNS = (
    "id, course_id, title, body, created_at, edited_at, publish_at,"
    " CASE WHEN is_draft THEN 'draft' WHEN publish_at > now() THEN 'scheduled' ELSE 'published' END AS state"
)
_VISIBLE_TO_STUDENTS = "NOT is_draft AND COALESCE(publish_at, created_at) <= now()"
_ORDER = "ORDER BY COALESCE(publish_at, created_at) DESC, id DESC"


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


def _timing(body: AnnouncementIn) -> dict:
    """The stored form of how a post is published: a draft has no time, a scheduled post has one."""
    return {"draft": body.mode == "draft", "at": body.publish_at if body.mode == "schedule" else None}


@router.get("", response_model=list[Announcement])
def list_announcements(course_id: int, user: Member, conn: Conn):
    """Newest first. A student sees published posts only; a teacher also sees drafts and scheduled posts."""
    _check(conn, user, course_id)
    notifications.publish_due_announcements(conn, [course_id])
    where = f" AND {_VISIBLE_TO_STUDENTS}" if user.role == "student" else ""
    rows = conn.execute(
        text(f"SELECT {_COLUMNS} FROM announcements WHERE course_id = :c{where} {_ORDER}"), {"c": course_id}
    ).mappings()
    return [Announcement(**r) for r in rows]


@router.post("", response_model=Announcement, status_code=201)
def post_announcement(course_id: int, body: AnnouncementIn, user: Instructor, conn: Conn):
    _check(conn, user, course_id)
    timing = _timing(body)
    announcement_id = conn.execute(
        text(
            "INSERT INTO announcements (course_id, author_id, title, body, is_draft, publish_at)"
            " VALUES (:c, :u, :t, :b, CAST(:draft AS boolean), CAST(:at AS timestamptz)) RETURNING id"
        ),
        {"c": course_id, "u": user.id, "t": body.title, "b": body.body, **timing},
    ).scalar_one()
    notifications.publish_due_announcements(conn, [course_id])
    return _one(conn, course_id, announcement_id)


@router.put("/{announcement_id}", response_model=Announcement)
def edit_announcement(course_id: int, announcement_id: int, body: AnnouncementIn, user: Instructor, conn: Conn):
    """Changes the text and how the post is published (for example a draft becomes a post now)."""
    _check(conn, user, course_id)
    _one(conn, course_id, announcement_id)
    conn.execute(
        text(
            "UPDATE announcements SET title = :t, body = :b, edited_at = now(), is_draft = CAST(:draft AS boolean),"
            " publish_at = CAST(:at AS timestamptz),"
            " notified_at = CASE WHEN CAST(:draft AS boolean) OR CAST(:at AS timestamptz) IS NOT NULL THEN NULL"
            " ELSE notified_at END WHERE id = :a"
        ),
        {"t": body.title, "b": body.body, "a": announcement_id, **_timing(body)},
    )
    notifications.publish_due_announcements(conn, [course_id])
    return _one(conn, course_id, announcement_id)


@router.delete("/{announcement_id}", status_code=204)
def delete_announcement(course_id: int, announcement_id: int, user: Instructor, conn: Conn):
    _check(conn, user, course_id)
    _one(conn, course_id, announcement_id)
    conn.execute(text("DELETE FROM announcements WHERE id = :a"), {"a": announcement_id})
    return Response(status_code=204)
