"""TR-A-02: only the mastery role writes mastery and mastery_events."""
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError


@pytest.fixture(scope="module")
def engines():
    return {
        "owner": create_engine(os.environ["OWNER_DATABASE_URL"]),
        "api": create_engine(os.environ["DATABASE_URL"]),
        "mastery": create_engine(os.environ["MASTERY_DATABASE_URL"]),
    }


@pytest.fixture(scope="module")
def seeded(engines):
    with engines["owner"].begin() as conn:
        conn.execute(text("TRUNCATE users, courses, concepts RESTART IDENTITY CASCADE"))
        conn.execute(text("INSERT INTO users (email, password_hash, role) VALUES ('t@x.y', 'h', 'student')"))
        conn.execute(text("INSERT INTO courses (title, instructor_id) VALUES ('c', 1)"))
        conn.execute(text("INSERT INTO concepts (course_id, name) VALUES (1, 'loops')"))
    yield
    with engines["owner"].begin() as conn:
        conn.execute(text("TRUNCATE users, courses, concepts RESTART IDENTITY CASCADE"))


INSERT_MASTERY = "INSERT INTO mastery (user_id, concept_id, p_known) VALUES (1, 1, 0.5)"
INSERT_EVENT = (
    "INSERT INTO mastery_events (user_id, concept_id, p_before, p_after, evidence_type, rule_id)"
    " VALUES (1, 1, 0.5, 0.6, 'tests_passed', 'bkt_v1')"
)


@pytest.mark.parametrize(
    "statement",
    [INSERT_MASTERY, INSERT_EVENT, "UPDATE mastery SET p_known = 1", "DELETE FROM mastery_events"],
)
def test_api_role_cannot_write_mastery(engines, seeded, statement):
    with pytest.raises(ProgrammingError, match="permission denied"):
        with engines["api"].begin() as conn:
            conn.execute(text(statement))


def test_api_role_can_read_mastery_and_write_other_tables(engines, seeded):
    with engines["api"].begin() as conn:
        conn.execute(text("SELECT * FROM mastery"))
        conn.execute(text("SELECT * FROM mastery_events"))
        conn.execute(text("INSERT INTO chat_messages (user_id, role, content) VALUES (1, 'user', 'hi')"))


def test_mastery_role_writes_mastery_and_appends_events_only(engines, seeded):
    with engines["mastery"].begin() as conn:
        conn.execute(text(INSERT_MASTERY))
        conn.execute(text("UPDATE mastery SET p_known = 0.6"))
        conn.execute(text(INSERT_EVENT))
    for statement in ["UPDATE mastery_events SET p_after = 1", "DELETE FROM mastery_events"]:
        with pytest.raises(ProgrammingError, match="permission denied"):
            with engines["mastery"].begin() as conn:
                conn.execute(text(statement))
    with pytest.raises(ProgrammingError, match="permission denied"):
        with engines["mastery"].begin() as conn:
            conn.execute(text("INSERT INTO chat_messages (user_id, role, content) VALUES (1, 'user', 'x')"))


def test_schema_has_the_15_core_tables_and_no_section_10_tables(engines):
    with engines["owner"].connect() as conn:
        names = {
            r[0]
            for r in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
        } - {"alembic_version"}
    assert len(names) == 15
    assert not names & {"misconceptions", "item_options", "explanation_cache", "explanation_checks"}
