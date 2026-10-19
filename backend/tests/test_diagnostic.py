"""F-20, F-24, F-34, F-60, TR-A-05: the placement test through the API, against the real services."""
import pytest
from sqlalchemy import text

from app.db import get_redis
from app.diagnostic import selection
from tests.conftest import PLACEMENT_RIGHT
from tests.helpers import enroll

API = "/api/v1"


def enrolled_student(client, make_user, course_id):
    user_id, headers = make_user("student")
    assert enroll(client, course_id, headers).status_code == 200
    return user_id, headers


def option(item, option_text):
    return next(o for o in item["options"] if o["text"] == option_text)


def answer(client, headers, session_id, item, *, wrong_for=None):
    """Answer a tracing item with the wrong option tagged `wrong_for` (misconception id), or code correctly."""
    if item["kind"] == "mcq":
        body = {"option_id": option(item, f"wrong {wrong_for}")["id"]}
    else:
        body = {"code": PLACEMENT_RIGHT}
    return client.post(
        f"{API}/diagnostic/answer",
        headers=headers,
        json={"session_id": session_id, "problem_id": item["problem_id"], **body},
    )


def run_whole_test(client, headers, course_id, wrong_for):
    started = client.post(f"{API}/diagnostic/start", headers=headers, json={"course_id": course_id}).json()
    session_id, item, kinds = started["session_id"], started["item"], []
    while True:
        kinds.append(item["kind"])
        data = answer(client, headers, session_id, item, wrong_for=wrong_for).json()
        if data["done"]:
            return session_id, kinds, data["result"]
        item = data["next_item"]


@pytest.fixture
def never_stop_early(monkeypatch):
    monkeypatch.setattr(selection, "UNCERTAINTY_STOP_BITS", 0.0)


def test_a_new_student_completes_ten_items_and_sees_a_vector_and_misconceptions(
    client, make_user, placement_course, owner, never_stop_early
):
    course_id, wrong_for = placement_course["course_id"], placement_course["misconceptions"][0]
    user_id, headers = enrolled_student(client, make_user, course_id)

    started = client.post(f"{API}/diagnostic/start", headers=headers, json={"course_id": course_id}).json()
    assert (started["item_number"], started["max_items"]) == (1, 10)
    assert get_redis().exists(f"diagnostic:{started['session_id']}")  # the session is in Redis, not process memory
    assert {o["text"] for o in started["item"]["options"]} >= {"right"}
    client.post(f"{API}/diagnostic/answer", headers=headers, json={
        "session_id": started["session_id"], "problem_id": started["item"]["problem_id"],
        "option_id": option(started["item"], f"wrong {wrong_for}")["id"],
    })

    # a second student runs the whole test
    other_id, other = enrolled_student(client, make_user, course_id)
    session_id, kinds, result = run_whole_test(client, other, course_id, wrong_for)

    assert kinds == ["mcq"] * 8 + ["code"] * 2
    assert len(result["mastery"]) == 3
    assert all(c["p_known"] < 0.5 for c in result["mastery"])  # eight wrong answers lower every concept
    names = {m["name"] for m in result["misconceptions"]}
    with owner.connect() as conn:
        tagged = conn.execute(text("SELECT name FROM misconceptions WHERE id = :m"), {"m": wrong_for}).scalar_one()
        status = conn.execute(
            text("SELECT status FROM diagnostic_sessions WHERE id = :i"), {"i": int(session_id)}
        ).scalar_one()
        ledger = conn.execute(text("SELECT count(*) FROM mastery_events WHERE user_id = :u"), {"u": other_id}).scalar_one()
    assert tagged in names and result["misconceptions"][0]["probability"] > 0.5
    assert status == "completed" and ledger >= 10
    assert not get_redis().exists(f"diagnostic:{session_id}")


def test_the_test_stops_early_when_the_concepts_are_settled(client, make_user, placement_course):
    course_id, wrong_for = placement_course["course_id"], placement_course["misconceptions"][0]
    _, headers = enrolled_student(client, make_user, course_id)
    _, kinds, result = run_whole_test(client, headers, course_id, wrong_for)
    # three concepts are well determined after six wrong answers, so the test ends before the coding tasks
    assert selection.MIN_ITEMS_BEFORE_STOP <= len(kinds) < selection.MAX_ITEMS
    assert kinds == ["mcq"] * len(kinds) and len(result["mastery"]) == 3


