"""F-84, F-85, F-86: draft and scheduled announcements, topics for assignments, and assignments given to chosen
students only."""
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from tests.helpers import enroll

API = "/api/v1"


def when(days: float = 0, hours: float = 0) -> datetime:
    return datetime.now(UTC) + timedelta(days=days, hours=hours)


@pytest.fixture
def course(client, make_user):
    teacher_id, teacher = make_user("instructor")
    made = client.post(f"{API}/courses", headers=teacher, json={"title": f"Page {uuid.uuid4().hex[:6]}"}).json()
    a_id, a = make_user("student")
    b_id, b = make_user("student")
    for who in (a, b):
        assert enroll(client, made["id"], who).status_code == 200
    return {"id": made["id"], "teacher": teacher, "teacher_id": teacher_id, "a": a, "a_id": a_id, "b": b, "b_id": b_id}


def post(client, course, **body):
    body.setdefault("title", "News")
    body.setdefault("body", "Details.")
    return client.post(f"{API}/courses/{course['id']}/announcements", headers=course["teacher"], json=body)


def titles(client, course, who):
    return [x["title"] for x in client.get(f"{API}/courses/{course['id']}/announcements", headers=who).json()]


def inbox_kinds(client, who):
    return [i["kind"] for i in client.get(f"{API}/notifications", headers=who).json()["items"]]


def test_a_draft_is_visible_to_teachers_only_and_notifies_nobody(client, course):
    made = post(client, course, title="Draft one", mode="draft")
    assert made.status_code == 201 and made.json()["state"] == "draft"
    assert titles(client, course, course["teacher"]) == ["Draft one"]
    assert titles(client, course, course["a"]) == []
    assert inbox_kinds(client, course["a"]) == []


def test_a_draft_becomes_a_post_when_it_is_published_and_students_hear_of_it_once(client, course):
    draft = post(client, course, title="Soon", mode="draft").json()
    url = f"{API}/courses/{course['id']}/announcements/{draft['id']}"
    edited = client.put(url, headers=course["teacher"], json={"title": "Soon", "body": "Now live.", "mode": "publish"})
    assert edited.json()["state"] == "published"
    assert titles(client, course, course["a"]) == ["Soon"]
    for _ in range(3):
        assert inbox_kinds(client, course["a"]) == ["announcement"]  # however often anyone looks
    assert inbox_kinds(client, course["b"]) == ["announcement"]
    client.put(url, headers=course["teacher"], json={"title": "Soon", "body": "Edited again.", "mode": "publish"})
    assert inbox_kinds(client, course["a"]) == ["announcement"]  # an edit of a published post is not news


def test_a_scheduled_post_stays_hidden_until_its_time_and_is_then_announced_once(client, owner, course):
    scheduled = post(client, course, title="Later", mode="schedule", publish_at=when(hours=3).isoformat()).json()
    assert scheduled["state"] == "scheduled" and scheduled["publish_at"]
    assert titles(client, course, course["a"]) == [] and inbox_kinds(client, course["a"]) == []
    assert [x["state"] for x in client.get(f"{API}/courses/{course['id']}/announcements",
                                           headers=course["teacher"]).json()] == ["scheduled"]
    with owner.begin() as conn:  # its time comes
        conn.execute(text("UPDATE announcements SET publish_at = now() - interval '1 minute' WHERE id = :a"),
                     {"a": scheduled["id"]})
    assert titles(client, course, course["a"]) == ["Later"]
    assert inbox_kinds(client, course["a"]) == ["announcement"]
    assert inbox_kinds(client, course["a"]) == ["announcement"]
    assert inbox_kinds(client, course["b"]) == ["announcement"]
    assert [x["state"] for x in client.get(f"{API}/courses/{course['id']}/announcements",
                                           headers=course["teacher"]).json()] == ["published"]


