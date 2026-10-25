"""F-73, F-74, F-75, F-76, F-77: handed-in work is checked by content, graded by hand, hidden until returned, counted in
the gradebook by the late rule, audited, and private to the student and their instructor."""
import base64
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from tests.helpers import enroll

API = "/api/v1"


def iso(delta_days: float) -> str:
    return (datetime.now(UTC) + timedelta(days=delta_days)).isoformat()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


@pytest.fixture
def course(client, make_user):
    teacher_id, teacher = make_user("instructor")
    made = client.post(f"{API}/courses", headers=teacher, json={"title": f"Work {uuid.uuid4().hex[:6]}"}).json()
    student_id, student = make_user("student")
    assert enroll(client, made['id'], student).status_code == 200
    return {"id": made["id"], "teacher": teacher, "teacher_id": teacher_id, "student": student, "student_id": student_id}


def make_assignment(client, course, due=2, points=10, **work):
    body = {"title": "Essay", "confirm_past_due": True, "due_at": iso(due),
            "work": {"instructions": "Write about loops.", "points": points, **work}}
    made = client.post(f"{API}/courses/{course['id']}/assignments", headers=course["teacher"], json=body)
    assert made.status_code == 201, made.text
    return made.json()


def path(course, assignment, tail=""):
    return f"{API}/courses/{course['id']}/assignments/{assignment['id']}/work{tail}"


def draft(client, course, assignment, headers=None, **body):
    return client.post(path(course, assignment, "/draft"), headers=headers or course["student"], json=body)


def turn_in(client, course, assignment, headers=None):
    return client.post(path(course, assignment, "/turn-in"), headers=headers or course["student"])


def hand_in(client, course, assignment, text_="my essay"):
    assert draft(client, course, assignment, text=text_).status_code == 200
    done = turn_in(client, course, assignment)
    assert done.status_code == 200, done.text
    return done.json()


def grade(client, course, assignment, score=6, feedback="Good start", headers=None):
    return client.put(path(course, assignment, f"/students/{course['student_id']}/grade"),
                      headers=headers or course["teacher"], json={"score": score, "feedback": feedback})


def give_back(client, course, assignment):
    return client.post(path(course, assignment, f"/students/{course['student_id']}/return"), headers=course["teacher"])


def my_row(client, course, assignment):
    listed = client.get(f"{API}/courses/{course['id']}/assignments", headers=course["student"]).json()
    return next(a["mine"] for a in listed if a["id"] == assignment["id"])


def audit_events(owner, user_id, event):
    with owner.connect() as conn:
        return conn.execute(
            text("SELECT detail FROM audit_events WHERE user_id = :u AND event = :e ORDER BY id"),
            {"u": user_id, "e": event},
        ).scalars().all()


def test_an_assignment_can_ask_for_work_alone_and_needs_something_to_ask_for(client, course):
    made = make_assignment(client, course, points=8)
    assert made["possible"] == 8 and made["problems"] == [] and made["work"]["instructions"] == "Write about loops."
    nothing = client.post(f"{API}/courses/{course['id']}/assignments", headers=course["teacher"],
                          json={"title": "Empty", "due_at": iso(1)})
    assert nothing.status_code == 422
    none_allowed = client.post(f"{API}/courses/{course['id']}/assignments", headers=course["teacher"], json={
        "title": "x", "due_at": iso(1), "work": {"instructions": "i", "points": 1, "allow_file": False,
                                                 "allow_link": False, "allow_text": False}})
    assert none_allowed.status_code == 422


def test_a_student_saves_a_draft_turns_in_and_can_unsubmit_until_it_is_graded(client, course):
    a = make_assignment(client, course)
    assert client.get(path(course, a), headers=course["student"]).json()["state"] == "assigned"
    assert turn_in(client, course, a).status_code == 422  # nothing to turn in yet
    saved = draft(client, course, a, text="first", link="https://example.org/essay").json()
    assert saved["state"] == "assigned" and saved["text"] == "first" and saved["link"] == "https://example.org/essay"
    done = turn_in(client, course, a).json()
    assert done["state"] == "turned_in" and done["turned_in_at"] and done["late"] is False
    assert draft(client, course, a, text="changed").status_code == 409  # unsubmit first
    assert turn_in(client, course, a).status_code == 409
    back = client.post(path(course, a, "/unsubmit"), headers=course["student"]).json()
    assert back["state"] == "assigned" and back["turned_in_at"] is None
    assert draft(client, course, a, text="second").json()["text"] == "second"
    assert turn_in(client, course, a).status_code == 200
    assert grade(client, course, a).status_code == 200
    assert client.post(path(course, a, "/unsubmit"), headers=course["student"]).status_code == 409


