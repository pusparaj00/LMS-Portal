"""F-71, F-72, F-75: quizzes are graded on the server, hide their answers from students, respect the attempt limit and
the late rule, and count in the gradebook."""
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from tests.helpers import enroll

API = "/api/v1"


def iso(delta_days: float) -> str:
    return (datetime.now(UTC) + timedelta(days=delta_days)).isoformat()


def questions():
    return [
        {"kind": "single", "prompt": "Which keyword starts a loop over items?", "options": ["for", "if", "def"],
         "correct_choices": [0], "weight": 1},
        {"kind": "multiple", "prompt": "Which of these are loop keywords?", "options": ["for", "while", "else", "try"],
         "correct_choices": [0, 1], "weight": 2},
        {"kind": "short", "prompt": "Name the function that gives the length of a list.", "accepted": ["len", "len()"],
         "weight": 1},
    ]


def quiz_body(**changes):
    return {"title": "Loops quiz", "max_attempts": 2, "show_answers": False, "published": True,
            "questions": questions(), **changes}


@pytest.fixture
def course(client, make_user):
    _, teacher = make_user("instructor")
    made = client.post(f"{API}/courses", headers=teacher, json={"title": f"Quizzes {uuid.uuid4().hex[:6]}"}).json()
    _, student = make_user("student")
    assert enroll(client, made['id'], student).status_code == 200
    return {"id": made["id"], "teacher": teacher, "student": student}


def make_quiz(client, course, **changes):
    made = client.post(f"{API}/courses/{course['id']}/quizzes", headers=course["teacher"], json=quiz_body(**changes))
    assert made.status_code == 201, made.text
    return made.json()


def answers_for(quiz, right=(True, True, True)):
    """Answers built from the staff view: each question right or wrong as asked."""
    given = []
    for q, ok in zip(quiz["question_list"], right, strict=False):
        if q["kind"] == "short":
            given.append({"question_id": q["id"], "text": "  LEN " if ok else "size"})
        else:
            wrong = [i for i in range(len(q["options"])) if i not in q["correct_choices"]][:1]
            given.append({"question_id": q["id"], "choices": q["correct_choices"] if ok else wrong})
    return {"answers": given}


def attempt(client, course, quiz_id, body, headers=None):
    return client.post(f"{API}/courses/{course['id']}/quizzes/{quiz_id}/attempts", headers=headers or course["student"],
                       json=body)


def test_a_student_never_receives_the_right_answers_with_the_questions(client, course):
    quiz = make_quiz(client, course)
    assert quiz["question_list"][0]["correct_choices"] == [0]
    seen = client.get(f"{API}/courses/{course['id']}/quizzes/{quiz['id']}", headers=course["student"])
    assert seen.status_code == 200
    for q in seen.json()["question_list"]:
        assert q["correct_choices"] is None and q["accepted"] is None
    assert "len()" not in seen.text


def test_a_student_sees_only_published_quizzes_and_cannot_open_a_draft(client, course):
    draft = make_quiz(client, course, title="Draft", published=False)
    live = make_quiz(client, course, title="Live")
    listed = client.get(f"{API}/courses/{course['id']}/quizzes", headers=course["student"]).json()
    assert [q["id"] for q in listed] == [live["id"]]
    assert client.get(f"{API}/courses/{course['id']}/quizzes/{draft['id']}", headers=course["student"]).status_code == 404
    assert attempt(client, course, draft["id"], answers_for(draft)).status_code == 404
    both = client.get(f"{API}/courses/{course['id']}/quizzes", headers=course["teacher"]).json()
    assert {q["id"] for q in both} == {draft["id"], live["id"]}


def test_grading_is_all_or_nothing_per_question_and_weighted(client, course):
    cases = [((True, True, True), 4, 4), ((True, True, False), 3, 4), ((False, True, True), 3, 4),
             ((True, False, True), 2, 4), ((False, False, False), 0, 4)]
    for n, (right, earned, possible) in enumerate(cases):
        fresh = make_quiz(client, course, max_attempts=1)
        out = attempt(client, course, fresh["id"], answers_for(fresh, right))
        assert out.status_code == 201, out.text
        body = out.json()
        assert (body["earned"], body["possible"], body["fraction"]) == (earned, possible, earned / possible), n


