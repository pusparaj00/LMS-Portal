"""F-81, F-82, F-83: a course is joined with its class code, people are listed without exposing classmates, co-teachers
teach like the owner, muting stops private comments, and a course carries a section, subject and colour."""
import re
import uuid

import pytest
from sqlalchemy import text

from tests.helpers import join_code

API = "/api/v1"


@pytest.fixture
def course(client, make_user):
    teacher_id, teacher = make_user("instructor")
    made = client.post(f"{API}/courses", headers=teacher, json={"title": f"Access {uuid.uuid4().hex[:6]}"}).json()
    return {"id": made["id"], "title": made["title"], "teacher": teacher, "teacher_id": teacher_id}


def join(client, code, headers):
    return client.post(f"{API}/courses/join", headers=headers, json={"code": code})


def code_of(client, course):
    return client.get(f"{API}/courses/{course['id']}/join-code", headers=course["teacher"]).json()


def test_a_new_course_gets_a_ten_character_code_and_its_owner_teaches_it(client, owner, course):
    shown = code_of(client, course)
    assert re.fullmatch(r"[0-9A-F]{10}", shown["code"]) and shown["enabled"] is True
    assert shown["link"] == f"#/join/{shown['code']}"
    with owner.connect() as conn:
        assert conn.execute(
            text("SELECT user_id FROM course_teachers WHERE course_id = :c"), {"c": course["id"]}
        ).scalars().all() == [course["teacher_id"]]
        made_directly = conn.execute(text("SELECT count(*) FROM courses WHERE join_code IS NULL")).scalar_one()
    assert made_directly == 0


def test_a_student_joins_with_the_code_however_it_is_typed(client, make_user, course):
    code = code_of(client, course)["code"]
    _, student = make_user("student")
    typed = f" {code[:5].lower()}-{code[5:].lower()} "
    joined = join(client, typed, student)
    assert joined.status_code == 200 and joined.json()["id"] == course["id"] and joined.json()["enrolled"] is True
    assert join(client, code, student).status_code == 200  # joining twice changes nothing
    assert course["id"] in {c["id"] for c in client.get(f"{API}/courses", headers=student).json()}


def test_a_wrong_disabled_or_archived_code_all_get_the_same_answer(client, make_user, course):
    _, student = make_user("student")
    code = code_of(client, course)["code"]
    wrong = join(client, "ZZZZZZZZZZ", student)
    client.put(f"{API}/courses/{course['id']}/join-code", headers=course["teacher"], json={"enabled": False})
    disabled = join(client, code, student)
    client.put(f"{API}/courses/{course['id']}/join-code", headers=course["teacher"], json={"enabled": True})
    client.post(f"{API}/courses/{course['id']}/archive", headers=course["teacher"])
    archived = join(client, code, student)
    assert wrong.status_code == disabled.status_code == archived.status_code == 404
    assert {r.json()["error"]["message"] for r in (wrong, disabled, archived)} == {wrong.json()["error"]["message"]}


def test_disabling_the_code_closes_the_class_to_new_students_only(client, make_user, course):
    code = code_of(client, course)["code"]
    _, inside = make_user("student")
    _, outside = make_user("student")
    join(client, code, inside)
    url = f"{API}/courses/{course['id']}/join-code"
    assert client.put(url, headers=course["teacher"], json={"enabled": False}).json()["enabled"] is False
    assert join(client, code, outside).status_code == 404
    assert client.get(f"{API}/courses/{course['id']}/people", headers=inside).status_code == 200
    assert client.put(url, headers=course["teacher"], json={"enabled": True}).json()["enabled"] is True
    assert join(client, code, outside).status_code == 200


def test_resetting_the_code_stops_the_old_one_and_keeps_current_students(client, make_user, course):
    old = code_of(client, course)["code"]
    _, inside = make_user("student")
    _, later = make_user("student")
    join(client, old, inside)
    new = client.post(f"{API}/courses/{course['id']}/join-code/reset", headers=course["teacher"]).json()["code"]
    assert new != old and re.fullmatch(r"[0-9A-F]{10}", new)
    assert join(client, old, later).status_code == 404
    assert join(client, new, later).status_code == 200
    assert client.get(f"{API}/courses/{course['id']}/people", headers=inside).status_code == 200


def test_only_the_courses_teachers_can_see_or_change_the_code(client, make_user, course):
    _, student = make_user("student")
    _, other_teacher = make_user("instructor")
    _, admin = make_user("admin")
    url = f"{API}/courses/{course['id']}/join-code"
    assert client.get(url, headers=student).status_code == 403
    assert client.get(url, headers=other_teacher).status_code == 403
    assert client.get(url, headers=admin).status_code == 200  # read only, for operators
    assert client.post(f"{url}/reset", headers=admin).status_code == 403
    assert client.post(f"{url}/reset", headers=other_teacher).status_code == 403
    assert client.put(url, headers=other_teacher, json={"enabled": False}).status_code == 403
    assert client.get(url).status_code == 401


