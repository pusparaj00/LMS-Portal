"""Deletion on request and scheduled erasure (TR-S-07).

A request never runs at once: it waits NOTICE_HOURS so the student can see the date and cancel. When it is due, the
mastery service removes the student's mastery rows (it is the only role that may), then everything else of theirs is
deleted in one transaction. Both steps can be repeated safely, so a failure half way is finished on the next sweep.
"""
import logging
from collections.abc import Callable

import redis
from sqlalchemy import Connection, Engine, text

from app import audit
from app.schemas import ErasureStatus

log = logging.getLogger("app.erasure")
NOTICE_HOURS = 48

# Child rows first. Mastery, its events and misconception state are removed by the mastery service before this runs.
_DELETIONS = [
    "DELETE FROM explanation_cache WHERE source_submission_id IN (SELECT id FROM submissions WHERE user_id = :u)",
    "DELETE FROM explanation_checks WHERE submission_id IN (SELECT id FROM submissions WHERE user_id = :u)",
    "DELETE FROM run_results WHERE submission_id IN (SELECT id FROM submissions WHERE user_id = :u)",
    "DELETE FROM submissions WHERE user_id = :u",
    "DELETE FROM chat_messages WHERE user_id = :u",
    "DELETE FROM worked_examples_seen WHERE user_id = :u",
    "DELETE FROM diagnostic_sessions WHERE user_id = :u",
    "DELETE FROM consents WHERE user_id = :u",
    "DELETE FROM item_completions WHERE user_id = :u",
    "DELETE FROM quiz_attempts WHERE user_id = :u",
    "DELETE FROM work_comments WHERE author_id = :u OR submission_id IN"
    " (SELECT id FROM work_submissions WHERE user_id = :u)",
    "DELETE FROM work_submissions WHERE user_id = :u",
    "DELETE FROM notifications WHERE user_id = :u",
    "DELETE FROM assignment_students WHERE user_id = :u",
    "DELETE FROM ratings WHERE user_id = :u",
    "DELETE FROM enrollments WHERE user_id = :u",
    "DELETE FROM lti_users WHERE user_id = :u",
    "DELETE FROM users WHERE id = :u",
]


def opened_from_lms(conn: Connection, user_id: int) -> bool:
    return conn.execute(text("SELECT 1 FROM lti_users WHERE user_id = :u"), {"u": user_id}).first() is not None


def status(conn: Connection, user_id: int) -> ErasureStatus:
    confirm_with = "lms" if opened_from_lms(conn, user_id) else "password"
    row = conn.execute(
        text("SELECT kind, notified_at, due_at FROM erasure_requests WHERE user_id = :u AND status = 'pending'"),
        {"u": user_id},
    ).first()
    if row is None:
        return ErasureStatus(confirm_with=confirm_with, pending=False, kind=None, notified_at=None, due_at=None)
    return ErasureStatus(
        confirm_with=confirm_with, pending=True, kind=row.kind, notified_at=row.notified_at, due_at=row.due_at
    )


def request(conn: Connection, user_id: int, kind: str) -> bool:
    """Records a pending request and when it will run. False if the student already has one."""
    created = conn.execute(
        text(
            "INSERT INTO erasure_requests (user_id, kind, notified_at, due_at)"
            " VALUES (:u, :k, now(), now() + make_interval(hours => :h))"
            " ON CONFLICT (user_id) WHERE status = 'pending' DO NOTHING RETURNING id"
        ),
        {"u": user_id, "k": kind, "h": NOTICE_HOURS},
    ).first()
    if created is not None:
        log.info("erasure scheduled", extra={"fields": {"user_id": user_id, "kind": kind}})
        audit.record("erasure.scheduled", user_id=user_id, detail={"kind": kind}, conn=conn)
    return created is not None


def cancel(conn: Connection, user_id: int) -> bool:
    cancelled = conn.execute(
        text("UPDATE erasure_requests SET status = 'cancelled' WHERE user_id = :u AND status = 'pending' RETURNING id"),
        {"u": user_id},
    ).first()
    if cancelled is not None:
        log.info("erasure cancelled", extra={"fields": {"user_id": user_id}})
        audit.record("erasure.cancelled", user_id=user_id, conn=conn)
    return cancelled is not None


def schedule_retention(conn: Connection, days: int) -> int:
    """Requests erasure for students with no activity for `days` days. They get the same notice period."""
    rows = conn.execute(
        text(
            "SELECT u.id FROM users u WHERE u.role = 'student' AND GREATEST("
            " u.created_at,"
            " COALESCE((SELECT max(created_at) FROM submissions WHERE user_id = u.id), u.created_at),"
            " COALESCE((SELECT max(created_at) FROM chat_messages WHERE user_id = u.id), u.created_at),"
            " COALESCE((SELECT max(GREATEST(accepted_at, withdrawn_at)) FROM consents WHERE user_id = u.id),"
            "          u.created_at)"
            ") < now() - make_interval(days => :d)"
        ),
        {"d": days},
    ).scalars().all()
    return sum(request(conn, user_id, "retention") for user_id in rows)


def redis_keys(conn: Connection, r: redis.Redis, user_id: int) -> list[str]:
    """Copies of the student's data held in Redis: chat history, explanations, probes, hint and placement state."""
    submissions = conn.execute(text("SELECT id FROM submissions WHERE user_id = :u"), {"u": user_id}).scalars()
    sessions = conn.execute(text("SELECT id FROM diagnostic_sessions WHERE user_id = :u"), {"u": user_id}).scalars()
    return [
        f"chat:{user_id}:history", f"chat:{user_id}:problem",
        *(key for s in submissions for key in (f"explain:{s}", f"probe:{s}")),
        *(f"diagnostic:{s}" for s in sessions),
        *(key.decode() for key in r.scan_iter(f"hint:{user_id}:*")),
    ]


def run_due(engine: Engine, r: redis.Redis, erase_mastery: Callable[[int], None]) -> int:
    """Carries out every request whose notice period is over. One that fails is left pending and tried again."""
    with engine.connect() as conn:
        due = conn.execute(
            text("SELECT id, user_id FROM erasure_requests WHERE status = 'pending' AND due_at <= now() ORDER BY id")
        ).all()
        conn.rollback()
    done = 0
    for request_id, user_id in due:
        try:
            erase_mastery(user_id)
            with engine.begin() as conn:
                r.delete(*redis_keys(conn, r, user_id))
                for statement in _DELETIONS:
                    conn.execute(text(statement), {"u": user_id})
                conn.execute(
                    text("UPDATE erasure_requests SET status = 'done', completed_at = now() WHERE id = :i"),
                    {"i": request_id},
                )
                audit.record("erasure.completed", user_id=user_id, conn=conn)
            done += 1
            log.info("erasure completed", extra={"fields": {"user_id": user_id}})
        except Exception:
            log.exception("erasure failed, will retry", extra={"fields": {"user_id": user_id}})
    return done
