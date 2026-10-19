"""F-87, F-88, F-89: weighted grade categories, rubrics, and audited score overrides."""
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from tests.helpers import enroll

API = "/api/v1"


def when(days: float = 0) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


@pytest.fixture
def course(client, make_user):
    teacher_id, teacher = make_user("instructor")
    made = client.post(f"{API}/courses", headers=teacher, json={"title": f"Grading {uuid.uuid4().hex[:6]}"}).json()
    student_id, student = make_user("student")
    assert enroll(client, made["id"], student).status_code == 200
    return {"id": made["id"], "teacher": teacher, "teacher_id": teacher_id, "student": student, "student_id": student_id}


def category(client, course, name, weight):
    made = client.post(f"{API}/courses/{course['id']}/categories", headers=course["teacher"],
                       json={"name": name, "weight": weight})
    assert made.status_code == 201, made.text
    return next(c for c in made.json() if c["name"] == name)


def work(client, course, title, points, due=3, **extra):
    body = {"title": title, "due_at": when(due), "work": {"instructions": "Do it.", "points": points}, **extra}
    made = client.post(f"{API}/courses/{course['id']}/assignments", headers=course["teacher"], json=body)
    assert made.status_code == 201, made.text
    return made.json()


def hand_in_and_grade(client, course, assignment, score, headers=None):
    base = f"{API}/courses/{course['id']}/assignments/{assignment['id']}/work"
    client.post(f"{base}/draft", headers=course["student"], json={"text": "my work"})
    assert client.post(f"{base}/turn-in", headers=course["student"]).status_code == 200
    url = f"{base}/students/{course['student_id']}"
    graded = client.put(f"{url}/grade", headers=headers or course["teacher"], json={"score": score})
    assert graded.status_code == 200, graded.text
    client.post(f"{url}/return", headers=course["teacher"])


def book_row(client, course):
    book = client.get(f"{API}/courses/{course['id']}/gradebook", headers=course["teacher"]).json()
    return next(r for r in book["students"] if r["student_id"] == course["student_id"])


# ---- F-87

def test_categories_are_managed_by_teachers_and_listed_with_their_share(client, make_user, course):
    homework = category(client, course, "Homework", 30)
    exams = category(client, course, "Exams", 70)
    url = f"{API}/courses/{course['id']}/categories"
    listed = client.get(url, headers=course["student"]).json()
    assert {c["name"]: c["share"] for c in listed} == {"Homework": 30.0, "Exams": 70.0}
    assert client.post(url, headers=course["teacher"], json={"name": "homework", "weight": 5}).status_code == 409
    changed = client.put(f"{url}/{homework['id']}", headers=course["teacher"], json={"name": "Homework", "weight": 50})
    assert {c["name"]: c["share"] for c in changed.json()} == {"Homework": 41.7, "Exams": 58.3}
    assert client.put(f"{url}/{exams['id']}", headers=course["teacher"], json={"name": "Homework", "weight": 1}).status_code == 409
    _, other = make_user("instructor")
    assert client.post(url, headers=other, json={"name": "X", "weight": 5}).status_code == 403
    assert client.post(url, headers=course["student"], json={"name": "X", "weight": 5}).status_code == 403
    for bad in ({"name": "", "weight": 5}, {"name": "x", "weight": 0}, {"name": "x", "weight": 101}, {"name": "  ", "weight": 5}):
        assert client.post(url, headers=course["teacher"], json=bad).status_code == 422


def test_the_weighted_grade_matches_a_hand_calculation_and_ignores_empty_categories(client, course):
    homework = category(client, course, "Homework", 30)
    exams = category(client, course, "Exams", 70)
    category(client, course, "Projects", 20)  # nothing in it: it must not pull the grade down
    hw = work(client, course, "HW1", 10, category_id=homework["id"])
    exam = work(client, course, "Exam1", 50, category_id=exams["id"])
    work(client, course, "No category", 10)
    hand_in_and_grade(client, course, hw, 8)  # 80 percent
    hand_in_and_grade(client, course, exam, 30)  # 60 percent
    overall = book_row(client, course)["overall"]
    assert overall["percent"] == 66.0  # (30 * 80 + 70 * 60) / 100
    assert {p["name"]: (p["score"], p["possible"], p["percent"]) for p in overall["parts"]} == {
        "Homework": (8, 10, 80.0), "Exams": (30, 50, 60.0)}
    assert overall["uncategorised"] == 1
    mine = client.get(f"{API}/students/me/grades", headers=course["student"]).json()[0]
    assert mine["overall"]["percent"] == 66.0 and mine["overall"]["uncategorised"] == 1