def test_a_missing_state_appears_once_the_due_time_has_passed(client, course):
    a = make_assignment(client, course, due=-1)
    assert client.get(path(course, a), headers=course["student"]).json()["state"] == "missing"
    done = hand_in(client, course, a)
    assert done["state"] == "turned_in" and done["late"] is True


def test_only_the_kinds_the_assignment_accepts_can_be_handed_in(client, course):
    a = make_assignment(client, course, allow_file=False, allow_link=False)
    assert draft(client, course, a, link="https://example.org").status_code == 422
    assert draft(client, course, a, file_base64=b64(b"%PDF-1.4 x"), file_name="a.pdf").status_code == 422
    assert draft(client, course, a, text="fine").status_code == 200


@pytest.mark.parametrize(
    "name, data",
    [
        ("fake.pdf", b"not a pdf at all"),
        ("tool.exe", b"MZ\x90\x00"),
        ("notes.txt", b"has a \x00 null"),
        ("bad.py", b"\xff\xfe\x00bad utf8"),
        ("empty.zip", b"not a zip"),
        ("huge.txt", b"a" * 4_600_000),
        ("blank.txt", b"   \n"),
    ],
)
def test_files_are_checked_by_content_not_by_name(client, course, name, data):
    a = make_assignment(client, course)
    assert draft(client, course, a, file_base64=b64(data), file_name=name).status_code == 422
    assert draft(client, course, a, file_base64="!!not base64!!", file_name="a.pdf").status_code == 422


def test_a_good_file_is_stored_cleaned_and_only_served_as_a_download(client, course):
    a = make_assignment(client, course)
    zipped = b"PK\x03\x04" + b"\x00" * 20
    saved = draft(client, course, a, file_base64=b64(zipped), file_name="../../my work (final)!.zip").json()
    assert saved["file_name"] == "my work _final__.zip" and saved["file_size"] == len(zipped)
    for who, url in ((course["student"], path(course, a, "/file")),
                     (course["teacher"], path(course, a, f"/students/{course['student_id']}/file"))):
        got = client.get(url, headers=who)
        assert got.status_code == 200 and got.content == zipped
        assert got.headers["content-type"] == "application/octet-stream"
        assert got.headers["content-disposition"].startswith("attachment;")
        assert got.headers["x-content-type-options"] == "nosniff"
    assert draft(client, course, a, text="kept", remove_file=True).json()["file_name"] is None
    assert client.get(path(course, a, "/file"), headers=course["student"]).status_code == 404
    py = draft(client, course, a, file_base64=b64(b"print('hi')\n"), file_name="solution.py").json()
    assert py["file_name"] == "solution.py"


def test_a_score_and_feedback_stay_hidden_until_the_work_is_returned(client, course):
    a = make_assignment(client, course)
    hand_in(client, course, a)
    graded = grade(client, course, a, score=6, feedback="Needs examples").json()
    assert graded["state"] == "graded" and graded["score"] == 6 and graded["feedback"] == "Needs examples"
    seen = client.get(path(course, a), headers=course["student"]).json()
    assert seen["state"] == "turned_in" and seen["score"] is None and seen["feedback"] is None
    assert "Needs examples" not in client.get(path(course, a), headers=course["student"]).text
    assert give_back(client, course, a).json()["state"] == "returned"
    seen = client.get(path(course, a), headers=course["student"]).json()
    assert (seen["state"], seen["score"], seen["feedback"]) == ("returned", 6, "Needs examples")
    # a regrade after the return is shown at once
    assert grade(client, course, a, score=9, feedback="Better").status_code == 200
    assert client.get(path(course, a), headers=course["student"]).json()["score"] == 9


