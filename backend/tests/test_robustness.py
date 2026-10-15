"""Bugs found by probing the API with hostile or awkward input. Each failed before it was fixed."""
import threading

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.test_diagnostic import PLACEMENT_RIGHT, enrolled_student, option

API = "/api/v1"
NUL = chr(0)


def test_passwords_longer_than_bcrypt_can_hash_are_refused_not_crashed(client):
    for password in ("a" * 73, "é" * 40):  # 73 bytes, and 80 bytes in 40 characters
        response = client.post(f"{API}/auth/register", json={"email": "long@test.local", "password": password})
        assert response.status_code == 422, password
        assert "72 bytes" in response.text
    login = client.post(f"{API}/auth/login", json={"email": "long@test.local", "password": "b" * 200})
    assert login.status_code == 401


@pytest.mark.parametrize("email", ["nope", "a@b", "a b@c.d", "@c.d", "a" * 250 + "@t.local"])
def test_registration_needs_a_real_looking_email(client, email):
    response = client.post(f"{API}/auth/register", json={"email": email, "password": "long-enough-1"})
    assert response.status_code == 422


def test_nul_characters_are_refused_everywhere_postgres_would_reject_them(client, course, make_user):
    assert client.post(
        f"{API}/auth/register", json={"email": f"a{NUL}b@test.local", "password": "long-enough-1"}
    ).status_code == 422
    assert client.post(
        f"{API}/auth/login", json={"email": f"a{NUL}b@test.local", "password": "long-enough-1"}
    ).status_code == 422
    user_id, headers = make_user("student")
    client.post(f"{API}/courses/{course['id']}/enroll", headers=headers)
    body = {"problem_id": course["problem_id"], "code": f"print(1){NUL}"}
    assert client.post(f"{API}/submissions", headers=headers, json=body).status_code == 422
    assert client.post(f"{API}/submissions/run", headers=headers, json=body).status_code == 422
    assert client.post(f"{API}/chat", headers=headers, json={"message": f"hi{NUL}"}).status_code == 422
    title = {"title": f"course{NUL}"}
    assert client.post(f"{API}/courses", headers=course["instructor"], json=title).status_code == 422


def test_unexpected_failures_use_the_single_json_error_shape(monkeypatch):
    def explode(_password):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.routers.accounts.hash_password", explode)
    quiet = TestClient(app, raise_server_exceptions=False)
    response = quiet.post(f"{API}/auth/register", json={"email": "boom@test.local", "password": "long-enough-1"})
    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "internal_error" and error["request_id"] == response.headers["X-Request-ID"]
    assert "boom" not in response.text  # internals are not leaked


def test_two_simultaneous_answers_to_one_placement_item_count_once(client, make_user, placement_course, owner):
    course_id = placement_course["course_id"]
    _, headers = enrolled_student(client, make_user, course_id)
    started = client.post(f"{API}/diagnostic/start", headers=headers, json={"course_id": course_id}).json()
    item = started["item"]
    body = {
        "session_id": started["session_id"],
        "problem_id": item["problem_id"],
        "option_id": option(item, "right")["id"],
    }
    codes, gate = [], threading.Barrier(2)

    def send():
        gate.wait()
        codes.append(client.post(f"{API}/diagnostic/answer", headers=headers, json=body).status_code)

    threads = [threading.Thread(target=send) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(codes) == [200, 409]

    import json

    from app.db import get_redis

    state = json.loads(get_redis().get(f"diagnostic:{started['session_id']}"))
    assert state["asked"] == [item["problem_id"]] and len(state["responses"]) == 1
    assert PLACEMENT_RIGHT  # the coding tasks are not reached in this test