def test_announcements_are_listed_by_the_time_they_became_visible(client, owner, course):
    early = post(client, course, title="Early").json()
    later = post(client, course, title="Scheduled earlier", mode="schedule", publish_at=when(hours=5).isoformat()).json()
    with owner.begin() as conn:
        conn.execute(text("UPDATE announcements SET publish_at = now() - interval '1 hour' WHERE id = :a"),
                     {"a": later["id"]})
        conn.execute(text("UPDATE announcements SET created_at = now() - interval '2 hours' WHERE id = :a"),
                     {"a": early["id"]})
    assert titles(client, course, course["a"]) == ["Scheduled earlier", "Early"]


@pytest.mark.parametrize(
    "bad",
    [
        {"mode": "schedule"},
        {"mode": "schedule", "publish_at": "2020-01-01T00:00:00+00:00"},
        {"mode": "schedule", "publish_at": "2999-01-01T00:00:00"},
        {"mode": "publish", "publish_at": "2999-01-01T00:00:00+00:00"},
        {"mode": "draft", "publish_at": "2999-01-01T00:00:00+00:00"},
        {"mode": "later"},
    ],
)
def test_a_bad_publishing_choice_is_refused(client, course, bad):
    assert post(client, course, **bad).status_code == 422


def test_students_cannot_post_or_see_a_teachers_other_states(client, course):
    assert client.post(f"{API}/courses/{course['id']}/announcements", headers=course["a"],
                       json={"title": "x", "body": "y", "mode": "draft"}).status_code == 403
    post(client, course, title="Hidden", mode="draft")
    assert "Hidden" not in str(client.get(f"{API}/courses/{course['id']}/announcements", headers=course["a"]).json())


def work_assignment(client, course, title="Essay", due=3, **extra):
    body = {"title": title, "due_at": when(due).isoformat(), "work": {"instructions": "Do it.", "points": 10}, **extra}
    made = client.post(f"{API}/courses/{course['id']}/assignments", headers=course["teacher"], json=body)
    assert made.status_code == 201, made.text
    return made.json()


def assignment_titles(client, course, who):
    return [a["title"] for a in client.get(f"{API}/courses/{course['id']}/assignments", headers=who).json()]


def test_an_assignment_given_to_chosen_students_is_invisible_to_the_others(client, course):
    a = work_assignment(client, course, "Just for A", students=[course["a_id"]])
    assert a["students"] == [course["a_id"]]
    assert assignment_titles(client, course, course["a"]) == ["Just for A"]
    assert assignment_titles(client, course, course["b"]) == []
    shown = client.get(f"{API}/courses/{course['id']}/assignments", headers=course["a"]).json()[0]
    assert shown["students"] is None  # nobody learns who else was chosen
    assert client.get(f"{API}/courses/{course['id']}/assignments", headers=course["teacher"]).json()[0]["students"] \
        == [course["a_id"]]
    todo_a = client.get(f"{API}/students/me/todo", headers=course["a"]).json()
    todo_b = client.get(f"{API}/students/me/todo", headers=course["b"]).json()
    assert [t["title"] for t in todo_a] == ["Just for A"] and todo_b == []
    window = {"start": when(0).isoformat(), "end": when(30).isoformat()}
    assert len(client.get(f"{API}/calendar", headers=course["a"], params=window).json()) == 1
    assert client.get(f"{API}/calendar", headers=course["b"], params=window).json() == []


def test_a_student_the_work_was_not_given_to_cannot_open_or_hand_in_to_it(client, course):
    a = work_assignment(client, course, students=[course["a_id"]])
    work = f"{API}/courses/{course['id']}/assignments/{a['id']}/work"
    assert client.get(work, headers=course["a"]).status_code == 200
    assert client.get(work, headers=course["b"]).status_code == 404
    assert client.post(f"{work}/draft", headers=course["b"], json={"text": "x"}).status_code == 404
    assert client.post(f"{work}/turn-in", headers=course["b"]).status_code == 404
    rows = client.get(f"{work}/submissions", headers=course["teacher"]).json()["rows"]
    assert [r["student_id"] for r in rows] == [course["a_id"]]


