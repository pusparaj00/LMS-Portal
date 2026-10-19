"""TR-S-08: the audit trail records what is needed to detect and report a breach, and nothing it should not."""
import json
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app import audit, breach_report
from app.db import get_engine
from tests.helpers import enroll

API = "/api/v1"
PASSWORD = "pw-12345678"  # make_user's password


@pytest.fixture
def since(owner):
    with owner.connect() as conn:
        return conn.execute(text("SELECT now()")).scalar_one()


def events(owner, since, *names):
    with owner.connect() as conn:
        return conn.execute(
            text("SELECT * FROM audit_events WHERE at >= :s AND event = ANY(:n) ORDER BY id"),
            {"s": since, "n": list(names)},
        ).mappings().all()


def email_of(owner, user_id):
    with owner.connect() as conn:
        return conn.execute(text("SELECT email FROM users WHERE id = :u"), {"u": user_id}).scalar_one()


def report(owner, since):
    with owner.connect() as conn:
        return breach_report.report(conn, since, conn.execute(text("SELECT now()")).scalar_one())


def test_logins_are_recorded_without_the_password_or_the_email(client, make_user, owner, since):
    user_id, _ = make_user("student")
    email = email_of(owner, user_id)
    assert client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200
    assert client.post(f"{API}/auth/login", json={"email": email, "password": "not-the-password"}).status_code == 401
    unknown = f"nobody-{uuid.uuid4().hex[:6]}@test.local"
    assert client.post(f"{API}/auth/login", json={"email": unknown, "password": "whatever-123"}).status_code == 401

    ok, wrong, nobody = events(owner, since, "auth.login", "auth.login_failed")
    assert ok["event"] == "auth.login" and ok["user_id"] == user_id and ok["ip"] == "testclient"
    assert wrong["user_id"] == user_id and wrong["detail"]["known_account"] is True
    assert nobody["user_id"] is None and nobody["detail"]["known_account"] is False
    assert wrong["detail"]["email_tag"] == audit.email_tag(email) != nobody["detail"]["email_tag"]
    stored = json.dumps([dict(r) for r in (ok, wrong, nobody)], default=str)
    for secret in (PASSWORD, "not-the-password", "whatever-123", email, unknown, email.split("@")[0]):
        assert secret not in stored


def test_refused_requests_are_recorded_with_who_and_where(client, make_user, owner, course, since):
    student_id, student = make_user("student")
    assert client.get(f"{API}/courses/{course['id']}/class-mastery", headers=student).status_code == 403
    assert client.get(f"{API}/courses/{course['id']}/class-mastery").status_code == 401
    denied = events(owner, since, "access.denied")
    assert [(e["user_id"], e["status"]) for e in denied] == [(student_id, 403), (None, 401)]
    assert denied[0]["detail"]["path"] == f"{API}/courses/{course['id']}/class-mastery"
    assert denied[0]["request_id"] and denied[0]["request_id"] != "-"


def test_the_report_finds_password_guessing_and_a_student_reading_others_submissions(
    client, make_user, owner, course, since, clock
):
    for _ in range(12):  # the first ten are refused, the rest are throttled
        client.post(f"{API}/auth/login", json={"email": "victim@test.local", "password": "guess-123456"})
    prober_id, prober = make_user("student")
    victim_id, _ = make_user("student")
    with owner.begin() as conn:
        ids = [
            conn.execute(
                text("INSERT INTO submissions (user_id, problem_id, code) VALUES (:u, :p, 'x') RETURNING id"),
                {"u": victim_id, "p": course["problem_id"]},
            ).scalar_one()
            for _ in range(12)
        ]
        for sid in ids:
            conn.execute(
                text("INSERT INTO run_results (submission_id, status, passed, failed) VALUES (:s, 'failed', 0, 1)"),
                {"s": sid},
            )
    for sid in ids:
        assert client.get(f"{API}/submissions/{sid}", headers=prober).status_code == 404

    found = report(owner, since)
    guessing = {r["ip"]: r for r in found["password_guessing_by_address"]}
    assert guessing["testclient"]["failures"] >= breach_report.FAILED_LOGINS_PER_IP
    assert found["password_guessing_by_account"][0]["failures"] >= breach_report.FAILED_LOGINS_PER_ACCOUNT
    probers = {r["user_id"]: r for r in found["accounts_with_many_refused_reads"]}
    assert probers[prober_id]["not_found"] == 12
    assert victim_id in found["possibly_affected_students"]["owners_of_probed_submissions"]
    assert prober_id not in found["possibly_affected_students"]["owners_of_probed_submissions"]
    assert {e["event"] for e in events(owner, since, "rate_limited")} == {"rate_limited"}


