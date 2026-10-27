"""F-52 (DRD router table): the assistant's recommend and lms routes answer from the student's own records, by the same
rules as the dashboard and the gradebook, through the read-only chat role, with no model writing the reply."""
import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError

from app.llm.adapter import LLMError
from tests.helpers import enroll
from tests.test_chat_api import say
from tests.test_feedback_api import (  # noqa: F401  (fixtures)
    P_REFERENCE,
    FakeLLM,
    failed_submission,
    llm,
    new_student,
    world,
)

API = "/api/v1"


def passed(owner, user_id, problem_id):
    with owner.begin() as conn:
        sid = conn.execute(
            text("INSERT INTO submissions (user_id, problem_id, code) VALUES (:u, :p, 'x') RETURNING id"),
            {"u": user_id, "p": problem_id},
        ).scalar_one()
        conn.execute(text("INSERT INTO run_results (submission_id, status, passed, failed) VALUES (:s, 'passed', 1, 0)"),
                     {"s": sid})


def test_recommend_gives_the_dashboards_next_problem_with_its_reason_and_a_notes_section(client, make_user, world, llm):
    _, headers = new_student(client, make_user, world)
    fake = llm(FakeLLM())
    body = say(client, headers, "what should I do next", route="recommend")
    dashboard = client.get(f"{API}/students/me/mastery", params={"course_id": world["course"]}, headers=headers).json()
    expected = dashboard["recommended"]
    assert body["route"] == "recommend" and fake.calls == []  # no model wrote this
    assert f'"{expected["title"]}"' in body["reply"] and "loops is your weakest area" in body["reply"]
    assert f"problem:{expected['problem_id']}" in body["tools"]
    assert body["sources"] and body["sources"][0]["title"] == "Loops" and "course notes" in body["reply"]


def test_recommend_says_so_when_everything_is_solved(client, make_user, world, owner, llm):
    user_id, headers = new_student(client, make_user, world)
    for problem in (world["p"], world["q"]):
        passed(owner, user_id, problem)
    llm(FakeLLM())
    assert "solved every coding problem" in say(client, headers, "next?", route="recommend")["reply"]


def make_assignment(client, world, title, due, problems):
    made = client.post(f"{API}/courses/{world['course']}/assignments", headers=world["instructor"], json={
        "title": title, "confirm_past_due": True, "due_at": due.isoformat(), "problems": [{"problem_id": p, "points": 2} for p in problems]})
    assert made.status_code == 201, made.text
    return made.json()


def test_lms_grades_are_the_gradebooks_numbers_for_this_student_only(client, make_user, world, owner, llm):
    tag = datetime.now(UTC).strftime("%H%M%S%f")
    week = make_assignment(client, world, f"Graded week {tag}", datetime.now(UTC) + timedelta(days=3), [world["p"]])
    me, headers = new_student(client, make_user, world)
    other, other_headers = new_student(client, make_user, world)
    failed_submission(client, world, headers)  # 1 of 2 tests: 1 point of 2
    client.post(f"{API}/submissions", headers=other_headers, json={"problem_id": world["p"], "code": P_REFERENCE})
    llm(FakeLLM())
    reply = say(client, headers, "what are my grades", route="lms")["reply"]
    book = client.get(f"{API}/courses/{world['course']}/gradebook", headers=world["instructor"]).json()
    mine = next(c for r in book["students"] if r["student_id"] == me for c in r["cells"] if c["assignment_id"] == week["id"])
    theirs = next(c for r in book["students"] if r["student_id"] == other for c in r["cells"] if c["assignment_id"] == week["id"])
    assert f'"{week["title"]}": {mine["score"]:g} of 2' in reply
    assert theirs["score"] != mine["score"] and f'"{week["title"]}": {theirs["score"]:g} of 2' not in reply


def test_lms_lists_upcoming_deadlines_and_missed_work(client, make_user, world, llm):
    tag = datetime.now(UTC).strftime("%H%M%S%f")
    soon = make_assignment(client, world, f"Soon {tag}", datetime.now(UTC) + timedelta(days=2), [world["q"]])
    gone = make_assignment(client, world, f"Gone {tag}", datetime.now(UTC) - timedelta(days=1), [world["q"]])
    _, headers = new_student(client, make_user, world)
    llm(FakeLLM())
    reply = say(client, headers, "when is the next deadline", route="lms")["reply"]
    assert f'"{soon["title"]}" (Feedback course) is due' in reply and "not started" in reply
    assert f'Missed: "{gone["title"]}"' in reply


