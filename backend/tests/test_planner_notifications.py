"""F-78, F-79, F-80: the to-do list, the calendar and in-app notifications show each person only their own things."""
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from tests.helpers import enroll

API = "/api/v1"


def when(days: float = 0, hours: float = 0) -> datetime:
    return datetime.now(UTC) + timedelta(days=days, hours=hours)


@pytest.fixture
def course(client, make_user):
    teacher_id, teacher = make_user("instructor")
    made = client.post(f"{API}/courses", headers=teacher, json={"title": f"Plan {uuid.uuid4().hex[:6]}"}).json()
    student_id, student = make_user("student")
    assert enroll(client, made['id'], student).status_code == 200
    return {"id": made["id"], "title": made["title"], "teacher": teacher, "teacher_id": teacher_id, "student": student,
            "student_id": student_id}


def assignment(client, course, title, due, work=True):
    body = {"title": title, "confirm_past_due": True, "due_at": due.isoformat(), "work": {"instructions": "Do it.", "points": 10}}
    made = client.post(f"{API}/courses/{course['id']}/assignments", headers=course["teacher"], json=body)
    assert made.status_code == 201, made.text
    return made.json()


def work_path(course, a, tail=""):
    return f"{API}/courses/{course['id']}/assignments/{a['id']}/work{tail}"


def hand_in(client, course, a):
    client.post(work_path(course, a, "/draft"), headers=course["student"], json={"text": "my work"})
    assert client.post(work_path(course, a, "/turn-in"), headers=course["student"]).status_code == 200


def inbox(client, headers):
    return client.get(f"{API}/notifications", headers=headers).json()


def test_the_todo_list_marks_each_assignment_assigned_missing_or_done(client, course):
    assignment(client, course, "Soon", when(2))
    assignment(client, course, "Late", when(-1))
    done = assignment(client, course, "Done", when(3))
    hand_in(client, course, done)
    todo = client.get(f"{API}/students/me/todo", headers=course["student"]).json()
    assert {t["title"]: t["state"] for t in todo} == {"Soon": "assigned", "Late": "missing", "Done": "done"}
    assert [t["title"] for t in todo] == ["Late", "Soon", "Done"]  # soonest due first
    assert all(t["course_title"] == course["title"] and t["has_work"] for t in todo)


def test_a_work_assignment_with_a_graded_score_is_done_only_when_the_score_is_complete(client, course):
    a = assignment(client, course, "Graded", when(2))
    hand_in(client, course, a)
    url = work_path(course, a, f"/students/{course['student_id']}")
    client.put(f"{url}/grade", headers=course["teacher"], json={"score": 5})
    client.post(f"{url}/return", headers=course["teacher"])
    todo = client.get(f"{API}/students/me/todo", headers=course["student"]).json()
    assert todo[0]["state"] == "done" and todo[0]["score"] == 5  # turned in counts as done for a work-only assignment


def test_the_todo_list_only_holds_the_students_own_live_courses(client, make_user, course):
    assignment(client, course, "Mine", when(2))
    _, outsider = make_user("student")
    assert client.get(f"{API}/students/me/todo", headers=outsider).json() == []
    assert client.get(f"{API}/students/me/todo", headers=course["teacher"]).status_code == 403
    assert client.get(f"{API}/students/me/todo").status_code == 401
    client.post(f"{API}/courses/{course['id']}/archive", headers=course["teacher"])
    assert client.get(f"{API}/students/me/todo", headers=course["student"]).json() == []


def test_the_calendar_shows_due_dates_in_range_for_the_courses_a_person_is_in(client, make_user, course):
    inside = assignment(client, course, "Inside", when(5))
    assignment(client, course, "Outside", when(60))
    start, end = when(0).isoformat(), when(30).isoformat()
    params = {"start": start, "end": end}
    mine = client.get(f"{API}/calendar", headers=course["student"], params=params).json()
    assert [(i["title"], i["state"]) for i in mine] == [("Inside", "assigned")]
    teacher = client.get(f"{API}/calendar", headers=course["teacher"], params=params).json()
    assert [(i["title"], i["state"]) for i in teacher] == [("Inside", None)]
    _, outsider = make_user("student")
    _, other_teacher = make_user("instructor")
    assert client.get(f"{API}/calendar", headers=outsider, params=params).json() == []
    assert client.get(f"{API}/calendar", headers=other_teacher, params=params).json() == []
    one = client.get(f"{API}/calendar", headers=course["student"], params={**params, "course_id": course["id"] + 99999})
    assert one.json() == []
    assert inside["id"] == mine[0]["assignment_id"]


def test_the_calendar_refuses_a_bad_range_and_the_wrong_role(client, make_user, course):
    ok = {"start": when(0).isoformat(), "end": when(10).isoformat()}
    assert client.get(f"{API}/calendar", headers=course["student"], params={"start": "2026-11-01T00:00:00",
                                                                          "end": "2026-11-05T00:00:00"}).status_code == 422
    assert client.get(f"{API}/calendar", headers=course["student"],
                      params={"start": ok["end"], "end": ok["start"]}).status_code == 422
    assert client.get(f"{API}/calendar", headers=course["student"],
                      params={"start": ok["start"], "end": when(200).isoformat()}).status_code == 422
    _, admin = make_user("admin")
    assert client.get(f"{API}/calendar", headers=admin, params=ok).status_code == 403
    assert client.get(f"{API}/calendar", params=ok).status_code == 401


