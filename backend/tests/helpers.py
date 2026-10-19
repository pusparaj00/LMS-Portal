"""Shared test helpers."""
import os

from sqlalchemy import create_engine, text

API = "/api/v1"
_owner = None


def join_code(course_id: int) -> str:
    global _owner
    if _owner is None:
        _owner = create_engine(os.environ["OWNER_DATABASE_URL"])
    with _owner.connect() as conn:
        return conn.execute(text("SELECT join_code FROM courses WHERE id = :c"), {"c": course_id}).scalar_one()


def enroll(client, course_id: int, headers):
    """A student joins a course the way a real one does: with its class code."""
    return client.post(f"{API}/courses/join", headers=headers, json={"code": join_code(course_id)})
