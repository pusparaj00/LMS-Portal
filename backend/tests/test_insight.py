"""F-90, F-91, F-92: at-risk alerts with their reasons, quiz question analysis, and the content report."""
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from tests.helpers import enroll

API = "/api/v1"


def when(days: float) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


@pytest.fixture
def course(client, make_user):
    teacher_id, teacher = make_user("instructor")
    made = client.post(f"{API}/courses", headers=teacher, json={"title": f"Insight {uuid.uuid4().hex[:6]}"}).json()
    return {"id": made["id"], "teacher": teacher, "teacher_id": teacher_id}


def student(client, make_user, course):
    user_id, headers = make_user("student")
    assert enroll(client, course["id"], headers).status_code == 200
    return user_id, headers


def work(client, course, title, due, points=10):
    body = {"title": title, "confirm_past_due": True, "due_at": when(due), "work": {"instructions": "Do it.", "points": points}}
    made = client.post(f"{API}/courses/{course['id']}/assignments", headers=course["teacher"], json=body)
    assert made.status_code == 201, made.text
    return made.json()


def give(client, course, assignment, student_id, score):
    url = f"{API}/courses/{course['id']}/assignments/{assignment['id']}/students/{student_id}/override"
    assert client.put(url, headers=course["teacher"], json={"score": score, "reason": "test"}).status_code == 204


def report(client, course, who=None):
    return client.get(f"{API}/courses/{course['id']}/at-risk", headers=who or course["teacher"])


def factors_of(found, student_id):
    return {f["kind"]: f for s in found["students"] if s["student_id"] == student_id for f in s["factors"]}


# ---- F-90

def test_a_student_with_missing_work_is_flagged_with_the_assignments_that_are_missing(client, make_user, course):
    done_id, _ = student(client, make_user, course)
    gone_id, _ = student(client, make_user, course)
    for n, due in enumerate((-3, -2, -1)):
        a = work(client, course, f"Task {n}", due)
        give(client, course, a, done_id, 10)
    found = report(client, course).json()
    assert found["checked"] == 2
    gone = factors_of(found, gone_id)
    assert set(gone) >= {"missing_work", "low_scores"}
    assert gone["missing_work"]["evidence"] == ["Task 0", "Task 1", "Task 2"]
    assert "3 assignments" in gone["missing_work"]["summary"]
    assert factors_of(found, done_id) == {}  # full marks on everything: nothing to flag
    assert found["thresholds"]["missing_assignments"] == 2


def test_low_scores_are_reported_as_a_percentage_with_the_scores_behind_it(client, make_user, course):
    sid, _ = student(client, make_user, course)
    for n in range(3):
        give(client, course, work(client, course, f"Work {n}", -n - 1), sid, 2)
    low = factors_of(report(client, course).json(), sid)["low_scores"]
    assert low["summary"] == "20.0% of the points on 3 past-due assignments"
    assert sorted(low["evidence"]) == ["Work 0: 2 of 10", "Work 1: 2 of 10", "Work 2: 2 of 10"]


def test_falling_scores_compare_the_latest_two_with_the_earlier_work(client, make_user, course):
    sid, _ = student(client, make_user, course)
    for n, score in enumerate((10, 10, 3, 3)):  # 100, 100, 30, 30: earlier 100%, latest 30%
        give(client, course, work(client, course, f"Step {n}", -(4 - n)), sid, score)
    found = factors_of(report(client, course).json(), sid)
    assert "falling_scores" in found and "70 points lower" in found["falling_scores"]["summary"]
    assert found["falling_scores"]["evidence"] == ["earlier assignments averaged 100%", "the latest 2 averaged 30%"]
    assert "low_scores" not in found  # 65 percent overall: not low, only falling


def test_low_mastery_needs_enough_concepts_with_evidence(client, make_user, owner, course):
    sid, _ = student(client, make_user, course)
    ids = [client.post(f"{API}/courses/{course['id']}/concepts", headers=course["teacher"], json={"name": f"topic {n}"}).json()["concept_id"]
           for n in range(3)]
    with owner.begin() as conn:
        for concept in ids[:2]:
            conn.execute(text("INSERT INTO mastery (user_id, concept_id, p_known) VALUES (:u, :c, 0.2)"), {"u": sid, "c": concept})
    assert factors_of(report(client, course).json(), sid) == {}  # two concepts are not enough
    with owner.begin() as conn:
        conn.execute(text("INSERT INTO mastery (user_id, concept_id, p_known) VALUES (:u, :c, 0.2)"), {"u": sid, "c": ids[2]})
    low = factors_of(report(client, course).json(), sid)["low_mastery"]
    assert low["summary"] == "average mastery is 20% over 3 concepts with evidence"
    assert low["evidence"] == ["topic 0: 20%", "topic 1: 20%", "topic 2: 20%"]


