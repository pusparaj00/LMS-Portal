import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.auth import create_token, hash_password
from app.consent import CONSENT_VERSION
from app.main import app
from tests.prepare_db import TEST_DATABASE

# The suite creates, changes and deletes data by the thousand, so it must never run against the app's own database,
# whatever the environment says. This stops the whole run before any test starts.
for _name in ("OWNER_DATABASE_URL", "DATABASE_URL", "MASTERY_DATABASE_URL", "CHAT_DATABASE_URL"):
    if not os.environ.get(_name, "").rsplit("/", 1)[-1] == TEST_DATABASE:
        pytest.exit(f"{_name} must point at the database '{TEST_DATABASE}'; the tests never run against app data", 2)
if not os.environ.get("REDIS_URL", "").endswith("/1"):
    pytest.exit("REDIS_URL must use Redis database 1 for tests; database 0 holds the app's own data", 2)


@pytest.fixture(autouse=True)
def fresh_rate_limits():
    """Counters live in Redis and survive between runs; every test starts with none."""
    from app.db import get_redis

    r = get_redis()
    keys = list(r.scan_iter("rl:*"))
    if keys:
        r.delete(*keys)


@pytest.fixture(scope="session")
def owner():
    return create_engine(os.environ["OWNER_DATABASE_URL"])


@pytest.fixture(autouse=True)
def fresh_explanation_cache(owner):
    """Each test starts without the stored explanations other tests made; the app's own entries are kept."""
    newest = "SELECT COALESCE(max(id), 0) FROM explanation_cache"
    with owner.connect() as conn:
        before = conn.execute(text(newest)).scalar_one()
    yield
    with owner.begin() as conn:
        conn.execute(text("DELETE FROM explanation_cache WHERE id > :b"), {"b": before})


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


