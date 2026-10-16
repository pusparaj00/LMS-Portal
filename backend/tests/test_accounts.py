"""F-01, TR-S-01, TR-S-08: own password and name; admin reset, disable and role changes; sessions end on a change."""
import time
import uuid

import pytest
from sqlalchemy import text

from app.auth import create_token

API = "/api/v1"
PASSWORD = "pw-12345678"  # make_user's password


def email_of(owner, user_id):
    with owner.connect() as conn:
        return conn.execute(text("SELECT email FROM users WHERE id = :u"), {"u": user_id}).scalar_one()


def login(client, email, password):
    return client.post(f"{API}/auth/login", json={"email": email, "password": password})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def older_token(user_id, role):
    """A session started before any change made in this test (the clock moves on by a second first)."""
    token = create_token(user_id, role)
    time.sleep(1.1)
    return bearer(token)


@pytest.fixture
def admin(make_user):
    return make_user("admin")


def test_changing_the_password_ends_other_sessions_and_keeps_this_one(client, make_user, owner):
    user_id, _ = make_user("student")
    old = older_token(user_id, "student")
    assert client.get(f"{API}/me", headers=old).status_code == 200
    body = {"current_password": "nope-nope-1", "new_password": "x" * 10}
    assert client.post(f"{API}/me/password", headers=old, json=body).status_code == 403
    body = {"current_password": PASSWORD, "new_password": PASSWORD}
    assert client.post(f"{API}/me/password", headers=old, json=body).status_code == 422
    body = {"current_password": PASSWORD, "new_password": "short"}
    assert client.post(f"{API}/me/password", headers=old, json=body).status_code == 422
    changed = client.post(f"{API}/me/password", headers=old,
                          json={"current_password": PASSWORD, "new_password": "a-new-password-9"})
    assert changed.status_code == 200
    assert client.get(f"{API}/me", headers=old).status_code == 401  # the old session ended
    assert client.get(f"{API}/me", headers=bearer(changed.json()["access_token"])).status_code == 200
    email = email_of(owner, user_id)
    assert login(client, email, PASSWORD).status_code == 401
    assert login(client, email, "a-new-password-9").status_code == 200
    with owner.connect() as conn:
        events = conn.execute(text("SELECT count(*) FROM audit_events WHERE event = 'account.password_changed'"
                                   " AND user_id = :u"), {"u": user_id}).scalar_one()
    assert events == 1


def test_a_display_name_is_set_and_shown_to_teachers(client, make_user, course):
    user_id, student = make_user("student")
    client.post(f"{API}/courses/{course['id']}/enroll", headers=student)
    named = client.patch(f"{API}/me", headers=student, json={"display_name": "  Asha Verma "})
    assert named.json()["display_name"] == "Asha Verma"
    assert client.patch(f"{API}/me", headers=student, json={"display_name": "x" * 81}).status_code == 422
    grid = client.get(f"{API}/courses/{course['id']}/class-mastery", headers=course["instructor"]).json()
    assert {s["student_id"]: s["label"] for s in grid["students"]}[user_id] == "Asha Verma"
    cleared = client.patch(f"{API}/me", headers=student, json={"display_name": None}).json()
    assert cleared["display_name"] is None


def test_an_admin_reset_forces_a_new_password_and_ends_sessions(client, make_user, owner, admin):
    _, admin_headers = admin
    user_id, _ = make_user("instructor")
    old = older_token(user_id, "instructor")
    reset = client.post(f"{API}/admin/users/{user_id}/reset-password", headers=admin_headers)
    assert reset.status_code == 200 and reset.json()["user"]["must_change_password"] is True
    temporary = reset.json()["temporary_password"]
    assert client.get(f"{API}/courses", headers=old).status_code == 401
    session = login(client, email_of(owner, user_id), temporary)
    assert session.status_code == 200 and session.json()["must_change_password"] is True
    forced = bearer(session.json()["access_token"])
    assert client.get(f"{API}/courses", headers=forced).status_code == 403  # nothing else until the password changes
    assert client.get(f"{API}/me", headers=forced).json()["must_change_password"] is True
    done = client.post(f"{API}/me/password", headers=forced,
                       json={"current_password": temporary, "new_password": "chosen-by-me-1"})
    assert done.status_code == 200
    assert client.get(f"{API}/courses", headers=bearer(done.json()["access_token"])).status_code == 200


def test_an_admin_creates_staff_with_a_temporary_password(client, owner, admin):
    _, admin_headers = admin
    email = f"new-teacher-{uuid.uuid4().hex[:6]}@test.local"
    made = client.post(f"{API}/admin/users", headers=admin_headers,
                       json={"email": email, "role": "instructor", "display_name": "Dr. New"})
    assert made.status_code == 201
    try:
        assert made.json()["user"]["role"] == "instructor" and made.json()["user"]["must_change_password"] is True
        assert login(client, email, made.json()["temporary_password"]).json()["must_change_password"] is True
        again = client.post(f"{API}/admin/users", headers=admin_headers, json={"email": email, "role": "instructor"})
        assert again.status_code == 409
        for reserved in ("x@synthetic.local", "x@lti.local", "no-at-sign"):
            response = client.post(f"{API}/admin/users", headers=admin_headers,
                                   json={"email": reserved, "role": "instructor"})
            assert response.status_code == 422
        found = client.get(f"{API}/admin/users", headers=admin_headers, params={"q": "Dr. New"}).json()
        assert [u["email"] for u in found] == [email]
    finally:
        with owner.begin() as conn:
            conn.execute(text("DELETE FROM audit_events WHERE user_id IN (SELECT id FROM users WHERE email = :e)"),
                         {"e": email})
            conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})