def test_inactivity_needs_a_week_of_enrolment_and_two_weeks_without_activity(client, make_user, owner, course):
    new_id, _ = student(client, make_user, course)
    old_id, _ = student(client, make_user, course)
    with owner.begin() as conn:
        conn.execute(text("UPDATE enrollments SET enrolled_at = now() - interval '30 days' WHERE user_id = :u AND course_id = :c"),
                     {"u": old_id, "c": course["id"]})
    found = report(client, course).json()
    assert factors_of(found, new_id) == {}
    quiet = factors_of(found, old_id)["inactive"]
    assert quiet["summary"].startswith("no activity since joining 30 days ago")
    with owner.begin() as conn:  # a lesson completion counts as activity
        module = conn.execute(text("INSERT INTO modules (course_id, title, position) VALUES (:c, 'm', 0) RETURNING id"),
                              {"c": course["id"]}).scalar_one()
        item = conn.execute(text("INSERT INTO content_items (module_id, kind, title, body, position) VALUES (:m, 'text', 't', 'b', 0)"
                                 " RETURNING id"), {"m": module}).scalar_one()
        conn.execute(text("INSERT INTO item_completions (user_id, item_id, completed_at) VALUES (:u, :i, now() - interval '20 days')"),
                     {"u": old_id, "i": item})
    assert factors_of(report(client, course).json(), old_id)["inactive"]["summary"] == "no activity for 20 days"
    with owner.begin() as conn:
        conn.execute(text("UPDATE item_completions SET completed_at = now() - interval '2 days' WHERE user_id = :u"), {"u": old_id})
    assert factors_of(report(client, course).json(), old_id) == {}


def test_alerts_list_the_students_with_the_most_signs_first_and_only_the_courses_own_people_see_them(
    client, make_user, owner, course
):
    most_id, _ = student(client, make_user, course)
    fewer_id, _ = student(client, make_user, course)
    for n in range(2):
        work(client, course, f"Task {n}", -n - 1)  # nobody hands anything in
    with owner.begin() as conn:
        conn.execute(text("UPDATE enrollments SET enrolled_at = now() - interval '30 days' WHERE user_id = :u AND course_id = :c"),
                     {"u": most_id, "c": course["id"]})
    found = report(client, course).json()
    assert [s["student_id"] for s in found["students"]] == [most_id, fewer_id]
    assert set(factors_of(found, most_id)) == {"missing_work", "low_scores", "inactive"}
    assert set(factors_of(found, fewer_id)) == {"missing_work", "low_scores"}
    _, other = make_user("instructor")
    _, pupil = make_user("student")
    _, admin = make_user("admin")
    assert report(client, course, other).status_code == 403
    assert report(client, course, pupil).status_code == 403
    assert report(client, course, admin).status_code == 200
    assert client.get(f"{API}/courses/{course['id']}/at-risk").status_code == 401


# ---- F-91

