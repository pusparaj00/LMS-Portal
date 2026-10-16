"""The audit trail (TR-S-08): who did what, from where and when, so a breach can be detected, scoped and reported.

Events hold numbers, addresses and short labels only: never a password, token, email address, code or message text.
An event about a refused request is written on its own connection, so it is kept when the request rolls back.
A failure to write an event is logged and never fails the request it describes.
"""
import hashlib
import hmac
import json
import logging
import re

from sqlalchemy import Connection, text

from app.config import get_settings
from app.logging import request_id_var

log = logging.getLogger("app.audit")

# Reads of one student's data by id: a run of 404s here is someone guessing other students' records.
PROBED_PATH = re.compile(r"^/api/v1/(submissions/\d+|students/me/mastery/\d+/history|probes/\d+/answer)")
# These write their own, more precise events (login, register, LTI launch), so a refusal is not recorded twice.
OWN_EVENTS_PATH = re.compile(r"^/api/v1/(auth|lti)/")

_INSERT = text(
    "INSERT INTO audit_events (event, user_id, ip, request_id, status, detail)"
    " VALUES (:e, :u, :ip, :rid, :st, CAST(:d AS jsonb))"
)


def email_tag(email: str) -> str:
    """A keyed hash of an email address: the same address always gives the same tag, but the tag reveals nothing."""
    key = get_settings().jwt_secret.encode()
    return hmac.new(key, email.strip().lower().encode(), hashlib.sha256).hexdigest()[:16]


def record(
    event: str, *, user_id: int | None = None, ip: str | None = None, status: int | None = None,
    detail: dict | None = None, conn: Connection | None = None,
) -> None:
    """Write one event. With `conn` it commits or rolls back with that work; without, it is written at once."""
    values = {
        "e": event, "u": user_id, "ip": ip, "rid": request_id_var.get(), "st": status,
        "d": json.dumps(detail or {}),
    }
    try:
        if conn is not None:
            conn.execute(_INSERT, values)
        else:
            from app.db import get_engine

            with get_engine().begin() as own:
                own.execute(_INSERT, values)
    except Exception:
        if conn is not None:
            raise  # inside a transaction a failed insert has already aborted the caller's work
        log.exception("audit event not written", extra={"fields": {"event": event}})


def for_response(path: str, method: str, status: int, user_id: int | None, ip: str) -> None:
    """The middleware's part: refused, throttled and probing requests."""
    if OWN_EVENTS_PATH.match(path) and status in (401, 403):
        return
    if status in (401, 403):
        event = "access.denied"
    elif status == 429:
        event = "rate_limited"
    elif status == 404 and PROBED_PATH.match(path):
        event = "access.not_found"
    else:
        return
    record(event, user_id=user_id, ip=ip, status=status, detail={"method": method, "path": path})


def purge(conn: Connection, days: int) -> int:
    return conn.execute(text("SELECT purge_audit_events(:d)"), {"d": days}).scalar_one()
