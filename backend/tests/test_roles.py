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


@pytest.fixture
def ids(engines, make_user):
    student_id, _ = make_user("student")
    instructor_id, _ = make_user("instructor")
    with engines["owner"].begin() as conn:
        course_id = conn.execute(
            text("INSERT INTO courses (title, instructor_id) VALUES ('roles', :i) RETURNING id"),
            {"i": instructor_id},
        ).scalar_one()
        concept_id = conn.execute(
            text("INSERT INTO concepts (course_id, name) VALUES (:c, 'loops') RETURNING id"),
            {"c": course_id},
        ).scalar_one()
    yield {"u": student_id, "c": concept_id}
    with engines["owner"].begin() as conn:
        conn.execute(text("DELETE FROM mastery_events WHERE user_id = :u"), {"u": student_id})
        conn.execute(text("DELETE FROM mastery WHERE user_id = :u"), {"u": student_id})


INSERT_MASTERY = "INSERT INTO mastery (user_id, concept_id, p_known) VALUES (:u, :c, 0.5)"
INSERT_EVENT = (
    "INSERT INTO mastery_events (user_id, concept_id, p_before, p_after, evidence_type, rule_id)"
    " VALUES (:u, :c, 0.5, 0.6, 'tests_passed', 'bkt_v1')"
)
INSERT_CHAT = "INSERT INTO chat_messages (user_id, role, content) VALUES (:u, 'user', 'hi')"


@pytest.mark.parametrize(
    "statement",
    [INSERT_MASTERY, INSERT_EVENT, "UPDATE mastery SET p_known = 1", "DELETE FROM mastery_events"],
)
def test_api_role_cannot_write_mastery(engines, ids, statement):
    with pytest.raises(ProgrammingError, match="permission denied"):
        with engines["api"].begin() as conn:
            conn.execute(text(statement), ids)


def test_api_role_can_read_mastery_and_write_other_tables(engines, ids):
    with engines["api"].begin() as conn:
        conn.execute(text("SELECT * FROM mastery"))
        conn.execute(text("SELECT * FROM mastery_events"))
        conn.execute(text(INSERT_CHAT), ids)


def test_mastery_role_writes_mastery_and_appends_events_only(engines, ids):
    with engines["mastery"].begin() as conn:
        conn.execute(text(INSERT_MASTERY), ids)
        conn.execute(text("UPDATE mastery SET p_known = 0.6 WHERE user_id = :u"), ids)
        conn.execute(text(INSERT_EVENT), ids)
    for statement in ["UPDATE mastery_events SET p_after = 1", "DELETE FROM mastery_events"]:
        with pytest.raises(ProgrammingError, match="permission denied"):
            with engines["mastery"].begin() as conn:
                conn.execute(text(statement))
    with pytest.raises(ProgrammingError, match="permission denied"):
        with engines["mastery"].begin() as conn:
            conn.execute(text(INSERT_CHAT), ids)


def test_schema_has_the_core_tables_and_the_later_additions(engines):
    with engines["owner"].connect() as conn:
        names = {
            r[0]
            for r in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
        } - {"alembic_version"}
    assert len(names) == 25
    assert names >= {
        "misconceptions", "item_options", "mastery_params", "evidence_concept_map", "misconception_state",
        "explanation_checks", "explanation_cache", "consents",
    }