def test_the_quiz_report_counts_each_students_latest_attempt_per_question(client, make_user, course):
    quiz = client.post(f"{API}/courses/{course['id']}/quizzes", headers=course["teacher"], json={
        "title": "Loops", "max_attempts": 2, "published": True, "questions": [
            {"kind": "single", "prompt": "Which starts a loop?", "options": ["for", "if", "def"], "correct_choices": [0]},
            {"kind": "multiple", "prompt": "Loop keywords?", "options": ["for", "while", "else"], "correct_choices": [0, 1]},
            {"kind": "short", "prompt": "Length function?", "accepted": ["len"]},
        ]}).json()
    q1, q2, q3 = (q["id"] for q in quiz["question_list"])

    def attempt(headers, c1, c2, t3):
        body = {"answers": [{"question_id": q1, "choices": c1}, {"question_id": q2, "choices": c2},
                            {"question_id": q3, "text": t3}]}
        assert client.post(f"{API}/courses/{course['id']}/quizzes/{quiz['id']}/attempts", headers=headers, json=body).status_code == 201

    heads = [student(client, make_user, course)[1] for _ in range(4)]
    attempt(heads[0], [0], [0, 1], "len")  # all right
    attempt(heads[1], [0], [0], "len")  # q2 wrong
    attempt(heads[2], [1], [2], "x")  # all wrong
    attempt(heads[3], [0], [0, 1], "len")  # right first, then
    attempt(heads[3], [1], [2], "x")  # all wrong: only this one counts
    rep = client.get(f"{API}/courses/{course['id']}/quizzes/{quiz['id']}/report", headers=course["teacher"]).json()
    assert (rep["students"], rep["attempts"], rep["average_percent"]) == (4, 5, 41.7)  # (100 + 66.7 + 0 + 0) / 4
    by = {q["question_id"]: q for q in rep["questions"]}
    assert (by[q1]["answered"], by[q1]["right"], by[q1]["percent_right"]) == (4, 2, 50.0)
    assert by[q1]["chosen_counts"] == [2, 2, 0] and by[q1]["right_choices"] == [0]
    assert (by[q2]["right"], by[q2]["percent_right"], by[q2]["class_missed"]) == (1, 25.0, True)
    assert by[q2]["chosen_counts"] == [2, 1, 2]
    assert (by[q3]["right"], by[q3]["class_missed"], by[q3]["chosen_counts"]) == (2, False, [])
    assert by[q1]["class_missed"] is False  # 50 percent is not below the line
    _, pupil = make_user("student")
    assert client.get(f"{API}/courses/{course['id']}/quizzes/{quiz['id']}/report", headers=pupil).status_code == 403
    assert client.get(f"{API}/courses/{course['id']}/quizzes/9999999/report", headers=course["teacher"]).status_code == 404


def test_a_quiz_nobody_took_reports_zeros_not_an_error(client, course):
    quiz = client.post(f"{API}/courses/{course['id']}/quizzes", headers=course["teacher"], json={
        "title": "Empty", "published": True,
        "questions": [{"kind": "short", "prompt": "p", "accepted": ["a"]}]}).json()
    rep = client.get(f"{API}/courses/{course['id']}/quizzes/{quiz['id']}/report", headers=course["teacher"]).json()
    assert (rep["students"], rep["attempts"], rep["average_percent"]) == (0, 0, None)
    assert rep["questions"][0]["answered"] == 0 and rep["questions"][0]["percent_right"] is None


# ---- F-92

def test_the_content_report_compares_finishers_with_the_rest_only_when_both_groups_are_big_enough(client, make_user, course):
    module = client.post(f"{API}/courses/{course['id']}/modules", headers=course["teacher"], json={"title": "Loops"}).json()
    client.patch(f"{API}/courses/{course['id']}/modules/{module['id']}", headers=course["teacher"], json={"published": True})
    items = [client.post(f"{API}/courses/{course['id']}/modules/{module['id']}/items", headers=course["teacher"],
                         json={"kind": "text", "title": t, "body": "Read this."}).json() for t in ("Lesson A", "Lesson B")]
    a = work(client, course, "Essay", 5)
    pupils = [student(client, make_user, course) for _ in range(6)]
    scores = [9, 8, 7, 5, 4, 3]  # out of 10: the first three finish Lesson A
    for (sid, _headers), score in zip(pupils, scores, strict=True):
        give(client, course, a, sid, score)
    for _sid, headers in pupils[:3]:
        assert client.put(f"{API}/courses/{course['id']}/items/{items[0]['id']}/completion", headers=headers).status_code == 204
    assert client.put(f"{API}/courses/{course['id']}/items/{items[1]['id']}/completion", headers=pupils[0][1]).status_code == 204
    rep = client.get(f"{API}/courses/{course['id']}/content-report", headers=course["teacher"]).json()
    assert (rep["students"], rep["min_group"]) == (6, 3)
    lesson_a, lesson_b = rep["items"]
    assert (lesson_a["title"], lesson_a["completed"], lesson_a["not_completed"]) == ("Lesson A", 3, 3)
    assert lesson_a["scores"] == {"n_with": 3, "n_without": 3, "average_with": 80.0, "average_without": 40.0,
                                  "difference": 40.0}
    assert lesson_a["mastery"]["difference"] is None and lesson_a["mastery"]["n_with"] == 0  # nobody has mastery data
    assert lesson_b["completed"] == 1 and lesson_b["scores"]["difference"] is None  # one finisher is not a group
    _, pupil = make_user("student")
    assert client.get(f"{API}/courses/{course['id']}/content-report", headers=pupil).status_code == 403