def test_lms_announcements_come_only_from_the_students_courses(client, make_user, world, llm):
    tag = datetime.now(UTC).strftime("%H%M%S%f")
    client.post(f"{API}/courses/{world['course']}/announcements", headers=world["instructor"],
                json={"title": f"Room change {tag}", "body": "Lab 2 moves to room 101."})
    _, elsewhere = make_user("instructor")
    other = client.post(f"{API}/courses", headers=elsewhere, json={"title": "Elsewhere"}).json()
    client.post(f"{API}/courses/{other['id']}/announcements", headers=elsewhere,
                json={"title": f"Not yours {tag}", "body": "x"})
    _, headers = new_student(client, make_user, world)
    llm(FakeLLM())
    reply = say(client, headers, "any announcements?", route="lms")["reply"]
    assert f"Room change {tag}" in reply and f"Not yours {tag}" not in reply


def test_both_routes_work_with_the_model_switched_off(client, make_user, world, llm):
    _, headers = new_student(client, make_user, world)
    llm(FakeLLM(LLMError("every provider failed"), LLMError("every provider failed")))
    grades = say(client, headers, "show me the grades")
    nextup = say(client, headers, "what should I practise next")
    assert grades["route"] == "lms" and grades["router"]["how"] == "keyword" and "on-time scores" in grades["reply"]
    assert nextup["route"] == "recommend" and "weakest area" in nextup["reply"]


def test_recommend_skips_a_course_that_was_archived(client, make_user, world, llm):
    _, teacher = make_user("instructor")
    old = client.post(f"{API}/courses", headers=teacher, json={"title": "Last term"}).json()["id"]
    client.post(f"{API}/courses/{old}/concepts", headers=teacher, json={"name": "recursion"})
    _, headers = make_user("student")
    assert enroll(client, old, headers).status_code == 200
    assert enroll(client, world['course'], headers).status_code == 200
    assert client.post(f"{API}/courses/{old}/archive", headers=teacher).status_code == 200
    llm(FakeLLM())
    reply = say(client, headers, "what should I do next", route="recommend")["reply"]
    assert "loops is your weakest area" in reply and "recursion" not in reply


def test_an_archived_course_is_closed_to_its_students_until_it_is_restored(client, make_user, world):
    _, headers = new_student(client, make_user, world)
    course, problem = world["course"], world["p"]
    reach = [
        lambda: client.get(f"{API}/problems", params={"course_id": course}, headers=headers),
        lambda: client.get(f"{API}/problems/{problem}", headers=headers),
        lambda: client.post(f"{API}/submissions", headers=headers, json={"problem_id": problem, "code": "print(2)"}),
        lambda: client.get(f"{API}/students/me/mastery", params={"course_id": course}, headers=headers),
    ]
    assert client.post(f"{API}/courses/{course}/archive", headers=world["instructor"]).status_code == 200
    try:
        assert [r().status_code for r in reach] == [403, 404, 404, 403]
    finally:
        assert client.post(f"{API}/courses/{course}/restore", headers=world["instructor"]).status_code == 200
    assert [r().status_code for r in reach[:2]] == [200, 200]


def test_a_student_with_no_course_is_told_so(client, make_user, llm):
    _, headers = make_user("student")
    llm(FakeLLM())
    for name in ("recommend", "lms"):
        assert "not enrolled" in say(client, headers, "x", route=name)["reply"]


def test_the_chat_role_reads_course_records_and_the_shared_rules_but_never_code_or_accounts():
    chat = create_engine(os.environ["CHAT_DATABASE_URL"])
    with chat.connect() as conn:
        for statement in ("SELECT * FROM assignments LIMIT 1", "SELECT * FROM announcements LIMIT 1",
                          "SELECT * FROM chunks LIMIT 1", "SELECT * FROM assignment_scores(0, 0)",
                          "SELECT * FROM next_problem(0, 0, 0)"):
            conn.execute(text(statement))
    for statement in ("SELECT * FROM submissions", "SELECT * FROM run_results", "SELECT * FROM users",
                      "SELECT code FROM submissions", "SELECT * FROM problems", "INSERT INTO announcements"
                      " (course_id, author_id, title, body) VALUES (1, 1, 'x', 'y')"):
        with pytest.raises(ProgrammingError, match="permission denied"):
            with chat.begin() as conn:
                conn.execute(text(statement))