def test_a_disabled_account_cannot_sign_in_and_its_sessions_end(client, make_user, owner, admin):
    _, admin_headers = admin
    user_id, headers = make_user("student")
    assert client.post(f"{API}/admin/users/{user_id}/disable", headers=admin_headers).json()["disabled"] is True
    assert client.get(f"{API}/me", headers=headers).status_code == 401
    refused = login(client, email_of(owner, user_id), PASSWORD)
    assert refused.status_code == 401 and "disabled" in refused.text
    guessed = login(client, email_of(owner, user_id), "wrong-password-1")
    assert guessed.json()["error"]["message"] == "wrong email or password"  # a guesser learns nothing
    assert client.post(f"{API}/admin/users/{user_id}/enable", headers=admin_headers).json()["disabled"] is False
    assert login(client, email_of(owner, user_id), PASSWORD).status_code == 200


def test_a_teacher_who_still_teaches_a_course_is_not_made_a_student(client, make_user, admin):
    _, admin_headers = admin
    teacher_id, teacher = make_user("instructor")
    assert client.post(f"{API}/courses", headers=teacher, json={"title": "Still taught"}).status_code == 201
    refused = client.patch(f"{API}/admin/users/{teacher_id}/role", headers=admin_headers, json={"role": "student"})
    assert refused.status_code == 409 and "'Still taught'" in refused.json()["error"]["message"]
    promoted = client.patch(f"{API}/admin/users/{teacher_id}/role", headers=admin_headers, json={"role": "admin"})
    assert promoted.status_code == 200  # an admin manages every course, so nothing is left without a teacher


def test_roles_change_at_once_and_the_last_admin_cannot_be_removed(client, make_user, owner, admin):
    admin_id, admin_headers = admin
    user_id, headers = make_user("student")
    changed = client.patch(f"{API}/admin/users/{user_id}/role", headers=admin_headers, json={"role": "instructor"})
    assert changed.json()["role"] == "instructor"
    assert client.post(f"{API}/courses", headers=headers, json={"title": "Now I teach"}).status_code == 201
    to_student = {"role": "student"}
    assert client.patch(f"{API}/admin/users/{admin_id}/role", headers=admin_headers, json=to_student).status_code == 409
    assert client.post(f"{API}/admin/users/{admin_id}/disable", headers=admin_headers).status_code == 409

    second_id, second = make_user("admin")
    with owner.begin() as conn:  # leave only these two admins enabled
        others = conn.execute(
            text("SELECT id FROM users WHERE role = 'admin' AND disabled_at IS NULL AND id <> ALL(:keep)"),
            {"keep": [admin_id, second_id]},
        ).scalars().all()
        conn.execute(text("UPDATE users SET disabled_at = now() WHERE id = ANY(:o)"), {"o": others})
    try:
        assert client.post(f"{API}/admin/users/{admin_id}/disable", headers=second).status_code == 200
        # second is now the last enabled admin: nobody can demote or disable them, and they cannot do it themselves
        assert client.post(f"{API}/admin/users/{second_id}/disable", headers=second).status_code == 409
        with owner.begin() as conn:
            conn.execute(text("UPDATE users SET disabled_at = NULL WHERE id = :a"), {"a": admin_id})
            conn.execute(text("UPDATE users SET disabled_at = now() WHERE id = :s"), {"s": second_id})
        last = client.patch(f"{API}/admin/users/{admin_id}/role", headers=second, json=to_student)
        assert last.status_code == 401  # second is disabled now, so cannot act at all
        with owner.begin() as conn:
            conn.execute(text("UPDATE users SET disabled_at = NULL WHERE id = :s"), {"s": second_id})
            conn.execute(text("UPDATE users SET disabled_at = now() WHERE id = :a"), {"a": admin_id})
        assert client.patch(f"{API}/admin/users/{second_id}/role", headers=second, json=to_student).status_code == 409
    finally:
        with owner.begin() as conn:
            conn.execute(text("UPDATE users SET disabled_at = NULL WHERE id = ANY(:o)"),
                         {"o": [*others, admin_id, second_id]})


def test_only_admins_manage_users(client, make_user):
    _, student = make_user("student")
    _, teacher = make_user("instructor")
    target, _ = make_user("student")
    for headers in (student, teacher):
        assert client.get(f"{API}/admin/users", headers=headers).status_code == 403
        assert client.post(f"{API}/admin/users/{target}/reset-password", headers=headers).status_code == 403
    assert client.get(f"{API}/admin/users").status_code == 401