def test_a_partly_right_multiple_choice_answer_earns_nothing(client, course):
    quiz = make_quiz(client, course, max_attempts=3)
    q = quiz["question_list"][1]
    body = {"answers": [{"question_id": q["id"], "choices": [0]}]}
    assert attempt(client, course, quiz["id"], body).json()["earned"] == 0
    body = {"answers": [{"question_id": q["id"], "choices": [0, 1, 2]}]}
    assert attempt(client, course, quiz["id"], body).json()["earned"] == 0
    body = {"answers": [{"question_id": q["id"], "choices": [1, 0]}]}
    assert attempt(client, course, quiz["id"], body).json()["earned"] == 2


def test_the_attempt_limit_is_enforced_and_counted_down(client, course):
    quiz = make_quiz(client, course, max_attempts=2)
    first = attempt(client, course, quiz["id"], answers_for(quiz, (False, False, False))).json()
    assert (first["attempt_number"], first["attempts_left"]) == (1, 1)
    second = attempt(client, course, quiz["id"], answers_for(quiz)).json()
    assert (second["attempt_number"], second["attempts_left"]) == (2, 0)
    refused = attempt(client, course, quiz["id"], answers_for(quiz))
    assert refused.status_code == 409
    mine = client.get(f"{API}/courses/{course['id']}/quizzes/{quiz['id']}/attempts/mine", headers=course["student"]).json()
    assert [a["fraction"] for a in mine["attempts"]] == [0, 1] and mine["attempts_left"] == 0
    listed = client.get(f"{API}/courses/{course['id']}/quizzes", headers=course["student"]).json()[0]
    assert (listed["attempts_used"], listed["best_fraction"]) == (2, 1)


def test_answers_naming_a_foreign_or_repeated_question_are_refused(client, course):
    quiz = make_quiz(client, course)
    other = make_quiz(client, course, title="Other")
    foreign = {"answers": [{"question_id": other["question_list"][0]["id"], "choices": [0]}]}
    assert attempt(client, course, quiz["id"], foreign).status_code == 422
    q = quiz["question_list"][0]["id"]
    twice = {"answers": [{"question_id": q, "choices": [0]}, {"question_id": q, "choices": [1]}]}
    assert attempt(client, course, quiz["id"], twice).status_code == 422


def test_review_is_off_by_default_and_waits_for_every_assignment_to_close(client, course):
    c = course
    plain = make_quiz(client, c)
    assert attempt(client, c, plain["id"], answers_for(plain)).json()["review"] is None
    reviewable = make_quiz(client, c, show_answers=True, max_attempts=5)
    out = attempt(client, c, reviewable["id"], answers_for(reviewable, (True, False, True))).json()
    assert [r["correct"] for r in out["review"]] == [True, False, True]
    assert out["review"][0]["correct_choices"] == [0] and out["review"][2]["accepted"] == ["len", "len()"]
    made = client.post(f"{API}/courses/{c['id']}/assignments", headers=c["teacher"], json={
        "title": "Open", "due_at": iso(2), "quizzes": [{"quiz_id": reviewable["id"], "points": 4}]})
    assert made.status_code == 201, made.text
    assert attempt(client, c, reviewable["id"], answers_for(reviewable)).json()["review"] is None
    mine = f"{API}/courses/{c['id']}/quizzes/{reviewable['id']}/attempts/mine"
    assert client.get(mine, headers=c["student"]).json()["review"] is None
    client.put(f"{API}/courses/{c['id']}/assignments/{made.json()['id']}", headers=c["teacher"], json={
        "title": "Closed", "confirm_past_due": True, "due_at": iso(-1), "quizzes": [{"quiz_id": reviewable["id"], "points": 4}]})
    assert client.get(mine, headers=c["student"]).json()["review"] is not None