def test_a_course_without_categories_has_no_weighted_grade_and_deleting_a_category_uncategorises(client, course):
    a = work(client, course, "Alone", 10)
    hand_in_and_grade(client, course, a, 5)
    assert book_row(client, course)["overall"] is None
    cat = category(client, course, "Only", 100)
    url = f"{API}/courses/{course['id']}/assignments/{a['id']}"
    body = {"title": "Alone", "due_at": when(3), "work": {"instructions": "Do it.", "points": 10}, "category_id": cat["id"]}
    assert client.put(url, headers=course["teacher"], json=body).json()["category_id"] == cat["id"]
    assert book_row(client, course)["overall"]["percent"] == 50.0
    assert client.delete(f"{API}/courses/{course['id']}/categories/{cat['id']}", headers=course["teacher"]).status_code == 200
    assert client.get(f"{API}/courses/{course['id']}/assignments", headers=course["teacher"]).json()[0]["category_id"] is None
    assert book_row(client, course)["overall"] is None


def test_an_assignment_can_only_go_in_a_category_of_its_own_course(client, make_user, course):
    elsewhere = client.post(f"{API}/courses", headers=course["teacher"], json={"title": "Elsewhere"}).json()
    foreign = client.post(f"{API}/courses/{elsewhere['id']}/categories", headers=course["teacher"],
                          json={"name": "X", "weight": 10}).json()[0]
    body = {"title": "t", "due_at": when(3), "work": {"instructions": "i", "points": 1}, "category_id": foreign["id"]}
    assert client.post(f"{API}/courses/{course['id']}/assignments", headers=course["teacher"], json=body).status_code == 422


def test_late_hand_ins_stay_out_of_the_weighted_grade(client, course):
    cat = category(client, course, "Homework", 100)
    late = work(client, course, "Late one", 10, due=-1, category_id=cat["id"])
    hand_in_and_grade(client, course, late, 9)
    assert book_row(client, course)["overall"]["percent"] == 0.0  # on-time score only, as everywhere else


# ---- F-89

def test_an_override_replaces_the_score_shows_its_reason_and_is_audited(client, owner, course):
    a = work(client, course, "Essay", 10)
    url = f"{API}/courses/{course['id']}/assignments/{a['id']}/students/{course['student_id']}/override"
    assert client.put(url, headers=course["teacher"], json={"score": 7.5, "reason": "Re-marked after appeal"}).status_code == 204
    cell = next(c for c in book_row(client, course)["cells"] if c["assignment_id"] == a["id"])
    assert (cell["score"], cell["with_late"], cell["override_reason"]) == (7.5, 7.5, "Re-marked after appeal")
    mine = client.get(f"{API}/students/me/grades", headers=course["student"]).json()[0]["assignments"][0]
    assert (mine["score"], mine["override_reason"]) == (7.5, "Re-marked after appeal")
    assert client.get(f"{API}/courses/{course['id']}/assignments", headers=course["student"]).json()[0]["mine"]["score"] == 7.5
    assert client.put(url, headers=course["teacher"], json={"score": 10, "reason": "Full marks"}).status_code == 204
    assert next(c for c in book_row(client, course)["cells"])["status"] == "complete"
    with owner.connect() as conn:
        events = conn.execute(
            text("SELECT detail::text FROM audit_events WHERE user_id = :u AND event = 'grade.overridden' ORDER BY id"),
            {"u": course["teacher_id"]},
        ).scalars().all()
    assert len(events) == 2 and json.loads(events[0])["was"] == 0 and "appeal" not in events[0]
    assert json.loads(events[1])["was"] == 7.5 and json.loads(events[1])["score"] == 10
    assert client.delete(url, headers=course["teacher"]).status_code == 204
    cell = next(c for c in book_row(client, course)["cells"])
    assert (cell["score"], cell["override_reason"]) == (0, None)
    assert client.delete(url, headers=course["teacher"]).status_code == 404


