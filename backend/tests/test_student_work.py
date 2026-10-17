"""F-61, F-34, TR-S-02, TR-S-08: the course's teacher sees one student's mastery, its history, and their submitted code;
nobody else does, hidden test inputs never show, and every view of code is audited."""
from sqlalchemy import text

from tests.conftest import HIDDEN_INPUT

API = "/api/v1"
VISIBLE_ONLY = "print({'1': 2, '41': 42}.get(input(), 0))\n"  # right on the two examples, wrong on the two hidden tests


def enrolled(client, make_user, course):
    student_id, headers = make_user("student")
    assert client.post(f"{API}/courses/{course['id']}/enroll", headers=headers).status_code == 204
    return student_id, headers


def submit(client, headers, course, code=VISIBLE_ONLY):
    response = client.post(f"{API}/submissions", headers=headers, json={"problem_id": course["problem_id"], "code": code})
    assert response.status_code == 200, response.text
    return response.json()["submission_id"]


def work(course, student_id):
    return f"{API}/courses/{course['id']}/students/{student_id}"


def test_the_teacher_sees_the_students_mastery_and_submissions(client, make_user, course):
    student_id, headers = enrolled(client, make_user, course)
    first = submit(client, headers, course)
    second = submit(client, headers, course, code="print(int(input()) + 1)\n")
    body = client.get(work(course, student_id), headers=course["instructor"]).json()
    assert [s["submission_id"] for s in body["submissions"]] == [second, first]  # newest first
    assert [(s["status"], s["passed"], s["failed"]) for s in body["submissions"]] == [("passed", 4, 0), ("failed", 2, 2)]
    assert body["concepts"] and body["student_id"] == student_id and body["label"]


def test_only_the_courses_teacher_sees_a_students_work(client, make_user, course):
    student_id, headers = enrolled(client, make_user, course)
    sid = submit(client, headers, course)
    _, other_teacher = make_user("instructor")
    _, admin = make_user("admin")
    _, classmate = enrolled(client, make_user, course)
    stranger_id, _ = make_user("student")  # not in this course
    for path in (work(course, student_id), f"{work(course, student_id)}/submissions/{sid}"):
        assert client.get(path, headers=other_teacher).status_code == 403
        assert client.get(path, headers=admin).status_code == 403
        assert client.get(path, headers=classmate).status_code == 403
        assert client.get(path).status_code == 401
    assert client.get(work(course, stranger_id), headers=course["instructor"]).status_code == 404
    # a submission of another student cannot be read through this student's address
    other_id, other = enrolled(client, make_user, course)
    theirs = submit(client, other, course)
    assert client.get(f"{work(course, student_id)}/submissions/{theirs}", headers=course["instructor"]).status_code == 404


def test_a_submission_shows_code_and_results_but_never_hidden_inputs_and_is_audited(client, make_user, course, owner):
    student_id, headers = enrolled(client, make_user, course)
    sid = submit(client, headers, course)
    response = client.get(f"{work(course, student_id)}/submissions/{sid}", headers=course["instructor"])
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == VISIBLE_ONLY and body["status"] == "failed"
    assert [(t["input"], t["passed"]) for t in body["visible_tests"]] == [("1\n", True), ("41\n", True)]
    assert body["hidden_failed"] == 2 and sorted(body["failed_categories"]) == ["large_input", "negative_numbers"]
    assert HIDDEN_INPUT not in response.text and "987655" not in response.text and "-5\\n" not in response.text
    assert body["explanation"] == {"requested": False, "attempts": 0, "outcome": None, "from_cache": False, "text": None}
    with owner.connect() as conn:
        event = conn.execute(
            text("SELECT user_id, detail FROM audit_events WHERE event = 'student_work.viewed' ORDER BY id DESC LIMIT 1")
        ).one()
    assert event.user_id == course["instructor_id"]
    assert event.detail == {"course_id": course["id"], "student_id": student_id, "submission_id": sid}


def test_the_explanation_the_student_asked_for_is_recorded(client, make_user, course):
    student_id, headers = enrolled(client, make_user, course)
    sid = submit(client, headers, course)
    shown = client.post(f"{API}/submissions/{sid}/explain", headers=headers).json()  # the stub model: a template
    assert shown["status"] == "fallback"
    record = client.get(f"{work(course, student_id)}/submissions/{sid}", headers=course["instructor"]).json()["explanation"]
    assert record["requested"] is True and record["outcome"] == "template" and record["attempts"] >= 1
    assert record["text"] == shown["fallback_text"]


def test_the_teacher_sees_the_same_why_did_it_change_ledger(client, make_user, course, owner):
    student_id, headers = enrolled(client, make_user, course)
    submit(client, headers, course)
    with owner.connect() as conn:
        concept = conn.execute(text("SELECT id FROM concepts WHERE course_id = :c LIMIT 1"), {"c": course["id"]}).scalar_one()
    own = client.get(f"{API}/students/me/mastery/{concept}/history", headers=headers).json()
    seen = client.get(f"{work(course, student_id)}/mastery/{concept}/history", headers=course["instructor"]).json()
    assert own and seen == own
    assert client.get(f"{work(course, student_id)}/mastery/999999/history", headers=course["instructor"]).status_code == 404


def test_the_privacy_notice_tells_students_what_their_teacher_sees(client, make_user):
    _, headers = make_user("student", consented=False)
    who = " ".join(client.get(f"{API}/consent/notice", headers=headers).json()["sections"][3]["paragraphs"])
    assert "code you submit" in who and "not shown to them" in who


def test_per_test_results_are_not_guessed_after_the_tests_were_changed(client, make_user, course, owner):
    student_id, headers = enrolled(client, make_user, course)
    sid = submit(client, headers, course)
    removed_student, _ = make_user("student")
    with owner.begin() as conn:  # the instructor replaced a test after this submission (Step 19 allows editing)
        conn.execute(text("UPDATE test_cases SET id = id + 100000 WHERE problem_id = :p AND hidden AND input = '-5\n'"),
                     {"p": course["problem_id"]})
    try:
        body = client.get(f"{work(course, student_id)}/submissions/{sid}", headers=course["instructor"]).json()
        assert body["visible_tests"] is None and body["hidden_failed"] is None
        assert (body["passed"], body["failed"]) == (2, 2)  # the stored counts still stand
        assert client.get(work(course, removed_student), headers=course["instructor"]).status_code == 404
    finally:
        with owner.begin() as conn:
            conn.execute(text("UPDATE test_cases SET id = id - 100000 WHERE problem_id = :p AND id > 100000"),
                         {"p": course["problem_id"]})