def test_exports_are_recorded_and_their_students_reported_as_affected(client, make_user, owner, course, since):
    student_id, student = make_user("student")
    enroll(client, course['id'], student)
    response = client.get(f"{API}/courses/{course['id']}/export/mastery", headers=course["instructor"])
    assert response.status_code == 200
    (event,) = events(owner, since, "export.download")
    assert event["user_id"] == course["instructor_id"]
    assert event["detail"] == {"course_id": course["id"], "kind": "mastery", "format": "csv"}
    found = report(owner, since)
    assert student_id in found["possibly_affected_students"]["students_in_exported_courses"]


def test_consent_erasure_and_staff_accounts_are_recorded(client, make_user, owner, since):
    student_id, student = make_user("student")
    client.post(f"{API}/consent/withdraw", headers=student)
    client.post(f"{API}/me/erasure", headers=student, json={"password": PASSWORD})
    client.delete(f"{API}/me/erasure", headers=student)

    from app.manage import create_user

    staff_id = create_user(f"staff-{uuid.uuid4().hex[:6]}@test.local", "instructor", "a-long-password-1")
    try:
        names = [e["event"] for e in events(
            owner, since, "consent.withdrawn", "erasure.scheduled", "erasure.cancelled", "staff.created"
        )]
        assert names == ["consent.withdrawn", "erasure.scheduled", "erasure.cancelled", "staff.created"]
        assert report(owner, since)["staff_accounts_created"][0]["user_id"] == staff_id
    finally:
        with owner.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE id = :u"), {"u": staff_id})


def test_the_api_role_cannot_change_or_remove_events_but_old_ones_expire(owner, since):
    for statement in ("UPDATE audit_events SET event = 'x'", "DELETE FROM audit_events"):
        with pytest.raises(ProgrammingError, match="permission denied"):
            with get_engine().begin() as conn:
                conn.execute(text(statement))
    with owner.begin() as conn:
        old = conn.execute(
            text("INSERT INTO audit_events (at, event) VALUES (now() - interval '400 days', 'test.old') RETURNING id")
        ).scalar_one()
        new = conn.execute(text("INSERT INTO audit_events (event) VALUES ('test.new') RETURNING id")).scalar_one()
    with get_engine().begin() as conn:
        assert audit.purge(conn, 0) == 0  # 0 keeps everything
        assert audit.purge(conn, 365) >= 1
    with owner.begin() as conn:
        left = conn.execute(text("SELECT id FROM audit_events WHERE id = ANY(:i)"), {"i": [old, new]}).scalars().all()
        assert left == [new]
        conn.execute(text("DELETE FROM audit_events WHERE id = :i"), {"i": new})


def test_a_request_still_works_when_the_audit_trail_cannot_be_written(client, make_user, owner, monkeypatch):
    def unavailable():
        raise ConnectionError("database down")

    monkeypatch.setattr("app.db.get_engine", unavailable)
    user_id, _ = make_user("student")
    email = email_of(owner, user_id)
    assert client.post(f"{API}/auth/login", json={"email": email, "password": "wrong-password-1"}).status_code == 401
    assert client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200