def test_only_students_join_and_guessing_codes_is_limited(client, make_user, course):
    _, student = make_user("student")
    assert join(client, code_of(client, course)["code"], course["teacher"]).status_code == 403
    for _ in range(10):
        assert join(client, "AAAAAAAAAA", student).status_code == 404
    assert join(client, "AAAAAAAAAA", student).status_code == 429
    assert join(client, code_of(client, course)["code"], student).status_code == 429  # even the right one waits


def test_the_old_open_enrol_route_no_longer_exists(client, make_user, course):
    _, student = make_user("student")
    assert client.post(f"{API}/courses/{course['id']}/enroll", headers=student).status_code in (404, 405)


def test_course_lists_show_each_role_only_its_own_courses(client, make_user, course):
    _, joined = make_user("student")
    _, stranger = make_user("student")
    _, other_teacher = make_user("instructor")
    _, admin = make_user("admin")
    join(client, join_code(course["id"]), joined)
    ids = lambda who: {c["id"] for c in client.get(f"{API}/courses", headers=who).json()}  # noqa: E731
    assert course["id"] in ids(joined) and course["id"] in ids(course["teacher"]) and course["id"] in ids(admin)
    assert course["id"] not in ids(stranger) and course["id"] not in ids(other_teacher)


def test_a_course_has_a_section_subject_and_colour_that_can_be_changed_and_cleared(client, course):
    url = f"{API}/courses/{course['id']}"
    set_ = client.patch(url, headers=course["teacher"], json={"section": "Period 3", "subject": "Python", "color": "#1A73E8"})
    assert set_.status_code == 200
    body = set_.json()
    assert (body["section"], body["subject"], body["color"]) == ("Period 3", "Python", "#1a73e8")
    assert body["title"] == course["title"]  # untouched fields stay
    cleared = client.patch(url, headers=course["teacher"], json={"section": None, "color": None}).json()
    assert (cleared["section"], cleared["subject"], cleared["color"]) == (None, "Python", None)
    assert client.patch(url, headers=course["teacher"], json={"section": "   "}).json()["section"] is None
    listed = next(c for c in client.get(f"{API}/courses", headers=course["teacher"]).json() if c["id"] == course["id"])
    assert listed["subject"] == "Python"


@pytest.mark.parametrize("bad", [{}, {"color": "red"}, {"color": "#12345"}, {"color": "#gggggg"},
                                 {"title": ""}, {"title": None}, {"section": "x" * 101}])
def test_bad_course_details_are_refused(client, course, bad):
    assert client.patch(f"{API}/courses/{course['id']}", headers=course["teacher"], json=bad).status_code == 422


def test_people_shows_a_teacher_every_student_and_a_student_only_the_count(client, make_user, course):
    mine_id, mine = make_user("student")
    other_id, other = make_user("student")
    for who in (mine, other):
        join(client, join_code(course["id"]), who)
    staff = client.get(f"{API}/courses/{course['id']}/people", headers=course["teacher"]).json()
    assert staff["student_count"] == 2 and {s["user_id"] for s in staff["students"]} == {mine_id, other_id}
    assert [t["owner"] for t in staff["teachers"]] == [True]
    seen = client.get(f"{API}/courses/{course['id']}/people", headers=mine)
    body = seen.json()
    assert body["student_count"] == 2 and body["students"] is None and len(body["teachers"]) == 1
    assert str(other_id) not in seen.text.replace(str(course["id"]), "") or "user_id" in seen.text
    assert "student-" not in seen.text  # no classmate's email-derived name
    _, outsider = make_user("student")
    assert client.get(f"{API}/courses/{course['id']}/people", headers=outsider).status_code == 403


def test_the_owner_adds_and_removes_a_co_teacher_who_then_teaches_the_course(client, make_user, owner, course):
    co_id, co = make_user("instructor")
    with owner.connect() as conn:
        email = conn.execute(text("SELECT email FROM users WHERE id = :u"), {"u": co_id}).scalar_one()
    url = f"{API}/courses/{course['id']}"
    assert client.get(f"{url}/gradebook", headers=co).status_code == 403
    added = client.post(f"{url}/teachers", headers=course["teacher"], json={"email": email.upper()})
    assert added.status_code == 201 and [t["owner"] for t in added.json()["teachers"]] == [True, False]
    assert client.post(f"{url}/teachers", headers=course["teacher"], json={"email": email}).status_code == 409
    assert client.get(f"{url}/gradebook", headers=co).status_code == 200
    assert client.get(f"{url}/join-code", headers=co).status_code == 200
    assert client.post(f"{url}/announcements", headers=co, json={"title": "From co", "body": "b"}).status_code == 201
    assert course["id"] in {c["id"] for c in client.get(f"{API}/courses", headers=co).json()}
    assert client.post(f"{url}/archive", headers=co).status_code == 403  # only the owner archives
    assert client.post(f"{url}/teachers", headers=co, json={"email": "x@y.zz"}).status_code == 403
    assert client.delete(f"{url}/teachers/{course['teacher_id']}", headers=course["teacher"]).status_code == 404
    assert client.delete(f"{url}/teachers/{co_id}", headers=course["teacher"]).status_code == 204
    assert client.get(f"{url}/gradebook", headers=co).status_code == 403