def test_the_questions_lock_once_a_student_has_attempted_but_settings_do_not(client, course):
    quiz = make_quiz(client, course)
    path = f"{API}/courses/{course['id']}/quizzes/{quiz['id']}"
    changed = quiz_body(questions=questions()[:2])
    assert client.put(path, headers=course["teacher"], json=changed).status_code == 200  # nobody attempted yet
    attempt(client, course, quiz["id"], answers_for(client.get(path, headers=course["teacher"]).json()))
    assert client.put(path, headers=course["teacher"], json=quiz_body(questions=questions()[:1])).status_code == 409
    renamed = client.put(path, headers=course["teacher"], json=quiz_body(title="Renamed", questions=questions()[:2]))
    assert renamed.status_code == 200 and renamed.json()["title"] == "Renamed"


def test_a_quiz_in_an_assignment_or_with_attempts_cannot_be_deleted(client, course):
    c = course
    quiz = make_quiz(client, c)
    path = f"{API}/courses/{c['id']}/quizzes/{quiz['id']}"
    made = client.post(f"{API}/courses/{c['id']}/assignments", headers=c["teacher"], json={
        "title": "A", "due_at": iso(3), "quizzes": [{"quiz_id": quiz["id"], "points": 2}]}).json()
    assert client.delete(path, headers=c["teacher"]).status_code == 409
    client.delete(f"{API}/courses/{c['id']}/assignments/{made['id']}", headers=c["teacher"])
    attempt(client, c, quiz["id"], answers_for(quiz))
    assert client.delete(path, headers=c["teacher"]).status_code == 409
    spare = make_quiz(client, c, title="Spare")
    assert client.delete(f"{API}/courses/{c['id']}/quizzes/{spare['id']}", headers=c["teacher"]).status_code == 204


def test_only_the_courses_own_people_can_use_its_quizzes(client, make_user, course):
    quiz = make_quiz(client, course)
    path = f"{API}/courses/{course['id']}/quizzes"
    _, outsider = make_user("student")
    _, other_teacher = make_user("instructor")
    assert client.get(path, headers=outsider).status_code == 403
    assert attempt(client, course, quiz["id"], answers_for(quiz), headers=outsider).status_code == 403
    assert client.get(f"{path}/{quiz['id']}", headers=other_teacher).status_code == 403
    assert client.post(path, headers=other_teacher, json=quiz_body()).status_code == 403
    assert client.post(path, headers=course["student"], json=quiz_body()).status_code == 403
    assert client.put(f"{path}/{quiz['id']}", headers=course["student"], json=quiz_body()).status_code == 403
    assert client.delete(f"{path}/{quiz['id']}", headers=course["student"]).status_code == 403
    assert client.get(path).status_code == 401
    assert attempt(client, course, quiz["id"], answers_for(quiz), headers=course["teacher"]).status_code == 403


@pytest.mark.parametrize(
    "bad",
    [
        {"kind": "single", "prompt": "q", "options": ["a", "b"], "correct_choices": [0, 1]},
        {"kind": "single", "prompt": "q", "options": ["a", "b"], "correct_choices": [2]},
        {"kind": "single", "prompt": "q", "options": ["a"], "correct_choices": [0]},
        {"kind": "multiple", "prompt": "q", "options": ["a", "a"], "correct_choices": [0]},
        {"kind": "multiple", "prompt": "q", "options": ["a", "b"], "correct_choices": []},
        {"kind": "short", "prompt": "q", "accepted": []},
        {"kind": "short", "prompt": "q", "accepted": ["  "]},
        {"kind": "short", "prompt": "q", "accepted": ["x"], "options": ["a", "b"]},
        {"kind": "single", "prompt": "q", "options": ["a", "b"], "correct_choices": [0], "accepted": ["x"]},
        {"kind": "single", "prompt": "  ", "options": ["a", "b"], "correct_choices": [0]},
    ],
)
def test_a_malformed_question_is_refused(client, course, bad):
    sent = client.post(f"{API}/courses/{course['id']}/quizzes", headers=course["teacher"],
                       json=quiz_body(questions=[bad]))
    assert sent.status_code == 422, sent.text


