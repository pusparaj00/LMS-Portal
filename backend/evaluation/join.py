"""F-81: join a course the way a student does, with its class code, from the evaluation and load scripts.

The scripts run inside the API container, so the code is read from the database; a real student would be given it by
the instructor."""
from sqlalchemy import text

from app.db import get_engine


def join_course(client, api: str, course_id: int, headers: dict):
    with get_engine().connect() as conn:
        code = conn.execute(text("SELECT join_code FROM courses WHERE id = :c"), {"c": course_id}).scalar_one()
    return client.post(f"{api}/courses/join", headers=headers, json={"code": code})