def test_only_an_existing_instructor_account_can_be_added_as_a_co_teacher(client, make_user, owner, course):
    student_id, _ = make_user("student")
    with owner.connect() as conn:
        student_email = conn.execute(text("SELECT email FROM users WHERE id = :u"), {"u": student_id}).scalar_one()
    url = f"{API}/courses/{course['id']}/teachers"
    assert client.post(url, headers=course["teacher"], json={"email": student_email}).status_code == 404
    assert client.post(url, headers=course["teacher"], json={"email": "nobody@nowhere.test"}).status_code == 404
    _, other = make_user("instructor")
    assert client.post(url, headers=other, json={"email": student_email}).status_code == 403


def test_a_co_teacher_is_notified_of_handed_in_work_and_can_grade_it(client, make_user, owner, course):
    co_id, co = make_user("instructor")
    with owner.connect() as conn:
        email = conn.execute(text("SELECT email FROM users WHERE id = :u"), {"u": co_id}).scalar_one()
    client.post(f"{API}/courses/{course['id']}/teachers", headers=course["teacher"], json={"email": email})
    student_id, student = make_user("student")
    join(client, join_code(course["id"]), student)
    from datetime import UTC, datetime, timedelta

    due = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    a = client.post(f"{API}/courses/{course['id']}/assignments", headers=course["teacher"], json={
        "title": "Essay", "due_at": due, "work": {"instructions": "Write.", "points": 10}}).json()
    work = f"{API}/courses/{course['id']}/assignments/{a['id']}/work"
    client.post(f"{work}/draft", headers=student, json={"text": "done"})
    client.post(f"{work}/turn-in", headers=student)
    for who in (course["teacher"], co):
        kinds = [i["kind"] for i in client.get(f"{API}/notifications", headers=who).json()["items"]]
        assert "work_turned_in" in kinds
    assert client.put(f"{work}/students/{student_id}/grade", headers=co, json={"score": 7}).status_code == 200
    queue = client.get(f"{API}/instructor/to-review", headers=co).json()
    assert [g["not_returned"] for g in queue if g["assignment_id"] == a["id"]] == [1]


def test_muting_stops_a_students_private_comments_but_not_the_teachers(client, make_user, course):
    from datetime import UTC, datetime, timedelta

    student_id, student = make_user("student")
    join(client, join_code(course["id"]), student)
    due = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    a = client.post(f"{API}/courses/{course['id']}/assignments", headers=course["teacher"], json={
        "title": "Essay", "due_at": due, "work": {"instructions": "Write.", "points": 10}}).json()
    work = f"{API}/courses/{course['id']}/assignments/{a['id']}/work"
    mute = f"{API}/courses/{course['id']}/students/{student_id}/mute"
    assert client.post(f"{work}/comments", headers=student, json={"body": "hello"}).status_code == 201
    muted = client.put(mute, headers=course["teacher"], json={"muted": True}).json()
    assert [s["muted"] for s in muted["students"]] == [True]
    assert client.post(f"{work}/comments", headers=student, json={"body": "again"}).status_code == 403
    assert client.post(f"{work}/students/{student_id}/comments", headers=course["teacher"],
                       json={"body": "reply"}).status_code == 201
    assert len(client.get(work, headers=student).json()["comments"]) == 2  # still readable
    client.put(mute, headers=course["teacher"], json={"muted": False})
    assert client.post(f"{work}/comments", headers=student, json={"body": "back"}).status_code == 201
    _, other_teacher = make_user("instructor")
    assert client.put(mute, headers=other_teacher, json={"muted": True}).status_code == 403
    assert client.put(f"{API}/courses/{course['id']}/students/99999999/mute", headers=course["teacher"],
                      json={"muted": True}).status_code == 404


def test_joining_and_code_changes_are_audited_without_the_code(client, make_user, owner, course):
    student_id, student = make_user("student")
    code = code_of(client, course)["code"]
    join(client, "BBBBBBBBBB", student)
    join(client, code, student)
    new = client.post(f"{API}/courses/{course['id']}/join-code/reset", headers=course["teacher"]).json()["code"]
    with owner.connect() as conn:
        rows = conn.execute(
            text("SELECT event, detail::text FROM audit_events WHERE user_id IN (:s, :t) AND event LIKE 'course.%'"),
            {"s": student_id, "t": course["teacher_id"]},
        ).all()
    events = {r.event for r in rows}
    assert {"course.joined", "course.join_refused", "course.join_code_reset"} <= events
    assert not any(code in r.detail or new in r.detail or "BBBBBBBBBB" in r.detail for r in rows)


def test_asking_an_admin_view_about_a_course_that_does_not_exist_is_a_404_not_a_crash(client, make_user):
    """Regression: the access matrix found a 500 here, because an admin passes the course access check for any id."""
    _, admin = make_user("admin")
    for tail in ("join-code", "people"):
        assert client.get(f"{API}/courses/99999999/{tail}", headers=admin).status_code == 404