def test_an_announcement_notifies_the_courses_students_and_nobody_else(client, make_user, course):
    _, outsider = make_user("student")
    client.post(f"{API}/courses/{course['id']}/announcements", headers=course["teacher"],
                json={"title": "Exam moved", "body": "Details inside."})
    mine = inbox(client, course["student"])
    assert mine["unread"] == 1
    item = mine["items"][0]
    assert item["kind"] == "announcement" and "Exam moved" in item["title"] and course["title"] in item["title"]
    assert item["link"] == f"#/course/{course['id']}" and item["read"] is False
    assert inbox(client, outsider) == {"unread": 0, "items": []}
    assert inbox(client, course["teacher"]) == {"unread": 0, "items": []}


def test_handing_in_returning_and_commenting_notify_the_right_person_without_private_text(client, course):
    a = assignment(client, course, "Essay", when(3))
    hand_in(client, course, a)
    teacher_items = inbox(client, course["teacher"])["items"]
    assert [i["kind"] for i in teacher_items] == ["work_turned_in"]
    assert teacher_items[0]["link"] == f"#/course/{course['id']}/assignment/{a['id']}/review"
    client.post(work_path(course, a, "/comments"), headers=course["student"], json={"body": "secret question text"})
    url = work_path(course, a, f"/students/{course['student_id']}")
    client.post(f"{url}/comments", headers=course["teacher"], json={"body": "secret answer text"})
    client.put(f"{url}/grade", headers=course["teacher"], json={"score": 8, "feedback": "secret feedback text"})
    assert inbox(client, course["student"])["items"][0]["kind"] == "comment"  # nothing yet from the grade itself
    client.post(f"{url}/return", headers=course["teacher"])
    student_items = inbox(client, course["student"])["items"]
    assert [i["kind"] for i in student_items] == ["work_returned", "comment"]
    assert student_items[0]["link"] == f"#/course/{course['id']}/assignment/{a['id']}"
    everything = str(inbox(client, course["student"])) + str(inbox(client, course["teacher"]))
    assert "secret" not in everything and "8" not in str([i["title"] for i in student_items])
    assert [i["kind"] for i in inbox(client, course["teacher"])["items"]] == ["comment", "work_turned_in"]


def test_return_all_notifies_every_returned_student(client, make_user, course):
    other_id, other = make_user("student")
    enroll(client, course['id'], other)
    a = assignment(client, course, "Both", when(3))
    hand_in(client, course, a)
    client.post(work_path(course, a, "/draft"), headers=other, json={"text": "mine"})
    client.post(work_path(course, a, "/turn-in"), headers=other)
    for sid in (course["student_id"], other_id):
        client.put(work_path(course, a, f"/students/{sid}/grade"), headers=course["teacher"], json={"score": 4})
    assert client.post(work_path(course, a, "/return-all"), headers=course["teacher"]).json() == {"count": 2}
    for who in (course["student"], other):
        assert [i["kind"] for i in inbox(client, who)["items"]] == ["work_returned"]


def test_notifications_can_be_marked_read_one_by_one_or_all_at_once_and_only_by_their_owner(client, course):
    for n in range(3):
        client.post(f"{API}/courses/{course['id']}/announcements", headers=course["teacher"],
                    json={"title": f"News {n}", "body": "b"})
    items = inbox(client, course["student"])["items"]
    assert [i["title"].split(": ")[-1] for i in items] == ["News 2", "News 1", "News 0"]  # newest first
    assert client.post(f"{API}/notifications/{items[0]['id']}/read", headers=course["teacher"]).status_code == 404
    assert client.post(f"{API}/notifications/{items[0]['id']}/read", headers=course["student"]).status_code == 204
    assert inbox(client, course["student"])["unread"] == 2
    assert client.post(f"{API}/notifications/99999999/read", headers=course["student"]).status_code == 404
    assert client.post(f"{API}/notifications/read-all", headers=course["student"]).status_code == 204
    after = inbox(client, course["student"])
    assert after["unread"] == 0 and all(i["read"] for i in after["items"])
    assert client.get(f"{API}/notifications").status_code == 401


def test_a_due_soon_notice_is_made_once_for_unfinished_work_due_within_two_days(client, course):
    assignment(client, course, "Tomorrow", when(hours=20))
    assignment(client, course, "Far away", when(5))
    finished = assignment(client, course, "Finished", when(hours=10))
    hand_in(client, course, finished)
    first = inbox(client, course["student"])
    again = inbox(client, course["student"])
    titles = [i["title"] for i in again["items"] if i["kind"] == "due_soon"]
    assert len(titles) == 1 and "Tomorrow" in titles[0]
    assert first["unread"] == again["unread"] == 1
    assert [i["kind"] for i in inbox(client, course["teacher"])["items"]
            if i["kind"] == "due_soon"] == []  # teachers get no due-soon notices


def test_a_student_who_is_removed_loses_nothing_but_sees_no_new_course_notices(client, make_user, course):
    client.delete(f"{API}/courses/{course['id']}/students/{course['student_id']}", headers=course["teacher"])
    client.post(f"{API}/courses/{course['id']}/announcements", headers=course["teacher"],
                json={"title": "After removal", "body": "b"})
    assert inbox(client, course["student"])["items"] == []


def test_the_notification_link_is_always_an_in_app_address(client, course):
    client.post(f"{API}/courses/{course['id']}/announcements", headers=course["teacher"], json={"title": "x", "body": "b"})
    for item in inbox(client, course["student"])["items"]:
        assert item["link"].startswith("#/") and "://" not in item["link"]
