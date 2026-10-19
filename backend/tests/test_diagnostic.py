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


def test_a_new_student_completes_the_whole_test_and_sees_a_vector_and_misconceptions(
    client, make_user, placement_course, owner
):
    course_id, wrong_for = placement_course["course_id"], placement_course["misconceptions"][0]
    user_id, headers = enrolled_student(client, make_user, course_id)

    started = client.post(f"{API}/diagnostic/start", headers=headers, json={"course_id": course_id}).json()
    assert started["item_number"] == 1 and started["max_items"] == 12  # 9 tracing questions and 3 coding tasks
    assert get_redis().exists(f"diagnostic:{started['session_id']}")  # the session is in Redis, not process memory
    assert {o["text"] for o in started["item"]["options"]} >= {"right"}
    client.post(f"{API}/diagnostic/answer", headers=headers, json={
        "session_id": started["session_id"], "problem_id": started["item"]["problem_id"],
        "option_id": option(started["item"], f"wrong {wrong_for}")["id"],
    })

    # a second student runs the whole test
    other_id, other = enrolled_student(client, make_user, course_id)
    session_id, kinds, result = run_whole_test(client, other, course_id, wrong_for)

    assert len(kinds) == 12 and kinds.count("code") == 3
    assert kinds[: selection.WARMUP_ITEMS] == ["mcq"] * selection.WARMUP_ITEMS
    for i, (a, b) in enumerate(zip(kinds, kinds[1:], strict=False)):
        if a == b == "code":
            assert kinds[: i + 2].count("mcq") == 9  # two coding tasks in a row only once the tracing questions ran out
    assert len(result["mastery"]) == 3
    names = {m["name"] for m in result["misconceptions"]}
    with owner.connect() as conn:
        tagged = conn.execute(text("SELECT name FROM misconceptions WHERE id = :m"), {"m": wrong_for}).scalar_one()
        status = conn.execute(
            text("SELECT status FROM diagnostic_sessions WHERE id = :i"), {"i": int(session_id)}
        ).scalar_one()
        ledger = conn.execute(text("SELECT count(*) FROM mastery_events WHERE user_id = :u"), {"u": other_id}).scalar_one()
    assert tagged in names and result["misconceptions"][0]["probability"] > 0.5
    assert status == "completed" and ledger >= 12
    assert not get_redis().exists(f"diagnostic:{session_id}")


def test_students_get_different_first_questions(client, make_user, placement_course):
    course_id = placement_course["course_id"]
    first_questions = set()
    for _ in range(8):
        _, headers = enrolled_student(client, make_user, course_id)
        started = client.post(f"{API}/diagnostic/start", headers=headers, json={"course_id": course_id}).json()
        first_questions.add(started["item"]["problem_id"])
    assert len(first_questions) >= 2  # chosen by a seeded draw among the best few, so not always the same one


def test_dont_know_counts_as_not_known_and_never_raises_a_misconception(
    client, make_user, placement_course, owner
):
    course_id = placement_course["course_id"]
    user_id, headers = enrolled_student(client, make_user, course_id)
    started = client.post(f"{API}/diagnostic/start", headers=headers, json={"course_id": course_id}).json()
    response = client.post(f"{API}/diagnostic/answer", headers=headers, json={
        "session_id": started["session_id"], "problem_id": started["item"]["problem_id"], "dont_know": True,
    })
    assert response.status_code == 200, response.text
    with owner.connect() as conn:
        rows = conn.execute(
            text("SELECT evidence_type, correct FROM mastery_events WHERE user_id = :u AND rule_id = 'bayes_update'"),
            {"u": user_id},
        ).all()
        picked = conn.execute(text("SELECT count(*) FROM misconception_state WHERE user_id = :u"), {"u": user_id}).scalar_one()
    assert rows and {tuple(r) for r in rows} == {("diagnostic_mcq_dontknow", False)}
    assert picked == 0


def test_a_wrong_answer_marked_sure_raises_the_misconception_more(client, make_user, placement_course, owner):
    course_id, wrong_for = placement_course["course_id"], placement_course["misconceptions"][0]

    def probability(confidence):
        user_id, headers = enrolled_student(client, make_user, course_id)
        started = client.post(f"{API}/diagnostic/start", headers=headers, json={"course_id": course_id}).json()
        item = started["item"]
        body = {"session_id": started["session_id"], "problem_id": item["problem_id"],
                "option_id": option(item, f"wrong {wrong_for}")["id"], "confidence": confidence}
        assert client.post(f"{API}/diagnostic/answer", headers=headers, json=body).status_code == 200
        with owner.connect() as conn:
            return conn.execute(
                text("SELECT probability FROM misconception_state WHERE user_id = :u AND misconception_id = :m"),
                {"u": user_id, "m": wrong_for},
            ).scalar_one()

    assert probability("sure") > probability(None)