def test_grading_follows_the_rules_of_the_work(client, course):
    a = make_assignment(client, course, points=10)
    assert grade(client, course, a).status_code == 409  # nothing turned in
    assert give_back(client, course, a).status_code == 409
    hand_in(client, course, a)
    assert give_back(client, course, a).status_code == 409  # not graded yet
    assert grade(client, course, a, score=10.5).status_code == 422
    assert grade(client, course, a, score=-1).status_code == 422
    assert grade(client, course, a, score=10).status_code == 200


def test_returned_scores_reach_the_gradebook_by_the_late_rule(client, course):
    a = make_assignment(client, course, points=10)
    assert (my_row(client, course, a)["score"], my_row(client, course, a)["status"]) == (0, "not_started")
    hand_in(client, course, a)
    assert (my_row(client, course, a)["score"], my_row(client, course, a)["status"]) == (0, "in_progress")
    grade(client, course, a, score=6)
    assert my_row(client, course, a)["score"] == 0  # graded, not yet returned
    give_back(client, course, a)
    row = my_row(client, course, a)
    assert (row["score"], row["possible"], row["status"]) == (6, 10, "in_progress")
    book = client.get(f"{API}/courses/{course['id']}/gradebook", headers=course["teacher"]).json()
    assert book["possible"] == 10 and book["students"][0]["total"] == 6
    grade(client, course, a, score=10)
    assert my_row(client, course, a)["status"] == "complete"
    # the same work handed in after the due time counts only in with_late
    late = make_assignment(client, course, due=-1, points=10)
    hand_in(client, course, late)
    grade(client, course, late, score=7)
    give_back(client, course, late)
    row = my_row(client, course, late)
    assert (row["score"], row["with_late"], row["status"]) == (0, 7, "late")


def test_only_the_courses_own_people_can_read_or_grade_the_work(client, make_user, course):
    a = make_assignment(client, course)
    hand_in(client, course, a)
    _, other_student = make_user("student")
    _, other_teacher = make_user("instructor")
    _, admin = make_user("admin")
    student_url = path(course, a, f"/students/{course['student_id']}")
    assert client.get(path(course, a), headers=other_student).status_code == 403  # not enrolled
    assert client.get(student_url, headers=other_teacher).status_code == 403
    assert client.get(student_url, headers=course["student"]).status_code == 403
    assert client.get(student_url, headers=admin).status_code == 403
    assert client.get(student_url).status_code == 401
    assert grade(client, course, a, headers=other_teacher).status_code == 403
    assert grade(client, course, a, headers=course["student"]).status_code == 403
    assert client.get(path(course, a, "/submissions"), headers=other_teacher).status_code == 403
    assert client.get(path(course, a, f"/students/{course['student_id']}/file"), headers=other_teacher).status_code == 403
    teacher_only = client.get(path(course, a), headers=course["teacher"])
    assert teacher_only.status_code == 403  # the hand-in page is for students
    elsewhere = client.post(f"{API}/courses", headers=course["teacher"], json={"title": "Elsewhere"}).json()
    assert client.get(f"{API}/courses/{elsewhere['id']}/assignments/{a['id']}/work",
                      headers=course["student"]).status_code == 403


def test_the_teacher_sees_every_enrolled_student_with_a_state(client, make_user, course):
    a = make_assignment(client, course)
    other_id, other = make_user("student")
    enroll(client, course['id'], other)
    hand_in(client, course, a)
    listed = client.get(path(course, a, "/submissions"), headers=course["teacher"]).json()
    states = {r["student_id"]: r["state"] for r in listed["rows"]}
    assert states == {course["student_id"]: "turned_in", other_id: "assigned"}
    grade(client, course, a)
    give_back(client, course, a)
    listed = client.get(path(course, a, "/submissions"), headers=course["teacher"]).json()
    assert {r["student_id"]: r["state"] for r in listed["rows"]}[course["student_id"]] == "returned"