@pytest.fixture(scope="session")
def make_user(owner):
    """Create users as the DB owner; remove them and everything they own at the end."""
    created: list[int] = []

    def factory(role: str, consented: bool = True):
        """Students have agreed to the privacy notice unless a test needs one who has not (TR-S-05)."""
        with owner.begin() as conn:
            user_id = conn.execute(
                text(
                    "INSERT INTO users (email, password_hash, role) VALUES (:e, :h, :r) RETURNING id"
                ),
                {"e": f"{role}-{uuid.uuid4().hex[:8]}@test.local", "h": hash_password("pw-12345678"), "r": role},
            ).scalar_one()
            if role == "student" and consented:
                conn.execute(
                    text("INSERT INTO consents (user_id, version, adult_confirmed) VALUES (:u, :v, true)"),
                    {"u": user_id, "v": CONSENT_VERSION},
                )
        created.append(user_id)
        return user_id, {"Authorization": f"Bearer {create_token(user_id, role)}"}

    yield factory

    if not created:
        return
    with owner.begin() as conn:
        params = {"ids": created}
        courses = "SELECT id FROM courses WHERE instructor_id = ANY(:ids)"
        concepts = f"SELECT id FROM concepts WHERE course_id IN ({courses})"
        problems = f"SELECT id FROM problems WHERE course_id IN ({courses})"
        subs = f"SELECT id FROM submissions WHERE user_id = ANY(:ids) OR problem_id IN ({problems})"
        for sql in [
            f"DELETE FROM explanation_checks WHERE submission_id IN ({subs})",
            f"DELETE FROM mastery_events WHERE submission_id IN ({subs})",
            f"DELETE FROM run_results WHERE submission_id IN ({subs})",
            f"DELETE FROM submissions WHERE id IN ({subs})",
            f"DELETE FROM assignment_problems WHERE problem_id IN ({problems})",
            f"DELETE FROM assignments WHERE course_id IN ({courses})",
            f"DELETE FROM announcements WHERE course_id IN ({courses})",
            f"DELETE FROM ratings WHERE course_id IN ({courses})",
            f"DELETE FROM test_cases WHERE problem_id IN ({problems})",
            f"DELETE FROM problem_concepts WHERE problem_id IN ({problems})",
            f"DELETE FROM item_options WHERE problem_id IN ({problems})",
            f"DELETE FROM chunks WHERE document_id IN (SELECT id FROM documents WHERE course_id IN ({courses}))",
            f"DELETE FROM documents WHERE course_id IN ({courses})",
            "DELETE FROM misconception_state WHERE user_id = ANY(:ids)",
            f"DELETE FROM misconceptions WHERE concept_id IN ({concepts})",
            f"DELETE FROM mastery_params WHERE concept_id IN ({concepts})",
            f"DELETE FROM evidence_concept_map WHERE concept_id IN ({concepts})",
            "DELETE FROM diagnostic_sessions WHERE user_id = ANY(:ids)",
            f"DELETE FROM problems WHERE course_id IN ({courses})",
            f"DELETE FROM mastery_events WHERE concept_id IN ({concepts})",
            f"DELETE FROM mastery WHERE concept_id IN ({concepts})",
            "DELETE FROM mastery WHERE user_id = ANY(:ids)",
            "DELETE FROM mastery_events WHERE user_id = ANY(:ids)",
            "DELETE FROM chat_messages WHERE user_id = ANY(:ids)",
            "DELETE FROM consents WHERE user_id = ANY(:ids)",
            "DELETE FROM erasure_requests WHERE user_id = ANY(:ids)",
            "DELETE FROM lti_users WHERE user_id = ANY(:ids)",
            f"DELETE FROM lti_contexts WHERE course_id IN ({courses})",
            "DELETE FROM lti_platforms WHERE issuer LIKE 'https://erasure-%'",
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


PLACEMENT_RIGHT = "print(int(input()) + 1)\n"


@pytest.fixture(scope="module")
def placement_course(make_user, owner):
    """A small synthetic course: 3 concepts, 9 tracing items tagged with 2 misconceptions, 3 coding tasks."""
    instructor_id, instructor = make_user("instructor")
    tag = uuid.uuid4().hex[:6]
    with owner.begin() as conn:
        course_id = conn.execute(
            text("INSERT INTO courses (title, instructor_id) VALUES ('Placement test course', :i) RETURNING id"),
            {"i": instructor_id},
        ).scalar_one()
        concepts = [
            conn.execute(
                text("INSERT INTO concepts (course_id, name) VALUES (:c, :n) RETURNING id"),
                {"c": course_id, "n": name},
            ).scalar_one()
            for name in ("alpha", "beta", "gamma")
        ]
        # beta builds on alpha and gamma on beta, so a sharp drop is passed back along the chain
        for child, parent in ((concepts[1], concepts[0]), (concepts[2], concepts[1])):
            conn.execute(
                text("UPDATE concepts SET parent_ids = ARRAY[CAST(:p AS integer)] WHERE id = :c"),
                {"p": parent, "c": child},
            )
        misconceptions = [
            conn.execute(
                text("INSERT INTO misconceptions (concept_id, name, description) VALUES (:c, :n, :d) RETURNING id"),
                {"c": concepts[i], "n": f"m{i}_{tag}", "d": f"misconception {i}"},
            ).scalar_one()
            for i in range(2)
        ]

        def problem(title, kind, b):
            return conn.execute(
                text(
                    "INSERT INTO problems (course_id, title, statement, kind, difficulty_b, discrimination_a,"
                    " reference_solution) VALUES (:c, :t, 'statement', :k, :b, 1.0, :r) RETURNING id"
                ),
                {"c": course_id, "t": title, "k": kind, "b": b, "r": PLACEMENT_RIGHT if kind == "code" else None},
            ).scalar_one()

        for n in range(9):
            pid = problem(f"item {n}", "mcq", -0.6 + 0.15 * n)
            conn.execute(
                text("INSERT INTO problem_concepts VALUES (:p, :c, 1.0)"), {"p": pid, "c": concepts[n % 3]}
            )
            conn.execute(
                text("INSERT INTO item_options (problem_id, option_text, is_correct) VALUES (:p, 'right', true)"),
                {"p": pid},
            )
            for m in misconceptions:
                conn.execute(
                    text(
                        "INSERT INTO item_options (problem_id, option_text, is_correct, misconception_id)"
                        " VALUES (:p, :t, false, :m)"
                    ),
                    {"p": pid, "t": f"wrong {m}", "m": m},
                )
        for n in range(3):
            pid = problem(f"task {n}", "code", 0.0)
            conn.execute(
                text("INSERT INTO problem_concepts VALUES (:p, :c, 1.0)"), {"p": pid, "c": concepts[n]}
            )
            conn.execute(
                text(
                    "INSERT INTO test_cases (problem_id, input, expected, hidden, category)"
                    " VALUES (:p, :i1, :e1, false, 'basic'), (:p, :i2, :e2, true, 'basic')"
                ),
                {"p": pid, "i1": "1\n", "e1": "2\n", "i2": "9\n", "e2": "10\n"},
            )
    return {"course_id": course_id, "concepts": concepts, "misconceptions": misconceptions, "tag": tag}
