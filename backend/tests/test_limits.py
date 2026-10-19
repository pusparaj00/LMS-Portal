"""TR-S-04: rate limits and request size limits. Each was missing before; the sweep showed 40 wrong-password logins
and a 3 MB body both being processed."""
import pytest
import redis
from sqlalchemy import text

from app import ratelimit
from app.bodylimit import MAX_BODY_BYTES
from app.ratelimit import Rule

API = "/api/v1"


def wrong_login(client, email="nobody@limits.test", **kw):
    return client.post(f"{API}/auth/login", json={"email": email, "password": "wrong-password"}, **kw)


def test_repeated_wrong_passwords_for_one_account_are_stopped(client, monkeypatch, clock):
    monkeypatch.setitem(ratelimit.RULES, "login_email", Rule(3, 60))
    assert [wrong_login(client).status_code for _ in range(3)] == [401, 401, 401]
    blocked = wrong_login(client)
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1
    error = blocked.json()["error"]
    assert error["code"] == "http_error" and "Try again in" in error["message"]
    assert error["request_id"] == blocked.headers["X-Request-ID"]
    assert wrong_login(client, "someone.else@limits.test").status_code == 401  # other accounts are unaffected


def test_the_limit_is_per_address_too_and_the_window_resets(client, monkeypatch, clock):
    monkeypatch.setitem(ratelimit.RULES, "login_ip", Rule(2, 60))
    first = {"headers": {"X-Forwarded-For": "10.1.1.1"}}
    assert [wrong_login(client, f"a{n}@limits.test", **first).status_code for n in range(2)] == [401, 401]
    assert wrong_login(client, "a9@limits.test", **first).status_code == 429
    assert wrong_login(client, "b@limits.test", headers={"X-Forwarded-For": "10.2.2.2"}).status_code == 401
    clock["now"] += 61
    assert wrong_login(client, "c@limits.test", **first).status_code == 401


def test_registration_is_limited_per_address(client, monkeypatch):
    monkeypatch.setitem(ratelimit.RULES, "register_ip", Rule(1, 3600))
    headers = {"X-Forwarded-For": "10.3.3.3"}
    body = {"email": "not-an-email", "password": "long-enough-1"}
    assert client.post(f"{API}/auth/register", json=body, headers=headers).status_code == 422  # validation first
    assert client.post(f"{API}/auth/register", json=body, headers=headers).status_code == 422
    ok = {"email": "limit-test@limits.test", "password": "long-enough-1"}
    first = client.post(f"{API}/auth/register", json=ok, headers=headers)
    assert first.status_code == 201
    assert client.post(f"{API}/auth/register", json={**ok, "email": "second@limits.test"}, headers=headers
                       ).status_code == 429


@pytest.fixture(scope="module", autouse=True)
def remove_limit_test_users(owner):
    yield
    with owner.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE email LIKE '%@limits.test'"))


def test_submissions_and_runs_are_limited_per_student_before_any_work_is_done(
    client, make_user, course, owner, monkeypatch, clock
):
    monkeypatch.setitem(ratelimit.RULES, "submit", Rule(2, 60))
    monkeypatch.setitem(ratelimit.RULES, "run", Rule(2, 60))
    user_id, headers = make_user("student")
    client.post(f"{API}/courses/{course['id']}/enroll", headers=headers)
    body = {"problem_id": course["problem_id"], "code": "print(int(input()) + 1)\n"}
    assert [client.post(f"{API}/submissions", headers=headers, json=body).status_code for _ in range(2)] == [200, 200]
    assert client.post(f"{API}/submissions", headers=headers, json=body).status_code == 429
    with owner.connect() as conn:
        stored = conn.execute(text("SELECT count(*) FROM submissions WHERE user_id = :u"), {"u": user_id}).scalar_one()
    assert stored == 2  # the refused submission was neither run nor stored
    assert [client.post(f"{API}/submissions/run", headers=headers, json=body).status_code for _ in range(2)] == [200, 200]
    assert client.post(f"{API}/submissions/run", headers=headers, json=body).status_code == 429
    _, other = make_user("student")
    client.post(f"{API}/courses/{course['id']}/enroll", headers=other)
    assert client.post(f"{API}/submissions/run", headers=other, json=body).status_code == 200


def test_chat_is_limited_per_student(client, make_user, monkeypatch):
    monkeypatch.setitem(ratelimit.RULES, "chat", Rule(2, 60))
    _, headers = make_user("student")
    sent = [client.post(f"{API}/chat", headers=headers, json={"message": "how am i doing"}).status_code for _ in range(3)]
    assert sent == [200, 200, 429]


def test_normal_use_is_not_blocked_by_the_default_limits(client, make_user, course):
    _, headers = make_user("student")
    client.post(f"{API}/courses/{course['id']}/enroll", headers=headers)
    body = {"problem_id": course["problem_id"], "code": "print(int(input()) + 1)\n"}
    codes = [client.post(f"{API}/submissions/run", headers=headers, json=body).status_code for _ in range(20)]
    assert codes == [200] * 20


def test_if_the_limiter_is_down_requests_are_still_served(client, monkeypatch):
    def broken():
        raise redis.RedisError("down")

    monkeypatch.setattr(ratelimit, "get_redis", broken)
    assert wrong_login(client).status_code == 401


def test_an_oversized_body_is_refused_with_413_and_the_usual_error_shape(client):
    response = client.post(f"{API}/auth/login", json={"email": "a@b.co", "password": "x" * (MAX_BODY_BYTES + 1)})
    assert response.status_code == 413 and response.json()["error"]["code"] == "payload_too_large"


def test_a_body_without_a_content_length_is_stopped_too(client):
    def chunks():
        for _ in range(8):
            yield b"x" * 100_000

    response = client.post(f"{API}/auth/login", content=chunks(), headers={"Content-Type": "application/json"})
    assert response.status_code == 413


def test_a_body_just_under_the_limit_is_still_handled(client):
    response = client.post(f"{API}/auth/login", json={"email": "a@b.co", "password": "x" * 500_000})
    assert response.status_code == 401
