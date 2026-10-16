"""TR-V-07, TR-S-02: every role against every endpoint.

The policy table below is the intended access rule for each route. The first test fails when a route exists that the
table does not list, so a new endpoint cannot ship without its access rule being written down and tested.
"""
import re

import pytest

from app.main import app

API = "/api/v1"
PUBLIC = "public"
ANY = "any signed-in user"
STUDENT = "student"
INSTRUCTOR = "instructor"
STAFF = "instructor or admin"
ADMIN = "admin only"

POLICY = {
    ("GET", "/health"): PUBLIC,
    ("POST", "/auth/register"): PUBLIC,
    ("POST", "/auth/login"): PUBLIC,
    ("GET", "/lti/login"): PUBLIC,
    ("POST", "/lti/login"): PUBLIC,
    ("POST", "/lti/launch"): PUBLIC,
    ("POST", "/lti/session"): PUBLIC,
    ("GET", "/lti/jwks"): PUBLIC,
    ("POST", "/courses/{course_id}/gradebook/send"): INSTRUCTOR,
    ("GET", "/courses"): ANY,
    ("GET", "/consent/notice"): ANY,
    ("GET", "/me"): ANY,
    ("PATCH", "/me"): ANY,
    ("POST", "/me/password"): ANY,
    ("GET", "/admin/users"): ADMIN,
    ("POST", "/admin/users"): ADMIN,
    ("POST", "/admin/users/{user_id}/reset-password"): ADMIN,
    ("POST", "/admin/users/{user_id}/disable"): ADMIN,
    ("POST", "/admin/users/{user_id}/enable"): ADMIN,
    ("PATCH", "/admin/users/{user_id}/role"): ADMIN,
    ("GET", "/consent"): STUDENT,
    ("POST", "/consent/accept"): STUDENT,
    ("POST", "/consent/withdraw"): STUDENT,
    ("GET", "/me/erasure"): STUDENT,
    ("POST", "/me/erasure"): STUDENT,
    ("DELETE", "/me/erasure"): STUDENT,
    ("POST", "/courses"): INSTRUCTOR,
    ("GET", "/courses/{course_id}/concepts"): ANY,
    ("POST", "/courses/{course_id}/concepts"): INSTRUCTOR,
    ("POST", "/courses/{course_id}/enroll"): STUDENT,
    ("DELETE", "/courses/{course_id}/enroll"): STUDENT,
    ("PATCH", "/courses/{course_id}"): INSTRUCTOR,
    ("POST", "/courses/{course_id}/archive"): INSTRUCTOR,
    ("POST", "/courses/{course_id}/restore"): INSTRUCTOR,
    ("PATCH", "/courses/{course_id}/concepts/{concept_id}"): INSTRUCTOR,
    ("DELETE", "/courses/{course_id}/concepts/{concept_id}"): INSTRUCTOR,
    ("DELETE", "/courses/{course_id}/students/{student_id}"): INSTRUCTOR,
    ("GET", "/courses/{course_id}/students/{student_id}"): INSTRUCTOR,
    ("GET", "/courses/{course_id}/students/{student_id}/mastery/{concept_id}/history"): INSTRUCTOR,
    ("GET", "/courses/{course_id}/students/{student_id}/submissions/{submission_id}"): INSTRUCTOR,
    ("DELETE", "/courses/{course_id}/documents/{document_id}"): INSTRUCTOR,
    ("GET", "/problems/{problem_id}/source"): INSTRUCTOR,
    ("PUT", "/problems/{problem_id}"): INSTRUCTOR,
    ("POST", "/problems/{problem_id}/archive"): INSTRUCTOR,
    ("POST", "/problems/{problem_id}/restore"): INSTRUCTOR,
    ("POST", "/problems/{problem_id}/review"): INSTRUCTOR,
    ("GET", "/courses/{course_id}/documents"): INSTRUCTOR,
    ("POST", "/courses/{course_id}/documents"): INSTRUCTOR,
    ("GET", "/courses/{course_id}/class-mastery"): STAFF,
    ("GET", "/courses/{course_id}/misconceptions"): STAFF,
    ("GET", "/courses/{course_id}/explanations"): STAFF,
    ("GET", "/courses/{course_id}/export/mastery"): STAFF,
    ("GET", "/courses/{course_id}/export/gradebook"): STAFF,
    ("GET", "/courses/{course_id}/assignments"): ANY,
    ("POST", "/courses/{course_id}/assignments"): INSTRUCTOR,
    ("PUT", "/courses/{course_id}/assignments/{assignment_id}"): INSTRUCTOR,
    ("DELETE", "/courses/{course_id}/assignments/{assignment_id}"): INSTRUCTOR,
    ("GET", "/courses/{course_id}/gradebook"): STAFF,
    ("GET", "/courses/{course_id}/announcements"): ANY,
    ("POST", "/courses/{course_id}/announcements"): INSTRUCTOR,
    ("PUT", "/courses/{course_id}/announcements/{announcement_id}"): INSTRUCTOR,
    ("DELETE", "/courses/{course_id}/announcements/{announcement_id}"): INSTRUCTOR,
    ("GET", "/courses/{course_id}/export/mastery-events"): STAFF,
    ("POST", "/explanations/{signature}/approve"): INSTRUCTOR,
    ("GET", "/problems"): ANY,
    ("GET", "/problems/{problem_id}"): ANY,
    ("POST", "/problems"): INSTRUCTOR,
    ("PUT", "/problems/{problem_id}/policy"): INSTRUCTOR,
    ("GET", "/problems/{problem_id}/policy"): INSTRUCTOR,
    ("POST", "/submissions"): STUDENT,
    ("POST", "/submissions/run"): STUDENT,
    ("GET", "/submissions/{submission_id}"): ANY,
    ("POST", "/submissions/{submission_id}/explain"): STUDENT,
    ("POST", "/submissions/{submission_id}/hint"): STUDENT,
    ("POST", "/probes/{problem_id}/answer"): STUDENT,
    ("POST", "/diagnostic/start"): STUDENT,
    ("POST", "/diagnostic/answer"): STUDENT,
    ("GET", "/students/me/mastery"): STUDENT,
    ("GET", "/students/me/mastery/{concept_id}/history"): STUDENT,
    ("POST", "/chat"): STUDENT,
}
ALLOWED = {
    PUBLIC: {"anonymous", "student", "instructor", "admin"},
    ANY: {"student", "instructor", "admin"},
    STUDENT: {"student"},
    INSTRUCTOR: {"instructor"},
    STAFF: {"instructor", "admin"},
    ADMIN: {"admin"},
}


