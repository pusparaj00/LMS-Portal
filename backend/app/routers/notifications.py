"""The bell (F-80): a person's own notifications, newest first. Marking one read only works on one's own."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import text

from app import notifications
from app.auth import Conn, CurrentUser, current_user
from app.schemas import NotificationList, NotificationOut

router = APIRouter(prefix="/notifications", tags=["notifications"])
Member = Annotated[CurrentUser, Depends(current_user)]
LIST_LIMIT = 40


def _my_courses(conn, user: CurrentUser) -> list[int]:
    table = "enrollments" if user.role == "student" else "course_teachers"
    return list(conn.execute(text(f"SELECT course_id FROM {table} WHERE user_id = :u"), {"u": user.id}).scalars())


@router.get("", response_model=NotificationList)
def list_notifications(user: Member, conn: Conn):
    notifications.publish_due_announcements(conn, _my_courses(conn, user))
    if user.role == "student":
        notifications.ensure_due_soon(conn, user.id)
    unread = conn.execute(
        text("SELECT count(*) FROM notifications WHERE user_id = :u AND read_at IS NULL"), {"u": user.id}
    ).scalar_one()
    rows = conn.execute(
        text(
            "SELECT id, kind, title, link, created_at, read_at IS NOT NULL AS read FROM notifications"
            " WHERE user_id = :u ORDER BY id DESC LIMIT :n"
        ),
        {"u": user.id, "n": LIST_LIMIT},
    ).mappings()
    return NotificationList(unread=unread, items=[NotificationOut(**r) for r in rows])


@router.post("/read-all", status_code=204)
def read_all(user: Member, conn: Conn):
    conn.execute(
        text("UPDATE notifications SET read_at = now() WHERE user_id = :u AND read_at IS NULL"), {"u": user.id}
    )
    return Response(status_code=204)


@router.post("/{notification_id}/read", status_code=204)
def read_one(notification_id: int, user: Member, conn: Conn):
    found = conn.execute(
        text("UPDATE notifications SET read_at = COALESCE(read_at, now()) WHERE id = :i AND user_id = :u RETURNING id"),
        {"i": notification_id, "u": user.id},
    ).first()
    if found is None:
        raise HTTPException(404, "notification not found")
    return Response(status_code=204)
