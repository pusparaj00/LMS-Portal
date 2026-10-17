"""TR-L-10: a model-drafted problem is offered only after its reference passes and a wrong solution fails as named."""
import json

import pytest
from sqlalchemy import text

from app.llm.adapter import LLMError
from tests.test_feedback_api import FakeLLM, llm  # noqa: F401

API = "/api/v1"

REFERENCE = "n = int(input())\nprint(sum(range(1, n + 1)))\n"
OFF_BY_ONE = "n = int(input())\nprint(sum(range(1, n)))\n"


def reply(**changes) -> str:
    draft = {
        "title": "Total up to n",
        "statement": "Read n and print 1 + 2 + ... + n.",
        "reference_solution": REFERENCE,
        "wrong_solution": OFF_BY_ONE,
        "wrong_category": "basic",
        "tests": [
            {"input": "3\n", "expected": "6\n", "hidden": False, "category": "basic"},
            {"input": "1\n", "expected": "1\n", "hidden": False, "category": "basic"},
            {"input": "0\n", "expected": "0\n", "hidden": True, "category": "zero"},
            {"input": "100\n", "expected": "5050\n", "hidden": True, "category": "large_input"},
        ],
    }
    return json.dumps({**draft, **changes})


@pytest.fixture
def concept(course, owner):
    with owner.connect() as conn:
        return conn.execute(text("SELECT id FROM concepts WHERE course_id = :c"), {"c": course["id"]}).scalar_one()


def ask(client, course, concept, headers=None):
    return client.post(
        f"{API}/problems/draft", headers=headers or course["instructor"],
        json={"course_id": course["id"], "concept_id": concept},
    )


def test_a_checked_draft_is_offered_and_nothing_is_saved_until_the_instructor_saves_it(
    client, course, concept, owner, llm
):
    fake = llm(FakeLLM(reply()))
    with owner.connect() as conn:
        before = conn.execute(text("SELECT count(*) FROM problems WHERE course_id = :c"), {"c": course["id"]}).scalar()
    response = ask(client, course, concept)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Total up to n" and body["attempts"] == 1 and len(body["test_cases"]) == 4
    assert "4 of 4" in body["checks"][0] and "'basic'" in body["checks"][1]
    assert "wrong_solution" not in body  # the planted mistake is not handed out
    system, user = fake.calls[0]
    assert "<concept>loops</concept>" in user and "add one" in user  # the course's existing title, to avoid repeats
    with owner.connect() as conn:
        after = conn.execute(text("SELECT count(*) FROM problems WHERE course_id = :c"), {"c": course["id"]}).scalar()
    assert after == before
    saved = client.post(
        f"{API}/problems", headers=course["instructor"],
        json={
            # a new title: the course fixture is shared, and later tests draft "Total up to n" again
            "course_id": course["id"], "title": body["title"] + " (reviewed)", "statement": body["statement"],
            "difficulty_b": 0.0,
            "discrimination_a": 1.0, "concepts": [{"concept_id": concept, "name": "loops", "weight": 1.0}],
            "reference_solution": body["reference_solution"], "test_cases": body["test_cases"],
        },
    )
    assert saved.status_code == 201, saved.text


def test_a_draft_whose_wrong_solution_is_not_caught_is_retried_once_then_refused(client, course, concept, llm):
    uncaught = reply(wrong_solution=REFERENCE)
    fake = llm(FakeLLM(uncaught, uncaught))
    response = ask(client, course, concept)
    assert response.status_code == 422
    assert "wrong solution passes every test" in response.json()["error"]["message"]
    assert len(fake.calls) == 2 and "previous_attempt_rejected" in fake.calls[1][1]


def test_a_draft_whose_reference_fails_its_own_tests_is_refused_with_the_reason(client, course, concept, llm):
    llm(FakeLLM(reply(reference_solution=OFF_BY_ONE), "not json"))
    response = ask(client, course, concept)
    assert response.status_code == 422
    assert "could not be read" in response.json()["error"]["message"]  # the last attempt's reasons are reported


def test_the_second_attempt_can_succeed_after_the_reasons_are_given(client, course, concept, llm):
    fake = llm(FakeLLM(reply(wrong_category="zero"), reply()))
    response = ask(client, course, concept)
    assert response.status_code == 200 and response.json()["attempts"] == 2
    assert "not in 'zero'" in fake.calls[1][1]


def test_drafts_are_for_the_course_instructor_and_a_model_failure_is_a_503(client, course, concept, make_user, llm):
    _, other_instructor = make_user("instructor")
    _, student = make_user("student")
    llm(FakeLLM(LLMError("down")))
    assert ask(client, course, concept, other_instructor).status_code == 403
    assert ask(client, course, concept, student).status_code == 403
    assert ask(client, course, 0).status_code == 404
    assert ask(client, course, concept).status_code == 503