def test_quiz_points_reach_the_gradebook_by_the_late_rule(client, make_user, course):
    c = course
    quiz = make_quiz(client, c, max_attempts=3)
    half = answers_for(quiz, (True, False, False))  # 1 of 4 points
    assignment = {"title": "Quiz week", "due_at": iso(2), "quizzes": [{"quiz_id": quiz["id"], "points": 8}]}
    made = client.post(f"{API}/courses/{c['id']}/assignments", headers=c["teacher"], json=assignment).json()
    assert made["possible"] == 8 and made["quizzes"][0]["title"] == "Loops quiz"

    def mine():
        listed = client.get(f"{API}/courses/{c['id']}/assignments", headers=c["student"]).json()
        return next(a["mine"] for a in listed if a["id"] == made["id"])

    assert (mine()["score"], mine()["status"]) == (0, "not_started")
    attempt(client, c, quiz["id"], half)
    assert (mine()["score"], mine()["possible"], mine()["status"]) == (2.0, 8, "in_progress")  # 8 * 1/4
    attempt(client, c, quiz["id"], answers_for(quiz))
    assert (mine()["score"], mine()["status"]) == (8.0, "complete")

    book = client.get(f"{API}/courses/{c['id']}/gradebook", headers=c["teacher"]).json()
    assert book["possible"] == 8 and book["students"][0]["total"] == 8.0

    late = {**assignment, "title": "Quiz late", "confirm_past_due": True, "due_at": iso(-1)}
    made_late = client.post(f"{API}/courses/{c['id']}/assignments", headers=c["teacher"], json=late).json()
    listed = client.get(f"{API}/courses/{c['id']}/assignments", headers=c["student"]).json()
    row = next(a["mine"] for a in listed if a["id"] == made_late["id"])
    assert (row["score"], row["with_late"], row["status"]) == (0, 8.0, "late")  # attempts were after this due time


def test_an_assignment_can_mix_problems_and_quizzes_and_must_hold_something(client, course):
    c = course
    quiz = make_quiz(client, c)
    path = f"{API}/courses/{c['id']}/assignments"
    assert client.post(path, headers=c["teacher"], json={"title": "Empty", "due_at": iso(1)}).status_code == 422
    other = client.post(f"{API}/courses", headers=c["teacher"], json={"title": "Elsewhere"}).json()
    foreign = client.post(f"{API}/courses/{other['id']}/quizzes", headers=c["teacher"], json=quiz_body()).json()
    refused = client.post(path, headers=c["teacher"], json={
        "title": "Foreign", "due_at": iso(1), "quizzes": [{"quiz_id": foreign["id"], "points": 1}]})
    assert refused.status_code == 422
    twice = client.post(path, headers=c["teacher"], json={
        "title": "Twice", "due_at": iso(1), "quizzes": [{"quiz_id": quiz["id"]}, {"quiz_id": quiz["id"]}]})
    assert twice.status_code == 422
    ok = client.post(path, headers=c["teacher"], json={"title": "Fine", "due_at": iso(1),
                                                       "quizzes": [{"quiz_id": quiz["id"], "points": 3}]})
    assert ok.status_code == 201 and ok.json()["problems"] == [] and ok.json()["possible"] == 3


def test_an_assignment_tells_students_when_its_quiz_is_not_open_yet(client, course):
    draft = make_quiz(client, course, published=False)
    client.post(f"{API}/courses/{course['id']}/assignments", headers=course["teacher"], json={
        "title": "Soon", "due_at": iso(3), "quizzes": [{"quiz_id": draft["id"], "points": 2}]})
    listed = client.get(f"{API}/courses/{course['id']}/assignments", headers=course["student"]).json()
    assert [q["published"] for q in listed[0]["quizzes"]] == [False]
