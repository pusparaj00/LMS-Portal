"""F-14: run code on the caller's own input. Nothing is stored or graded; access follows the problem's course."""
import pytest
from sqlalchemy import text

from app import ratelimit
from app.ratelimit import Rule

API = "/api/v1"
DOUBLE = "print(int(input()) * 2)\n"


@pytest.fixture(scope="module")
def student(client, make_user, course):
    user_id, headers = make_user("student")
    assert client.post(f"{API}/courses/{course['id']}/enroll", headers=headers).status_code == 204
    return user_id, headers


def run(client, course, headers, code=DOUBLE, stdin="21\n", **extra):
    return client.post(
        f"{API}/submissions/run-custom", headers=headers,
        json={"problem_id": course["problem_id"], "code": code, "stdin": stdin, **extra},
    )


def test_the_code_runs_on_the_given_input_and_nothing_is_stored(client, course, student, owner):
    user_id, headers = student
    with owner.connect() as conn:
        before = conn.execute(text("SELECT count(*) FROM submissions WHERE user_id = :u"), {"u": user_id}).scalar_one()
    response = run(client, course, headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"status", "stdout", "stderr", "runtime_ms"}  # no test, no hidden data
    assert (body["status"], body["stdout"], body["stderr"]) == ("ok", "42\n", "")
    with owner.connect() as conn:
        after = conn.execute(text("SELECT count(*) FROM submissions WHERE user_id = :u"), {"u": user_id}).scalar_one()
    assert after == before


def test_errors_come_back_as_structured_results(client, course, student):
    _, headers = student
    syntax = run(client, course, headers, code="print(\n").json()
    assert syntax["status"] == "syntax_error" and "SyntaxError" in syntax["stderr"]
    runtime = run(client, course, headers, code="print(1 / 0)\n").json()
    assert runtime["status"] == "runtime_error" and "ZeroDivisionError" in runtime["stderr"]
    assert "/work/" not in runtime["stderr"] and 'File "main.py"' in runtime["stderr"]  # no runner path
    empty = run(client, course, headers, stdin="").json()  # input() on an empty stdin
    assert empty["status"] == "runtime_error" and "EOFError" in empty["stderr"]


def test_the_input_is_optional(client, course, student):
    _, headers = student
    response = client.post(f"{API}/submissions/run-custom", headers=headers,
                           json={"problem_id": course["problem_id"], "code": "print('hi')\n"})
    assert response.status_code == 200 and response.json()["stdout"] == "hi\n"


def test_the_teacher_of_the_course_can_try_the_problem_too(client, course):
    response = run(client, course, course["instructor"])
    assert response.status_code == 200 and response.json()["stdout"] == "42\n"


def test_only_people_with_access_to_the_problem_can_run_on_it(client, make_user, course):
    _, outsider = make_user("student")
    _, other_teacher = make_user("instructor")
    assert run(client, course, outsider).status_code == 404
    assert run(client, course, other_teacher).status_code == 404
    assert client.post(f"{API}/submissions/run-custom", json={"problem_id": 1, "code": "x", "stdin": ""}).status_code == 401


def test_a_student_who_has_not_agreed_to_the_notice_cannot_run(client, make_user, course):
    _, headers = make_user("student", consented=False)
    client.post(f"{API}/courses/{course['id']}/enroll", headers=headers)
    assert run(client, course, headers).status_code == 403


@pytest.mark.parametrize("change", [{"stdin": "x" * 10_001}, {"stdin": "a\x00b"}, {"code": "x" * 50_001}])
def test_oversized_or_unsafe_input_is_refused(client, course, student, change):
    _, headers = student
    assert run(client, course, headers, **change).status_code == 422


def test_runs_are_rate_limited_per_user_and_apart_from_example_runs(client, course, student, monkeypatch):
    _, headers = student
    monkeypatch.setitem(ratelimit.RULES, "run_custom", Rule(2, 60))
    assert [run(client, course, headers).status_code for _ in range(2)] == [200, 200]
    assert run(client, course, headers).status_code == 429
    examples = client.post(f"{API}/submissions/run", headers=headers,
                           json={"problem_id": course["problem_id"], "code": DOUBLE})
    assert examples.status_code == 200