def test_an_override_is_checked_and_only_a_teacher_of_the_course_can_make_one(client, make_user, course):
    a = work(client, course, "Essay", 10)
    url = f"{API}/courses/{course['id']}/assignments/{a['id']}/students/{course['student_id']}/override"
    good = {"score": 5, "reason": "ok"}
    assert client.put(url, headers=course["teacher"], json={"score": 10.5, "reason": "too high"}).status_code == 422
    assert client.put(url, headers=course["teacher"], json={"score": -1, "reason": "negative"}).status_code == 422
    assert client.put(url, headers=course["teacher"], json={"score": 5, "reason": "   "}).status_code == 422
    assert client.put(url, headers=course["teacher"], json={"score": 5}).status_code == 422
    _, other = make_user("instructor")
    assert client.put(url, headers=other, json=good).status_code == 403
    assert client.put(url, headers=course["student"], json=good).status_code == 403
    assert client.put(url, json=good).status_code == 401
    not_given = work(client, course, "Not for them", 10, students=[])
    other_student_id, other_student = make_user("student")
    enroll(client, course["id"], other_student)
    only_other = client.put(f"{API}/courses/{course['id']}/assignments/{not_given['id']}",
                            headers=course["teacher"], json={"title": "Not for them", "due_at": when(3),
                                                             "work": {"instructions": "i", "points": 10},
                                                             "students": [other_student_id]})
    assert only_other.status_code == 200
    skipped = f"{API}/courses/{course['id']}/assignments/{not_given['id']}/students/{course['student_id']}/override"
    assert client.put(skipped, headers=course["teacher"], json=good).status_code == 404


# ---- F-88

RUBRIC = {"title": "Essay rubric", "criteria": [
    {"title": "Argument", "description": "Is there a clear claim?",
     "levels": [{"label": "Weak", "points": 0}, {"label": "Clear", "points": 6}, {"label": "Strong", "points": 4}]},
    {"title": "Style", "levels": [{"label": "Rough", "points": 1}, {"label": "Polished", "points": 4}]},
]}


def make_rubric(client, course, body=None):
    made = client.post(f"{API}/courses/{course['id']}/rubrics", headers=course["teacher"], json=body or RUBRIC)
    assert made.status_code == 201, made.text
    return made.json()


def test_a_rubric_is_stored_with_its_levels_best_first_and_a_top_score(client, course):
    rubric = make_rubric(client, course)
    assert rubric["max_points"] == 10  # 6 + 4
    assert [lv["label"] for lv in rubric["criteria"][0]["levels"]] == ["Clear", "Strong", "Weak"]
    assert [r["id"] for r in client.get(f"{API}/courses/{course['id']}/rubrics", headers=course["teacher"]).json()] == [rubric["id"]]
    assert client.get(f"{API}/courses/{course['id']}/rubrics", headers=course["student"]).status_code == 403


@pytest.mark.parametrize(
    "bad",
    [
        {"title": "x", "criteria": []},
        {"title": "x", "criteria": [{"title": "c", "levels": [{"label": "a", "points": 1}]}]},
        {"title": "x", "criteria": [{"title": "c", "levels": [{"label": "a", "points": 1}, {"label": "a", "points": 2}]}]},
        {"title": "x", "criteria": [{"title": "c", "levels": [{"label": "a", "points": 0}, {"label": "b", "points": 0}]}]},
        {"title": "  ", "criteria": [{"title": "c", "levels": [{"label": "a", "points": 0}, {"label": "b", "points": 1}]}]},
    ],
)
def test_a_malformed_rubric_is_refused(client, course, bad):
    assert client.post(f"{API}/courses/{course['id']}/rubrics", headers=course["teacher"], json=bad).status_code == 422


def graded_with_rubric(client, course):
    rubric = make_rubric(client, course)
    a = work(client, course, "Essay", 10, due=3)
    url = f"{API}/courses/{course['id']}/assignments/{a['id']}"
    body = {"title": "Essay", "due_at": when(3), "work": {"instructions": "Do it.", "points": 10, "rubric_id": rubric["id"]}}
    assert client.put(url, headers=course["teacher"], json=body).status_code == 200
    return rubric, a


def test_work_graded_with_a_rubric_scores_the_sum_of_the_chosen_levels(client, course):
    rubric, a = graded_with_rubric(client, course)
    base = f"{API}/courses/{course['id']}/assignments/{a['id']}/work"
    seen = client.get(base, headers=course["student"]).json()["rubric"]
    assert seen["max_points"] == 10 and all(c["chosen_level_id"] is None for c in seen["criteria"])
    client.post(f"{base}/draft", headers=course["student"], json={"text": "x"})
    client.post(f"{base}/turn-in", headers=course["student"])
    crit = rubric["criteria"]
    pick = {str(crit[0]["id"]): crit[0]["levels"][1]["id"], str(crit[1]["id"]): crit[1]["levels"][0]["id"]}  # Strong 4 + Polished 4
    url = f"{base}/students/{course['student_id']}"
    graded = client.put(f"{url}/grade", headers=course["teacher"], json={"levels": pick, "feedback": "Good"})
    assert graded.status_code == 200 and graded.json()["score"] == 8
    assert [c["chosen_level_id"] for c in graded.json()["rubric"]["criteria"]] == list(pick.values())
    hidden = client.get(base, headers=course["student"]).json()
    assert hidden["score"] is None and all(c["chosen_level_id"] is None for c in hidden["rubric"]["criteria"])
    client.post(f"{url}/return", headers=course["teacher"])
    shown = client.get(base, headers=course["student"]).json()
    assert shown["score"] == 8 and [c["chosen_level_id"] for c in shown["rubric"]["criteria"]] == list(pick.values())


