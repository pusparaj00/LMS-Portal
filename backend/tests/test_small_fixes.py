"""G-14: a coding problem needs a hidden test. G-15: a due date that has passed needs the teacher's confirmation."""
from datetime import UTC, datetime, timedelta

import pytest

from app.services.validation import validate_code_problem
from tests.conftest import SUM_REFERENCE, SUM_TESTS

API = "/api/v1"
VISIBLE_ONLY = [{**t, "hidden": False} for t in SUM_TESTS]


def iso(moment: datetime) -> str:
    return moment.isoformat()


def new_assignment(client, course, due, **extra):
    return client.post(
        f"{API}/courses/{course['id']}/assignments", headers=course["instructor"],
        json={"title": "Week", "due_at": iso(due), "problems": [{"problem_id": course["problem_id"], "points": 1}], **extra},
    )


def test_a_problem_with_no_hidden_test_is_refused_with_the_reason():
    errors = validate_code_problem(
        concept_names=["loops"], known_concepts={"loops"}, reference_solution=SUM_REFERENCE, tests=VISIBLE_ONLY
    )
    assert any("no hidden test" in e for e in errors)


def test_a_problem_with_one_hidden_test_is_accepted():
    errors = validate_code_problem(
        concept_names=["loops"], known_concepts={"loops"}, reference_solution=SUM_REFERENCE, tests=SUM_TESTS
    )
    assert errors == []


def test_the_problem_form_refuses_a_problem_with_no_hidden_test(client, course):
    body = {
        "course_id": course["id"], "title": "Visible only", "statement": "Read n, print n + 1.", "difficulty_b": 0.0,
        "discrimination_a": 1.0, "concepts": [{"concept_id": _concept(client, course), "name": "loops", "weight": 1.0}],
        "reference_solution": SUM_REFERENCE, "test_cases": VISIBLE_ONLY,
    }
    response = client.post(f"{API}/problems", headers=course["instructor"], json=body)
    assert response.status_code == 422 and "no hidden test" in response.text


def _concept(client, course) -> int:
    problem = client.get(f"{API}/problems/{course['problem_id']}", headers=course["instructor"]).json()
    return problem["concepts"][0]["concept_id"]


def test_a_past_due_date_is_refused_until_the_teacher_confirms_it(client, course):
    past = datetime.now(UTC).replace(microsecond=0) - timedelta(days=3)
    refused = new_assignment(client, course, past)
    assert refused.status_code == 422 and "confirm_past_due" in refused.text
    kept = new_assignment(client, course, past, confirm_past_due=True)
    assert kept.status_code == 201


def test_a_future_due_date_needs_no_confirmation(client, course):
    assert new_assignment(client, course, datetime.now(UTC) + timedelta(days=2)).status_code == 201


@pytest.mark.parametrize("move_to", ["same", "other_past"])
def test_editing_an_assignment_only_asks_again_when_the_past_date_changes(client, course, move_to):
    past = datetime.now(UTC).replace(microsecond=0) - timedelta(days=4)
    made = new_assignment(client, course, past, confirm_past_due=True).json()
    path = f"{API}/courses/{course['id']}/assignments/{made['id']}"
    due = past if move_to == "same" else past - timedelta(days=1)
    body = {"title": "Renamed", "due_at": iso(due), "problems": [{"problem_id": course["problem_id"], "points": 1}]}
    response = client.put(path, headers=course["instructor"], json=body)
    assert (response.status_code == 200) if move_to == "same" else (response.status_code == 422)
