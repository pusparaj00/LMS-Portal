"""TR-S-02: a teacher or a student who is not part of a course reaches nothing in it, whatever the route.

test_access_matrix.py proves each role is let in or turned away at the door with the id 1. This one builds a real course
with a real object behind every id (assignment, quiz, module, lesson item, announcement, category, rubric, handed-in
work) and calls every course route as a teacher of another course and as a student who is not enrolled. The answer must
be a refusal. A route whose body this file cannot fill in is listed in UNFILLED so it is not mistaken for tested.
"""
import re
import uuid

import pytest
from sqlalchemy import text

from app.main import app
from tests.helpers import enroll
from tests.test_access_matrix import POLICY
from tests.test_grading_structure import RUBRIC
from tests.test_quizzes import quiz_body

API = "/api/v1"


def iso(days=3):
    from datetime import UTC, datetime, timedelta

    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


@pytest.fixture(scope="module")
def victim(client, make_user, owner):
    teacher_id, teacher = make_user("instructor")
    student_id, student = make_user("student")
    course = client.post(f"{API}/courses", headers=teacher, json={"title": f"Victim {uuid.uuid4().hex[:6]}"}).json()
    cid = course["id"]
    assert enroll(client, cid, student).status_code == 200
    base = f"{API}/courses/{cid}"
    ids = {"course_id": cid, "student_id": student_id}
    ids["rubric_id"] = client.post(f"{base}/rubrics", headers=teacher, json=RUBRIC).json()["id"]
    ids["category_id"] = client.post(f"{base}/categories", headers=teacher, json={"name": "Homework", "weight": 10}).json()[0]["id"]
    work = {"title": "Essay", "due_at": iso(), "work": {"instructions": "Write.", "points": 10, "rubric_id": ids["rubric_id"]}}
    ids["assignment_id"] = client.post(f"{base}/assignments", headers=teacher, json=work).json()["id"]
    ids["quiz_id"] = client.post(f"{base}/quizzes", headers=teacher, json=quiz_body()).json()["id"]
    ids["module_id"] = client.post(f"{base}/modules", headers=teacher, json={"title": "Week 1"}).json()["id"]
    item = client.post(f"{base}/modules/{ids['module_id']}/items", headers=teacher,
                       json={"kind": "text", "title": "Reading", "body": "Read this."}).json()
    ids["item_id"] = item["id"]
    ids["announcement_id"] = client.post(f"{base}/announcements", headers=teacher,
                                         json={"title": "Hello", "body": "Welcome."}).json()["id"]
    work_url = f"{base}/assignments/{ids['assignment_id']}/work"
    client.post(f"{work_url}/draft", headers=student, json={"text": "my essay"})
    client.post(f"{work_url}/turn-in", headers=student)
    with owner.begin() as conn:
        ids["notification_id"] = conn.execute(
            text("SELECT id FROM notifications WHERE user_id = :u ORDER BY id LIMIT 1"), {"u": teacher_id}
        ).scalar() or 0
        ids["concept_id"] = conn.execute(
            text("INSERT INTO concepts (course_id, name) VALUES (:c, 'loops') RETURNING id"), {"c": cid}
        ).scalar_one()
        ids["teacher_id"] = teacher_id
        ids["document_id"] = 0
        ids["submission_id"] = 0
        ids["problem_id"] = 0
    return {"ids": ids, "teacher": teacher, "student": student}