def test_rubric_grading_refuses_a_plain_score_a_missing_criterion_and_a_foreign_level(client, course):
    rubric, a = graded_with_rubric(client, course)
    base = f"{API}/courses/{course['id']}/assignments/{a['id']}/work"
    client.post(f"{base}/draft", headers=course["student"], json={"text": "x"})
    client.post(f"{base}/turn-in", headers=course["student"])
    url = f"{base}/students/{course['student_id']}/grade"
    crit = rubric["criteria"]
    assert client.put(url, headers=course["teacher"], json={"score": 7}).status_code == 422
    assert client.put(url, headers=course["teacher"], json={"levels": {str(crit[0]["id"]): crit[0]["levels"][0]["id"]}}).status_code == 422
    wrong = {str(crit[0]["id"]): crit[1]["levels"][0]["id"], str(crit[1]["id"]): crit[1]["levels"][0]["id"]}
    assert client.put(url, headers=course["teacher"], json={"levels": wrong}).status_code == 422


def test_levels_are_refused_on_work_that_has_no_rubric(client, course):
    a = work(client, course, "Plain", 10)
    base = f"{API}/courses/{course['id']}/assignments/{a['id']}/work"
    client.post(f"{base}/draft", headers=course["student"], json={"text": "x"})
    client.post(f"{base}/turn-in", headers=course["student"])
    assert client.put(f"{base}/students/{course['student_id']}/grade", headers=course["teacher"],
                      json={"levels": {"1": 1}}).status_code == 422


def test_a_rubric_must_match_the_points_and_belong_to_the_course(client, course):
    rubric = make_rubric(client, course)
    body = {"title": "Essay", "due_at": when(3), "work": {"instructions": "i", "points": 12, "rubric_id": rubric["id"]}}
    assert client.post(f"{API}/courses/{course['id']}/assignments", headers=course["teacher"], json=body).status_code == 422
    elsewhere = client.post(f"{API}/courses", headers=course["teacher"], json={"title": "Else"}).json()
    foreign = client.post(f"{API}/courses/{elsewhere['id']}/rubrics", headers=course["teacher"], json=RUBRIC).json()
    body["work"].update(points=10, rubric_id=foreign["id"])
    assert client.post(f"{API}/courses/{course['id']}/assignments", headers=course["teacher"], json=body).status_code == 422


def test_a_rubric_in_use_cannot_be_deleted_and_one_used_for_grading_cannot_change(client, course):
    rubric, a = graded_with_rubric(client, course)
    url = f"{API}/courses/{course['id']}/rubrics/{rubric['id']}"
    assert client.delete(url, headers=course["teacher"]).status_code == 409  # attached to an assignment
    smaller = {"title": "Smaller", "criteria": [{"title": "Only", "levels": [{"label": "a", "points": 0}, {"label": "b", "points": 5}]}]}
    assert client.put(url, headers=course["teacher"], json=smaller).status_code == 409  # would change the top score
    same_top = {**RUBRIC, "title": "Renamed"}
    assert client.put(url, headers=course["teacher"], json=same_top).json()["title"] == "Renamed"
    base = f"{API}/courses/{course['id']}/assignments/{a['id']}/work"
    client.post(f"{base}/draft", headers=course["student"], json={"text": "x"})
    client.post(f"{base}/turn-in", headers=course["student"])
    fresh = client.get(url.replace(f"/rubrics/{rubric['id']}", "/rubrics"), headers=course["teacher"]).json()[0]
    pick = {str(c["id"]): c["levels"][0]["id"] for c in fresh["criteria"]}
    client.put(f"{base}/students/{course['student_id']}/grade", headers=course["teacher"], json={"levels": pick})
    assert client.put(url, headers=course["teacher"], json=same_top).status_code == 409  # graded with it now
    spare = make_rubric(client, course)
    assert client.delete(f"{API}/courses/{course['id']}/rubrics/{spare['id']}", headers=course["teacher"]).status_code == 204
