"""F-11, F-12, TR-X-07: structured results, hidden tests never returned."""
import json

import pytest
from sqlalchemy import text

from tests.conftest import HIDDEN_INPUT
from tests.helpers import enroll

API = "/api/v1"


@pytest.fixture(scope="module")
def student(client, make_user, course):
    user_id, headers = make_user("student")
    assert enroll(client, course['id'], headers).status_code == 200
    return user_id, headers


def submit(client, course, headers, code, path="/submissions"):
    return client.post(
        API + path, headers=headers, json={"problem_id": course["problem_id"], "code": code}
    )


def test_correct_submission_is_accepted_and_stored(client, course, student, owner):
    _, headers = student
    response = submit(client, course, headers, "print(int(input()) + 1)\n")
    body = response.json()
    assert response.status_code == 200
    assert (body["status"], body["passed"], body["failed"]) == ("passed", 4, 0)
    assert body["error_type"] is None and body["failed_categories"] == []
    with owner.connect() as conn:
        row = conn.execute(
            text("SELECT status, passed, failed FROM run_results WHERE submission_id = :s"),
            {"s": body["submission_id"]},
        ).one()
    assert tuple(row) == ("passed", 4, 0)


def test_wrong_submission_fails_in_the_right_categories(client, course, student):
    _, headers = student
    # Correct for positive numbers, wrong for the negative hidden test only.
    code = "n = int(input())\nprint(abs(n) + 1 if n > 0 else n)\n"
    body = submit(client, course, headers, code).json()
    assert body["status"] == "failed"
    assert body["failed_categories"] == ["negative_numbers"]
    assert (body["passed"], body["failed"]) == (3, 1)


def test_hidden_tests_are_never_returned(client, course, student):
    _, headers = student
    response = submit(client, course, headers, "print('wrong')\n")
    assert HIDDEN_INPUT.strip() not in response.text
    assert "987655" not in response.text
    visible = response.json()["visible_tests"]
    assert [t["input"] for t in visible] == ["1\n", "41\n"]
    detail = client.get(f"{API}/problems/{course['problem_id']}", headers=headers)
    assert "987654" not in detail.text and "reference" not in detail.text
    assert len(detail.json()["examples"]) == 2


def test_syntax_error_is_reported_as_error(client, course, student):
    _, headers = student
    body = submit(client, course, headers, "print(\n").json()
    assert (body["status"], body["error_type"]) == ("error", "syntax_error")


def test_runtime_error_and_timeout_are_structured(client, course, student):
    _, headers = student
    body = submit(client, course, headers, "raise ValueError('boom')\n").json()
    assert (body["status"], body["error_type"]) == ("failed", "runtime_error")
    body = submit(client, course, headers, "while True:\n    pass\n").json()
    assert (body["status"], body["error_type"]) == ("failed", "time_limit")


def test_run_executes_visible_tests_only_and_stores_nothing(client, course, student, owner):
    user_id, headers = student
    with owner.connect() as conn:
        before = conn.execute(
            text("SELECT count(*) FROM submissions WHERE user_id = :u"), {"u": user_id}
        ).scalar_one()
    body = submit(client, course, headers, "print(int(input()) + 1)\n", "/submissions/run").json()
    assert body["submission_id"] is None
    assert body["passed"] == 2 and len(body["visible_tests"]) == 2
    with owner.connect() as conn:
        after = conn.execute(
            text("SELECT count(*) FROM submissions WHERE user_id = :u"), {"u": user_id}
        ).scalar_one()
    assert before == after


def test_oversized_code_is_rejected(client, course, student):
    _, headers = student
    assert submit(client, course, headers, "x" * 60_000).status_code == 422


def test_create_problem_rejects_a_bad_reference_solution(client, course):
    ok = {"concept_id": 0, "name": "loops", "weight": 1.0}
    with_concept = client.get(
        f"{API}/problems?course_id={course['id']}", headers=course["instructor"]
    ).json()["problems"][0]["concepts"][0]
    body = {
        "course_id": course["id"], "title": "Bad", "statement": "s", "difficulty_b": 0,
        "discrimination_a": 1, "concepts": [{**ok, "concept_id": with_concept["concept_id"]}],
        "reference_solution": "print('nope')\n",
        "test_cases": [{"input": "1\n", "expected": "2\n", "hidden": True, "category": "basic"}],
    }
    response = client.post(f"{API}/problems", headers=course["instructor"], json=body)
    assert response.status_code == 422
    message = response.json()["error"]["message"]
    assert "reference solution fails test 1 (basic): it printed 'nope' but the test expects '2'" in message
    body["test_cases"][0]["category"] = ""
    body["concepts"] = []
    message = client.post(f"{API}/problems", headers=course["instructor"], json=body).json()
    assert "has no concept" in json.dumps(message) and "has no category" in json.dumps(message)


def test_a_graded_submission_moves_mastery_and_writes_the_ledger(client, course, student, owner):
    user_id, headers = student
    passed = submit(client, course, headers, "print(int(input()) + 1)\n").json()
    assert [c["concept"] for c in passed["mastery_changes"]] == ["loops"]
    assert passed["mastery_changes"][0]["after"] > passed["mastery_changes"][0]["before"]
    failed = submit(client, course, headers, "print('wrong')\n").json()
    assert failed["mastery_changes"][0]["after"] < failed["mastery_changes"][0]["before"]
    with owner.connect() as conn:
        refs = conn.execute(
            text("SELECT evidence_ref, rule_id FROM mastery_events WHERE user_id = :u ORDER BY id"),
            {"u": user_id},
        ).all()
    expected = (f"submission:{passed['submission_id']}", "bayes_update")
    assert [tuple(r) for r in refs].count(expected) == 1
    assert len(refs) >= 2


def test_the_problem_list_shows_each_student_only_their_own_progress(client, course, make_user):
    """F-60: new until the first submission, tried after a failure, solved once any submission passes."""
    def status(headers):
        problems = client.get(f"{API}/problems?course_id={course['id']}", headers=headers).json()["problems"]
        return next(p["my_status"] for p in problems if p["id"] == course["problem_id"])

    _, mine = make_user("student")
    _, other = make_user("student")
    for headers in (mine, other):
        assert enroll(client, course['id'], headers).status_code == 200
    assert status(mine) == "new"
    submit(client, course, mine, "print('wrong')\n")
    assert status(mine) == "tried"
    submit(client, course, mine, "print(int(input()) + 1)\n")
    submit(client, course, mine, "print('wrong again')\n")
    assert status(mine) == "solved"
    assert status(other) == "new"
    assert status(course["instructor"]) is None