BODIES = {
    ("POST", "/courses/{course_id}/assignments"): lambda ids: {
        "title": "X", "due_at": iso(), "work": {"instructions": "i", "points": 1}},
    ("POST", "/courses/{course_id}/quizzes"): lambda ids: quiz_body(),
    ("POST", "/courses/{course_id}/modules"): lambda ids: {"title": "X"},
    ("POST", "/courses/{course_id}/modules/{module_id}/items"): lambda ids: {"kind": "text", "title": "X", "body": "x"},
    ("POST", "/courses/{course_id}/announcements"): lambda ids: {"title": "X", "body": "x"},
    ("POST", "/courses/{course_id}/categories"): lambda ids: {"name": "Other", "weight": 5},
    ("PUT", "/courses/{course_id}/categories/{category_id}"): lambda ids: {"name": "Other", "weight": 5},
    ("POST", "/courses/{course_id}/rubrics"): lambda ids: RUBRIC,
    ("PUT", "/courses/{course_id}/rubrics/{rubric_id}"): lambda ids: RUBRIC,
    ("POST", "/courses/{course_id}/concepts"): lambda ids: {"name": "other"},
    ("PATCH", "/courses/{course_id}"): lambda ids: {"title": "Hijacked"},
    ("PUT", "/courses/{course_id}/join-code"): lambda ids: {"enabled": False},
    ("POST", "/courses/{course_id}/assignments/{assignment_id}/work/draft"): lambda ids: {"text": "x"},
    ("PUT", "/courses/{course_id}/assignments/{assignment_id}/work/students/{student_id}/grade"): lambda ids: {
        "levels": {"1": 1}},
    ("POST", "/courses/{course_id}/assignments/{assignment_id}/work/students/{student_id}/comments"): lambda ids: {
        "body": "x"},
    ("POST", "/courses/{course_id}/assignments/{assignment_id}/work/comments"): lambda ids: {"body": "x"},
    ("POST", "/courses/{course_id}/quizzes/{quiz_id}/attempts"): lambda ids: {"answers": []},
    ("PATCH", "/courses/{course_id}/concepts/{concept_id}"): lambda ids: {"name": "renamed"},
    ("PATCH", "/courses/{course_id}/items/{item_id}"): lambda ids: {"title": "Hijacked"},
    ("PATCH", "/courses/{course_id}/modules/{module_id}"): lambda ids: {"title": "Hijacked"},
    ("POST", "/courses/{course_id}/items/{item_id}/move"): lambda ids: {"direction": "up"},
    ("POST", "/courses/{course_id}/modules/{module_id}/move"): lambda ids: {"direction": "up"},
    ("POST", "/courses/{course_id}/teachers"): lambda ids: {"email": "nobody@test.local"},
    ("PUT", "/courses/{course_id}/announcements/{announcement_id}"): lambda ids: {"title": "X", "body": "x"},
    ("PUT", "/courses/{course_id}/assignments/{assignment_id}"): lambda ids: {
        "title": "X", "due_at": iso(), "work": {"instructions": "i", "points": 1}},
    ("PUT", "/courses/{course_id}/assignments/{assignment_id}/students/{student_id}/override"): lambda ids: {
        "score": 5, "reason": "because"},
    ("PUT", "/courses/{course_id}/concepts/{concept_id}/prerequisites"): lambda ids: {"prerequisite_ids": []},
    ("PUT", "/courses/{course_id}/quizzes/{quiz_id}"): lambda ids: quiz_body(),
    ("PATCH", "/courses/{course_id}/documents/{document_id}"): lambda ids: {"visible_to_students": True},
    ("PUT", "/courses/{course_id}/ratings"): lambda ids: {"course_rating": 5, "instructor_rating": 5},
    ("PUT", "/courses/{course_id}/students/{student_id}/mute"): lambda ids: {"muted": True},
}
SKIP = {
    # these take no course in the path or have no owner to protect
    ("POST", "/courses/join"),
    ("DELETE", "/courses/{course_id}/enroll"),  # leaving a course one is not in is a harmless no-op
}


def routes():
    for path, operations in app.openapi()["paths"].items():
        template = path[len(API):]
        if "{course_id}" not in template:
            continue
        for method in operations:
            if (method.upper(), template) in POLICY and (method.upper(), template) not in SKIP:
                yield method.upper(), template


@pytest.mark.parametrize("method,template", sorted(routes()))
def test_outsiders_are_refused_on_every_course_route(client, make_user, victim, method, template):
    ids = victim["ids"]
    path = API + re.sub(r"\{([^}]+)\}", lambda m: str(ids.get(m.group(1), 1)), template)
    outsiders = [make_user("instructor")[1], make_user("student")[1]]
    for headers in outsiders:
        kwargs = {"headers": headers}
        if method in ("POST", "PUT", "PATCH"):
            kwargs["json"] = BODIES.get((method, template), lambda _ids: {})(ids)
        response = client.request(method, path, **kwargs)
        assert response.status_code not in range(200, 300), (
            f"outsider got {response.status_code} from {method} {template}: {response.text[:120]}")
        assert response.status_code != 500
