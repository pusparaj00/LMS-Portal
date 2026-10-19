"""In-app notifications (F-80). Nothing is sent by email, and a notification names things (an assignment, an
announcement title) but never holds a score, a comment, feedback or any work: those are read from their own pages,
where the access rules apply."""
from datetime import timedelta

from sqlalchemy import Connection, text

from app import todo

DUE_SOON = timedelta(hours=48)
_INSERT = (
    "INSERT INTO notifications (user_id, kind, course_id, assignment_id, title, link)"
    " VALUES (:u, :k, :c, :a, :t, :l)"
)


def notify(
    conn: Connection, user_id: int, kind: str, title: str, link: str, course_id: int | None = None,
    assignment_id: int | None = None,
) -> None:
    conn.execute(text(_INSERT), {"u": user_id, "k": kind, "c": course_id, "a": assignment_id, "t": title[:300],
                                 "l": link})


def publish_due_announcements(conn: Connection, course_ids: list[int]) -> None:
    """Notifies each course's students, once, of every announcement that has become visible. Whoever asks first does
    it: the update hands each announcement to exactly one caller, so a scheduled post is announced when its time has
    come the next time anyone in the course looks, and never twice."""
    due = conn.execute(
        text(
            "UPDATE announcements a SET notified_at = now() FROM courses c WHERE c.id = a.course_id"
            " AND a.course_id = ANY(:ids) AND a.notified_at IS NULL AND NOT a.is_draft"
            " AND COALESCE(a.publish_at, a.created_at) <= now() RETURNING a.course_id, a.title, c.title AS course"
        ),
        {"ids": course_ids},
    ).all()
    for row in due:
        conn.execute(
            text(
                "INSERT INTO notifications (user_id, kind, course_id, title, link)"
                " SELECT e.user_id, 'announcement', :c, :t, :l FROM enrollments e JOIN users u ON u.id = e.user_id"
                " WHERE e.course_id = :c AND u.role = 'student'"
            ),
            {"c": row.course_id, "t": f"New announcement in {row.course}: {row.title}"[:300],
             "l": f"#/course/{row.course_id}"},
        )


def work_link(course_id: int, assignment_id: int, teacher: bool) -> str:
    return f"#/course/{course_id}/assignment/{assignment_id}" + ("/review" if teacher else "")


def ensure_due_soon(conn: Connection, user_id: int) -> None:
    """One 'due soon' notification per assignment the student has not finished and that is due within 48 hours. The
    unique index makes this safe to run on every read."""
    now = conn.execute(text("SELECT now()")).scalar_one()
    for item in todo.items(conn, user_id):
        if item.state == "assigned" and item.due_at - now <= DUE_SOON:
            conn.execute(
                text(_INSERT + " ON CONFLICT (user_id, assignment_id) WHERE kind = 'due_soon' DO NOTHING"),
                {"u": user_id, "k": "due_soon", "c": item.course_id, "a": item.assignment_id,
                 "t": f"Due soon: {item.title} ({item.course_title})",
                 "l": work_link(item.course_id, item.assignment_id, False) if item.has_work
                 else f"#/course/{item.course_id}"},
            )