def test_viewing_grading_and_returning_are_audited_without_the_text(client, owner, course):
    a = make_assignment(client, course)
    hand_in(client, course, a, text_="secret essay words")
    client.get(path(course, a, f"/students/{course['student_id']}"), headers=course["teacher"])
    grade(client, course, a, score=5, feedback="private feedback words")
    give_back(client, course, a)
    me = course["teacher_id"]
    assert audit_events(owner, me, "work.viewed")[0]["student_id"] == course["student_id"]
    assert audit_events(owner, me, "work.graded")[0]["score"] == 5
    assert audit_events(owner, me, "work.returned")
    everything = str(audit_events(owner, me, "work.viewed") + audit_events(owner, me, "work.graded"))
    assert "secret essay words" not in everything and "private feedback words" not in everything


def test_private_comments_are_visible_only_to_the_student_and_their_instructor(client, make_user, course):
    a = make_assignment(client, course)
    sent = client.post(path(course, a, "/comments"), headers=course["student"], json={"body": "Can I use a link?"})
    assert sent.status_code == 201 and sent.json()["comments"][0]["mine"] is True
    reply = client.post(path(course, a, f"/students/{course['student_id']}/comments"), headers=course["teacher"],
                        json={"body": "Yes, any link is fine."})
    assert reply.status_code == 201
    mine = client.get(path(course, a), headers=course["student"]).json()["comments"]
    assert [(c["from_teacher"], c["mine"]) for c in mine] == [(False, True), (True, False)]
    theirs = client.get(path(course, a, f"/students/{course['student_id']}"), headers=course["teacher"]).json()
    assert [(c["from_teacher"], c["mine"]) for c in theirs["comments"]] == [(False, False), (True, True)]
    _, other_student = make_user("student")
    enroll(client, course['id'], other_student)
    assert client.get(path(course, a), headers=other_student).json()["comments"] == []
    assert "Can I use a link" not in client.get(path(course, a), headers=other_student).text
    assert client.post(path(course, a, "/comments"), headers=course["student"], json={"body": "  "}).status_code == 422


def test_the_to_review_queue_counts_work_across_the_instructors_own_courses_only(client, make_user, course):
    a = make_assignment(client, course)
    _, other_teacher = make_user("instructor")
    assert client.get(f"{API}/instructor/to-review", headers=other_teacher).json() == []
    assert client.get(f"{API}/instructor/to-review", headers=course["student"]).status_code == 403
    hand_in(client, course, a)

    def mine():
        return next(g for g in client.get(f"{API}/instructor/to-review", headers=course["teacher"]).json()
                    if g["assignment_id"] == a["id"])

    assert (mine()["waiting"], mine()["graded"], mine()["not_returned"]) == (1, 0, 0)
    grade(client, course, a)
    assert (mine()["waiting"], mine()["graded"], mine()["not_returned"]) == (0, 1, 1)
    returned = client.post(path(course, a, "/return-all"), headers=course["teacher"])
    assert returned.json() == {"count": 1}
    assert (mine()["waiting"], mine()["graded"], mine()["not_returned"]) == (0, 1, 0)
    assert client.post(path(course, a, "/return-all"), headers=course["teacher"]).json() == {"count": 0}


def test_work_that_students_have_handed_in_cannot_be_deleted_or_cut_below_a_given_score(client, course):
    a = make_assignment(client, course, points=10)
    url = f"{API}/courses/{course['id']}/assignments/{a['id']}"
    hand_in(client, course, a)
    grade(client, course, a, score=8)
    smaller = {"title": "Essay", "due_at": iso(2), "work": {"instructions": "x", "points": 5}}
    assert client.put(url, headers=course["teacher"], json=smaller).status_code == 409
    removed = {"title": "Essay", "due_at": iso(2), "problems": [], "quizzes": [],
               "work": None}
    assert client.put(url, headers=course["teacher"], json=removed).status_code == 422  # nothing left to ask for
    bigger = {"title": "Essay 2", "due_at": iso(2), "work": {"instructions": "x", "points": 20}}
    assert client.put(url, headers=course["teacher"], json=bigger).status_code == 200
    assert client.delete(url, headers=course["teacher"]).status_code == 409


def test_an_assignment_nobody_worked_on_can_still_be_deleted(client, course):
    a = make_assignment(client, course)
    assert client.delete(f"{API}/courses/{course['id']}/assignments/{a['id']}", headers=course["teacher"]).status_code == 204
