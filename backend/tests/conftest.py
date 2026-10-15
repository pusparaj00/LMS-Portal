import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.auth import create_token, hash_password
from app.main import app


@pytest.fixture(scope="session")
def owner():
    return create_engine(os.environ["OWNER_DATABASE_URL"])


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


@pytest.fixture(scope="session")
def make_user(owner):
    """Create users as the DB owner; remove them and everything they own at the end."""
    created: list[int] = []

    def factory(role: str):
        with owner.begin() as conn:
            user_id = conn.execute(
                text(
                    "INSERT INTO users (email, password_hash, role) VALUES (:e, :h, :r) RETURNING id"
                ),
                {"e": f"{role}-{uuid.uuid4().hex[:8]}@test.local", "h": hash_password("pw-12345678"), "r": role},
            ).scalar_one()
        created.append(user_id)
        return user_id, {"Authorization": f"Bearer {create_token(user_id, role)}"}

    yield factory

    if not created:
        return
    with owner.begin() as conn:
        params = {"ids": created}
        courses = "SELECT id FROM courses WHERE instructor_id = ANY(:ids)"
        problems = f"SELECT id FROM problems WHERE course_id IN ({courses})"
        subs = f"SELECT id FROM submissions WHERE user_id = ANY(:ids) OR problem_id IN ({problems})"
        for sql in [
            f"DELETE FROM mastery_events WHERE submission_id IN ({subs})",
            f"DELETE FROM run_results WHERE submission_id IN ({subs})",
            f"DELETE FROM submissions WHERE id IN ({subs})",
            f"DELETE FROM test_cases WHERE problem_id IN ({problems})",
            f"DELETE FROM problem_concepts WHERE problem_id IN ({problems})",
            f"DELETE FROM item_options WHERE problem_id IN ({problems})",
            f"DELETE FROM problems WHERE course_id IN ({courses})",
            "DELETE FROM mastery WHERE user_id = ANY(:ids)",
            "DELETE FROM mastery_events WHERE user_id = ANY(:ids)",
            "DELETE FROM chat_messages WHERE user_id = ANY(:ids)",
            f"DELETE FROM concepts WHERE course_id IN ({courses})",
            "DELETE FROM enrollments WHERE user_id = ANY(:ids)",
            f"DELETE FROM enrollments WHERE course_id IN ({courses})",
            "DELETE FROM courses WHERE instructor_id = ANY(:ids)",
            "DELETE FROM users WHERE id = ANY(:ids)",
        ]:
            conn.execute(text(sql), params)


HIDDEN_INPUT = "987654\n"
SUM_REFERENCE = "a = int(input())\nprint(a + 1)\n"
SUM_TESTS = [
    {"input": "1\n", "expected": "2\n", "hidden": False, "category": "basic"},
    {"input": "41\n", "expected": "42\n", "hidden": False, "category": "basic"},
    {"input": HIDDEN_INPUT, "expected": "987655\n", "hidden": True, "category": "large_input"},
    {"input": "-5\n", "expected": "-4\n", "hidden": True, "category": "negative_numbers"},
]


@pytest.fixture(scope="module")
def course(client, make_user, owner):
    """An instructor, a course with one concept, and one validated problem created via the API."""
    instructor_id, instructor = make_user("instructor")
    with owner.begin() as conn:
        course_id = conn.execute(
            text("INSERT INTO courses (title, instructor_id) VALUES ('Test course', :i) RETURNING id"),
            {"i": instructor_id},
        ).scalar_one()
        concept_id = conn.execute(
            text("INSERT INTO concepts (course_id, name) VALUES (:c, 'loops') RETURNING id"),
            {"c": course_id},
        ).scalar_one()
    response = client.post(
        "/api/v1/problems",
        headers=instructor,
        json={
            "course_id": course_id,
            "title": "Add one",
            "statement": "Read n, print n + 1.",
            "difficulty_b": 0.0,
            "discrimination_a": 1.0,
            "concepts": [{"concept_id": concept_id, "name": "loops", "weight": 1.0}],
            "reference_solution": SUM_REFERENCE,
            "test_cases": SUM_TESTS,
        },
    )
    assert response.status_code == 201, response.text
    return {
        "id": course_id,
        "problem_id": response.json()["id"],
        "instructor_id": instructor_id,
        "instructor": instructor,
    }