def test_the_background_answer_is_stored_and_checked(client, make_user, placement_course, owner):
    course_id = placement_course["course_id"]
    user_id, headers = enrolled_student(client, make_user, course_id)
    bad = client.post(f"{API}/diagnostic/start", headers=headers, json={"course_id": course_id, "background": "expert"})
    assert bad.status_code == 422
    ok = client.post(f"{API}/diagnostic/start", headers=headers, json={"course_id": course_id, "background": "new"})
    assert ok.status_code == 200
    with owner.connect() as conn:
        stored = conn.execute(
            text("SELECT background FROM enrollments WHERE user_id = :u AND course_id = :c"),
            {"u": user_id, "c": course_id},
        ).scalar_one()
    assert stored == "new"


def test_a_course_with_only_coding_tasks_runs_the_test_and_assignment_problems_are_left_out(
    client, make_user, owner
):
    instructor_id, _ = make_user("instructor")
    with owner.begin() as conn:
        course_id = conn.execute(
            text("INSERT INTO courses (title, instructor_id) VALUES ('Coding only', :i) RETURNING id"), {"i": instructor_id}
        ).scalar_one()
        concept = conn.execute(
            text("INSERT INTO concepts (course_id, name) VALUES (:c, 'only') RETURNING id"), {"c": course_id}
        ).scalar_one()
        problems = []
        for n in range(4):
            pid = conn.execute(
                text(
                    "INSERT INTO problems (course_id, title, statement, kind, difficulty_b, discrimination_a,"
                    " reference_solution) VALUES (:c, :t, 'statement', 'code', :b, 1.0, :r) RETURNING id"
                ),
                {"c": course_id, "t": f"task {n}", "b": -0.8 + 0.5 * n, "r": PLACEMENT_RIGHT},
            ).scalar_one()
            conn.execute(text("INSERT INTO problem_concepts VALUES (:p, :c, 1.0)"), {"p": pid, "c": concept})
            conn.execute(
                text(
                    "INSERT INTO test_cases (problem_id, input, expected, hidden, category)"
                    " VALUES (:p, :i1, :e1, false, 'basic'), (:p, :i2, :e2, true, 'basic')"
                ),
                {"p": pid, "i1": "1\n", "e1": "2\n", "i2": "9\n", "e2": "10\n"},
            )
            problems.append(pid)
        assignment = conn.execute(
            text("INSERT INTO assignments (course_id, title, due_at) VALUES (:c, 'hw', now() + interval '1 day') RETURNING id"),
            {"c": course_id},
        ).scalar_one()
        conn.execute(
            text("INSERT INTO assignment_problems (assignment_id, problem_id) VALUES (:a, :p)"),
            {"a": assignment, "p": problems[3]},
        )
    _, headers = enrolled_student(client, make_user, course_id)
    started = client.post(f"{API}/diagnostic/start", headers=headers, json={"course_id": course_id}).json()
    assert started["max_items"] == 3 and started["item"]["kind"] == "code"
    asked, item = [], started["item"]
    while True:
        asked.append(item["problem_id"])
        data = answer(client, headers, started["session_id"], item).json()
        if data["done"]:
            break
        item = data["next_item"]
    assert len(asked) == 3 and problems[3] not in asked


def test_dashboard_and_the_why_view_read_from_the_ledger(client, make_user, placement_course):
    course_id, wrong_for = placement_course["course_id"], placement_course["misconceptions"][1]
    user_id, headers = enrolled_student(client, make_user, course_id)
    run_whole_test(client, headers, course_id, wrong_for)

    dashboard = client.get(f"{API}/students/me/mastery", headers=headers, params={"course_id": course_id}).json()
    assert dashboard["placement_completed"] is True and dashboard["placement_available"] is True
    assert all(c["status"] == "assessed" and c["evidence_count"] > 0 and c["confidence"] for c in dashboard["concepts"])
    assert all(c["last_assessed"] for c in dashboard["concepts"])
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
    assert {"bayes_update", "pooled_estimate"} <= rules  # the placement ends by setting each concept to the pooled estimate


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


def mastery_page(client, headers, course_id):
    return client.get(f"{API}/students/me/mastery", headers=headers, params={"course_id": course_id}).json()


def test_a_recheck_is_offered_after_ten_submissions_or_two_weeks_and_not_before(
    client, make_user, placement_course, owner
):
    course_id, wrong_for = placement_course["course_id"], placement_course["misconceptions"][0]
    user_id, headers = enrolled_student(client, make_user, course_id)
    assert mastery_page(client, headers, course_id)["recheck_due"] is False  # no placement yet
    run_whole_test(client, headers, course_id, wrong_for)
    page = mastery_page(client, headers, course_id)
    assert page["recheck_due"] is False and page["recheck_concepts"] == []  # it was just done

    with owner.begin() as conn:
        problem = conn.execute(
            text("SELECT id FROM problems WHERE course_id = :c AND kind = 'code' LIMIT 1"), {"c": course_id}
        ).scalar_one()
        for _ in range(10):
            conn.execute(text("INSERT INTO submissions (user_id, problem_id, code) VALUES (:u, :p, 'x')"),
                         {"u": user_id, "p": problem})
    page = mastery_page(client, headers, course_id)
    assert page["recheck_due"] is True
    assert 1 <= len(page["recheck_concepts"]) <= 3 and set(page["recheck_concepts"]) <= {"alpha", "beta", "gamma"}

    other_id, other = enrolled_student(client, make_user, course_id)
    run_whole_test(client, other, course_id, wrong_for)
    with owner.begin() as conn:
        conn.execute(text("UPDATE mastery_events SET created_at = now() - interval '20 days' WHERE user_id = :u"),
                     {"u": other_id})
    assert mastery_page(client, other, course_id)["recheck_due"] is True