def routes():
    """Every route the API publishes, read from its OpenAPI description (the frozen contract)."""
    for path, operations in app.openapi()["paths"].items():
        if path.startswith(API):
            for method in operations:
                yield method.upper(), path[len(API):]


def test_every_route_has_a_written_access_rule():
    assert sorted(set(routes())) == sorted(POLICY), "add the new route to POLICY with its rule"


def request(client, method, template, headers):
    path = API + re.sub(r"\{[^}]+\}", "1", template)
    kwargs = {"headers": headers} if headers else {}
    if template in ("/problems", "/students/me/mastery"):
        kwargs["params"] = {"course_id": 1}
    if method in ("POST", "PUT", "PATCH"):
        kwargs["json"] = {}
    return client.request(method, path, **kwargs)


@pytest.fixture(scope="module")
def principals(make_user):
    return {
        "anonymous": None,
        "student": make_user("student")[1],
        "instructor": make_user("instructor")[1],
        "admin": make_user("admin")[1],
    }


@pytest.mark.parametrize("method,template", sorted(POLICY))
def test_each_role_gets_exactly_the_access_it_should(client, principals, method, template):
    allowed = ALLOWED[POLICY[(method, template)]]
    for role, headers in principals.items():
        response = request(client, method, template, headers)
        refused_for_role = response.status_code == 403 and "insufficient role" in response.text
        if role in allowed:
            # A later 403 or 404 for ownership is fine; being turned away at the door is not.
            assert response.status_code != 401 and not refused_for_role, f"{role} blocked from {method} {template}"
        elif role == "anonymous":
            assert response.status_code == 401, f"anonymous {method} {template}: {response.status_code}"
        else:
            assert refused_for_role, f"{role} {method} {template}: {response.status_code} {response.text[:80]}"
        assert response.status_code != 500, f"{role} {method} {template} crashed"


def test_admin_has_no_extra_reach_today():
    """Documented behaviour, not a goal: admin can read the class views and manage users, but cannot create courses or problems."""
    assert not any("admin" in ALLOWED[rule] for rule in (INSTRUCTOR, STUDENT))