def test_scores_and_the_gradebook_ignore_an_assignment_a_student_was_not_given(client, owner, course):
    given = work_assignment(client, course, "Given to A", students=[course["a_id"]])
    everyone = work_assignment(client, course, "For all", due=4)
    book = client.get(f"{API}/courses/{course['id']}/gradebook", headers=course["teacher"]).json()
    rows = {r["student_id"]: r for r in book["students"]}
    assert {c["assignment_id"] for c in rows[course["a_id"]]["cells"]} == {given["id"], everyone["id"]}
    assert {c["assignment_id"] for c in rows[course["b_id"]]["cells"]} == {everyone["id"]}
    assert (rows[course["a_id"]]["possible"], rows[course["b_id"]]["possible"]) == (20, 10)
    with owner.connect() as conn:
        found = conn.execute(
            text("SELECT student_id FROM assignment_scores(:c, NULL) WHERE assignment_id = :a"),
            {"c": course["id"], "a": given["id"]},
        ).scalars().all()
    assert found == [course["a_id"]]
    csv = client.get(f"{API}/courses/{course['id']}/export/gradebook", headers=course["teacher"])
    assert csv.status_code == 200 and csv.text.count("Given to A") == 1


def test_changing_who_an_assignment_is_given_to_changes_what_each_student_sees(client, course):
    a = work_assignment(client, course, students=[course["a_id"]])
    url = f"{API}/courses/{course['id']}/assignments/{a['id']}"
    body = {"title": "Essay", "due_at": when(3).isoformat(), "work": {"instructions": "Do it.", "points": 10}}
    client.put(url, headers=course["teacher"], json={**body, "students": [course["b_id"]]})
    assert assignment_titles(client, course, course["a"]) == [] and assignment_titles(client, course, course["b"]) == ["Essay"]
    everyone = client.put(url, headers=course["teacher"], json={**body, "students": []}).json()
    assert everyone["students"] is None
    assert assignment_titles(client, course, course["a"]) == ["Essay"] == assignment_titles(client, course, course["b"])


def test_only_students_of_this_course_can_be_chosen(client, make_user, course):
    outsider_id, _ = make_user("student")
    other_teacher_id, _ = make_user("instructor")
    body = {"title": "x", "due_at": when(3).isoformat(), "work": {"instructions": "i", "points": 1}}
    url = f"{API}/courses/{course['id']}/assignments"
    for ids in ([outsider_id], [other_teacher_id], [course["a_id"], 99999999], [course["teacher_id"]]):
        assert client.post(url, headers=course["teacher"], json={**body, "students": ids}).status_code == 422


def test_an_assignment_is_filed_under_a_topic_of_its_own_course(client, make_user, course):
    module = client.post(f"{API}/courses/{course['id']}/modules", headers=course["teacher"], json={"title": "Loops"}).json()
    a = work_assignment(client, course, module_id=module["id"])
    assert a["module_id"] == module["id"]
    assert client.get(f"{API}/courses/{course['id']}/assignments", headers=course["a"]).json()[0]["module_id"] == module["id"]
    elsewhere = client.post(f"{API}/courses", headers=course["teacher"], json={"title": "Elsewhere"}).json()
    foreign = client.post(f"{API}/courses/{elsewhere['id']}/modules", headers=course["teacher"], json={"title": "X"}).json()
    body = {"title": "y", "due_at": when(3).isoformat(), "work": {"instructions": "i", "points": 1}}
    assert client.post(f"{API}/courses/{course['id']}/assignments", headers=course["teacher"],
                       json={**body, "module_id": foreign["id"]}).status_code == 422
    assert client.delete(f"{API}/courses/{course['id']}/modules/{module['id']}", headers=course["teacher"]).status_code == 204
    assert client.get(f"{API}/courses/{course['id']}/assignments", headers=course["teacher"]).json()[0]["module_id"] is None


def test_the_instructor_dashboard_counts_only_the_students_an_assignment_was_given_to(client, course):
    work_assignment(client, course, students=[course["a_id"]])
    stats = client.get(f"{API}/instructor/stats", headers=course["teacher"]).json()
    assert [u["students"] for u in stats["upcoming"]] == [1]