def test_a_recheck_asks_four_questions_and_adds_to_the_ledger_without_redoing_the_placement(
    client, make_user, placement_course, owner
):
    course_id, wrong_for = placement_course["course_id"], placement_course["misconceptions"][0]
    user_id, headers = enrolled_student(client, make_user, course_id)
    run_whole_test(client, headers, course_id, wrong_for)
    with owner.begin() as conn:
        conn.execute(text("UPDATE mastery_events SET created_at = now() - interval '20 days' WHERE user_id = :u"),
                     {"u": user_id})
    pooled_before = events_of(owner, user_id, "pooled_estimate")

    started = client.post(f"{API}/diagnostic/start", headers=headers, json={"course_id": course_id, "mode": "recheck"}).json()
    assert started["max_items"] == 4
    session_id, item, asked = started["session_id"], started["item"], 0
    while True:
        asked += 1
        data = answer(client, headers, session_id, item, wrong_for=wrong_for).json()
        if data["done"]:
            break
        item = data["next_item"]
    assert asked == 4 and len(data["result"]["mastery"]) == 3

    with owner.connect() as conn:
        added = conn.execute(
            text("SELECT count(DISTINCT evidence_ref) FROM mastery_events WHERE user_id = :u AND rule_id = 'bayes_update'"
                 " AND evidence_ref LIKE :p"), {"u": user_id, "p": f"diagnostic:{session_id}:%"},
        ).scalar_one()
    assert added == 4  # its answers are ordinary evidence
    assert events_of(owner, user_id, "pooled_estimate") == pooled_before  # no new placement estimate
    page = mastery_page(client, headers, course_id)
    assert page["placement_completed"] is True and page["recheck_due"] is False  # the re-check renewed the evidence


def events_of(owner, user_id, rule):
    with owner.connect() as conn:
        return conn.execute(
            text("SELECT count(*) FROM mastery_events WHERE user_id = :u AND rule_id = :r"), {"u": user_id, "r": rule}
        ).scalar_one()


def test_a_recheck_alone_does_not_count_as_taking_the_placement(client, make_user, placement_course):
    course_id = placement_course["course_id"]
    _, headers = enrolled_student(client, make_user, course_id)
    started = client.post(f"{API}/diagnostic/start", headers=headers, json={"course_id": course_id, "mode": "recheck"}).json()
    item, session_id = started["item"], started["session_id"]
    while True:
        data = answer(client, headers, session_id, item, wrong_for=placement_course["misconceptions"][0]).json()
        if data["done"]:
            break
        item = data["next_item"]
    assert mastery_page(client, headers, course_id)["placement_completed"] is False


def test_a_question_archived_during_the_test_does_not_break_it(client, make_user, placement_course, owner):
    course_id, wrong_for = placement_course["course_id"], placement_course["misconceptions"][0]
    user_id, headers = enrolled_student(client, make_user, course_id)
    started = client.post(f"{API}/diagnostic/start", headers=headers, json={"course_id": course_id}).json()
    session_id, first = started["session_id"], started["item"]
    second = answer(client, headers, session_id, first, wrong_for=wrong_for).json()["next_item"]
    with owner.begin() as conn:  # the teacher archives the question just answered and the one on screen
        conn.execute(
            text("UPDATE problems SET archived_at = now() WHERE id = ANY(:ids)"),
            {"ids": [first["problem_id"], second["problem_id"]]},
        )
    response = answer(client, headers, session_id, second, wrong_for=wrong_for)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["done"] or data["next_item"]["problem_id"] not in (first["problem_id"], second["problem_id"])
    with owner.connect() as conn:
        recorded = conn.execute(
            text("SELECT count(DISTINCT evidence_ref) FROM mastery_events WHERE user_id = :u AND rule_id = 'bayes_update'"
                 " AND evidence_ref LIKE :p"),
            {"u": user_id, "p": f"diagnostic:{session_id}:%"},
        ).scalar_one()
    assert recorded == 1  # only the answer given before the change; none for the archived question
    item = data["next_item"]
    while not data["done"]:  # the rest of the test still finishes
        data = answer(client, headers, session_id, item, wrong_for=wrong_for).json()
        item = data["next_item"]
    assert len(data["result"]["mastery"]) == 3