def test_dashboard_and_the_why_view_read_from_the_ledger(client, make_user, placement_course):
    course_id, wrong_for = placement_course["course_id"], placement_course["misconceptions"][1]
    user_id, headers = enrolled_student(client, make_user, course_id)
    run_whole_test(client, headers, course_id, wrong_for)

    dashboard = client.get(f"{API}/students/me/mastery", headers=headers, params={"course_id": course_id}).json()
    assert dashboard["placement_completed"] is True
    assert len(dashboard["concepts"]) == 3 and dashboard["misconceptions"]
    assert dashboard["recommended"] is None or dashboard["recommended"]["problem_id"]

    rules = set()
    for concept in dashboard["concepts"]:
        response = client.get(f"{API}/students/me/mastery/{concept['concept_id']}/history", headers=headers)
        assert response.status_code == 200, response.text
        history = response.json()
        assert history and history[0]["p_after"] == pytest.approx(concept["p_known"], abs=1e-9)
        assert all(h["rule_id"] and h["evidence_type"] and h["explanation"] for h in history)
        rules |= {h["rule_id"] for h in history}
        if any(h["rule_id"] == "bayes_update" for h in history):
            assert any(h["explanation"].startswith("Placement answer to") for h in history)
    # eight wrong answers on chained concepts pass part of the drop to the prerequisites
    assert rules == {"bayes_update", "prerequisite_propagation"}


def test_session_checks(client, make_user, placement_course):
    course_id = placement_course["course_id"]
    _, headers = enrolled_student(client, make_user, course_id)
    _, outsider = make_user("student")
    started = client.post(f"{API}/diagnostic/start", headers=headers, json={"course_id": course_id}).json()
    session_id, item = started["session_id"], started["item"]
    wrong_for = placement_course["misconceptions"][0]

    body = {"session_id": session_id, "problem_id": item["problem_id"], "option_id": option(item, "right")["id"]}
    assert client.post(f"{API}/diagnostic/answer", headers=outsider, json=body).status_code == 404
    assert client.post(f"{API}/diagnostic/start", headers=outsider, json={"course_id": course_id}).status_code == 403
    assert client.post(f"{API}/diagnostic/answer", headers=headers, json={**body, "problem_id": 0}).status_code == 409
    other_option = {**body, "option_id": 0}
    assert client.post(f"{API}/diagnostic/answer", headers=headers, json=other_option).status_code == 422
    assert client.post(f"{API}/diagnostic/answer", headers=headers, json={**body, "option_id": None}).status_code == 422

    assert client.post(f"{API}/diagnostic/answer", headers=headers, json=body).status_code == 200
    again = client.post(f"{API}/diagnostic/answer", headers=headers, json=body)
    assert again.status_code == 409  # the same item cannot be answered twice
    assert wrong_for  # (placement_course tags both misconceptions on every tracing item)


def test_the_correct_answer_is_not_always_the_first_option(client, make_user, placement_course):
    course_id = placement_course["course_id"]
    positions = set()
    for _ in range(6):
        _, headers = enrolled_student(client, make_user, course_id)
        started = client.post(f"{API}/diagnostic/start", headers=headers, json={"course_id": course_id}).json()
        positions.add([o["text"] for o in started["item"]["options"]].index("right"))
    assert len(positions) > 1


def test_a_problem_whose_worked_solution_was_shown_is_not_a_placement_item(client, make_user, placement_course, owner):
    course_id = placement_course["course_id"]
    user_id, headers = enrolled_student(client, make_user, course_id)
    first = client.post(f"{API}/diagnostic/start", headers=headers, json={"course_id": course_id}).json()["item"]
    with owner.begin() as conn:
        conn.execute(
            text("INSERT INTO worked_examples_seen (user_id, problem_id) VALUES (:u, :p)"),
            {"u": user_id, "p": first["problem_id"]},
        )
    again = client.post(f"{API}/diagnostic/start", headers=headers, json={"course_id": course_id}).json()["item"]
    assert again["problem_id"] != first["problem_id"]
