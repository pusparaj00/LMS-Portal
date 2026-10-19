"""TR-S-01, TR-S-02, TR-V-07: role and ownership checks on every endpoint."""
import time

import jwt
import pytest
from sqlalchemy import text

from app.config import get_settings
from tests.helpers import enroll

API = "/api/v1"
CODE = "print(int(input()) + 1)\n"


@pytest.fixture(scope="module")
def students(client, make_user, course, owner):
    a_id, a = make_user("student")
    b_id, b = make_user("student")
    with owner.begin() as conn:
        conn.execute(
            text("INSERT INTO enrollments (user_id, course_id) VALUES (:u, :c)"),
            {"u": a_id, "c": course["id"]},
        )
    return a, b


PROTECTED = [
    ("get", "/courses"),
    ("post", "/courses"),
    ("post", "/courses/join"),
    ("get", "/problems?course_id=1"),
    ("get", "/problems/1"),
    ("post", "/problems"),
    ("post", "/submissions"),
    ("post", "/submissions/run"),
    ("get", "/submissions/1"),
    ("post", "/diagnostic/start"),
    ("post", "/diagnostic/answer"),
    ("get", "/students/me/mastery?course_id=1"),
    ("get", "/students/me/mastery/1/history"),
    ("post", "/chat"),
]


@pytest.mark.parametrize("method,path", PROTECTED)
def test_anonymous_is_rejected_everywhere(client, method, path):
    response = getattr(client, method)(API + path)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "http_error"


def test_student_cannot_call_instructor_endpoints(client, students, course):
    a, _ = students
    assert client.post(f"{API}/courses", headers=a, json={"title": "x"}).status_code == 403
    assert client.post(f"{API}/problems", headers=a, json={}).status_code == 403


def test_instructor_cannot_use_student_endpoints(client, course):
    ins = course["instructor"]
    body = {"problem_id": course["problem_id"], "code": CODE}
    assert client.post(f"{API}/submissions", headers=ins, json=body).status_code == 403
    assert client.post(f"{API}/submissions/run", headers=ins, json=body).status_code == 403
    assert enroll(client, course['id'], ins).status_code == 403


def test_register_always_creates_a_student(client):
    response = client.post(
        f"{API}/auth/register",
        json={"email": "Reg-Test@test.local", "password": "long-enough-pw", "role": "admin"},
    )
    assert response.status_code == 201
    assert response.json()["role"] == "student"
    again = client.post(
        f"{API}/auth/register", json={"email": "reg-test@test.local", "password": "long-enough-pw"}
    )
    assert again.status_code == 409


@pytest.fixture(scope="module", autouse=True)
def remove_registered_user(owner):
    delete = text("DELETE FROM users WHERE email = 'reg-test@test.local'")
    with owner.begin() as conn:
        conn.execute(delete)
    yield
    with owner.begin() as conn:
        conn.execute(delete)


def test_login(client):
    ok = client.post(
        f"{API}/auth/login", json={"email": "reg-test@test.local", "password": "long-enough-pw"}
    )
    assert ok.status_code == 200 and ok.json()["token_type"] == "bearer"
    bad = client.post(
        f"{API}/auth/login", json={"email": "reg-test@test.local", "password": "wrong-password"}
    )
    assert bad.status_code == 401


def test_password_is_stored_as_a_bcrypt_hash(owner):
    with owner.connect() as conn:
        stored = conn.execute(
            text("SELECT password_hash FROM users WHERE email = 'reg-test@test.local'")
        ).scalar_one()
    assert stored.startswith("$2") and "long-enough-pw" not in stored


def test_expired_and_forged_tokens_are_rejected(client, students):
    secret = get_settings().jwt_secret
    expired = jwt.encode({"sub": "1", "role": "admin", "exp": int(time.time()) - 5}, secret, "HS256")
    forged = jwt.encode({"sub": "1", "role": "admin", "exp": int(time.time()) + 600}, "wrong", "HS256")
    for token in (expired, forged):
        response = client.get(f"{API}/courses", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401


def test_enrolment_gates_problem_access(client, students, course):
    enrolled, outsider = students
    pid, cid = course["problem_id"], course["id"]
    assert client.get(f"{API}/problems?course_id={cid}", headers=enrolled).status_code == 200
    assert client.get(f"{API}/problems/{pid}", headers=enrolled).status_code == 200
    assert client.get(f"{API}/problems?course_id={cid}", headers=outsider).status_code == 403
    assert client.get(f"{API}/problems/{pid}", headers=outsider).status_code == 404
    body = {"problem_id": pid, "code": CODE}
    assert client.post(f"{API}/submissions", headers=outsider, json=body).status_code == 404
    assert enroll(client, cid, outsider).status_code == 200
    assert client.post(f"{API}/submissions/run", headers=outsider, json=body).status_code == 200


def test_students_cannot_read_each_others_submissions(client, students, course, make_user):
    enrolled, outsider = students
    submitted = client.post(
        f"{API}/submissions", headers=enrolled, json={"problem_id": course["problem_id"], "code": CODE}
    )
    sid = submitted.json()["submission_id"]
    assert client.get(f"{API}/submissions/{sid}", headers=enrolled).status_code == 200
    assert client.get(f"{API}/submissions/{sid}", headers=outsider).status_code == 404
    assert client.get(f"{API}/submissions/{sid}", headers=course["instructor"]).status_code == 200
    _, other_instructor = make_user("instructor")
    assert client.get(f"{API}/submissions/{sid}", headers=other_instructor).status_code == 404
    _, admin = make_user("admin")
    assert client.get(f"{API}/submissions/{sid}", headers=admin).status_code == 200


def test_instructor_cannot_add_problems_to_someone_elses_course(client, course, make_user):
    _, other = make_user("instructor")
    response = client.post(
        f"{API}/problems",
        headers=other,
        json={
            "course_id": course["id"], "title": "x", "statement": "x", "difficulty_b": 0,
            "discrimination_a": 1, "concepts": [], "reference_solution": "", "test_cases": [],
        },
    )
    assert response.status_code == 403
