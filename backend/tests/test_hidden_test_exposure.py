"""TR-S-12: hidden test inputs and expected outputs never leave the server for a student, on any route a student can reach."""
import pytest

from app.llm.adapter import LLMError
from tests.conftest import HIDDEN_INPUT
from tests.helpers import enroll
from tests.test_feedback_api import FakeLLM, llm  # noqa: F401  (fixtures)

API = "/api/v1"
HIDDEN_VALUES = ("987654", "987655")
WRONG = "print('wrong')\n"


@pytest.fixture(scope="module")
def student(client, make_user, course):
    user_id, headers = make_user("student")
    assert enroll(client, course["id"], headers).status_code == 200
    return user_id, headers


def assert_clean(response):
    assert response.status_code < 500, response.text
    for value in HIDDEN_VALUES:
        assert value not in response.text, f"{response.request.method} {response.request.url.path} returned {value}"


def test_no_student_route_returns_a_hidden_test(client, course, student, llm):
    _, headers = student
    problem = course["problem_id"]
    seen = []

    def check(response):
        assert_clean(response)
        seen.append(f"{response.request.method} {response.request.url.path}")
        return response

    check(client.get(f"{API}/problems", headers=headers, params={"course_id": course["id"]}))
    check(client.get(f"{API}/problems/{problem}", headers=headers))
    ran = check(client.post(f"{API}/submissions/run", headers=headers, json={"problem_id": problem, "code": WRONG}))
    assert ran.status_code == 200
    sub = check(client.post(f"{API}/submissions", headers=headers, json={"problem_id": problem, "code": WRONG}))
    assert sub.json()["status"] == "failed"
    sid = sub.json()["submission_id"]
    check(client.get(f"{API}/submissions/{sid}", headers=headers))
    check(client.post(
        f"{API}/submissions/run-custom", headers=headers, json={"problem_id": problem, "code": WRONG, "stdin": "1\n"}
    ))
    llm(FakeLLM(LLMError("every provider failed"), LLMError("every provider failed")))
    check(client.post(f"{API}/submissions/{sid}/explain", headers=headers))
    for _ in range(3):
        check(client.post(f"{API}/submissions/{sid}/hint", headers=headers))
    check(client.get(f"{API}/students/me/mastery", headers=headers, params={"course_id": course["id"]}))
    check(client.post(f"{API}/chat", headers=headers, json={"message": "why did my submission fail", "problem_id": problem}))
    assert HIDDEN_INPUT.strip() in HIDDEN_VALUES
    assert len(seen) >= 10
