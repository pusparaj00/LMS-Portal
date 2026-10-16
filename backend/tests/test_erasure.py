"""TR-S-07: deletion on request and retention erasure, each after a 48-hour notice."""
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError

from app import erasure
from app.db import get_engine, get_redis
from app.mastery.client import erase_user

API = "/api/v1"
PASSWORD = "pw-12345678"


def erase_mastery(user_id: int) -> None:
    erase_user(user_id, url=os.environ["MASTERY_SERVICE_URL"], token=os.environ["MASTERY_SERVICE_TOKEN"])


def make_due(owner, user_id: int) -> None:
    with owner.begin() as conn:
        conn.execute(
            text(
                "UPDATE erasure_requests SET notified_at = now() - interval '3 days', due_at = now() - interval '1 day'"
                " WHERE user_id = :u AND status = 'pending'"
            ),
            {"u": user_id},
        )


def fill(owner, user_id: int, course) -> int:
    """One of everything a student owns; returns the submission id."""
    with owner.begin() as conn:
        concept = conn.execute(
            text("SELECT id FROM concepts WHERE course_id = :c LIMIT 1"), {"c": course["id"]}
        ).scalar_one()
        misconception = conn.execute(
            text("INSERT INTO misconceptions (concept_id, name, description) VALUES (:c, :n, 'd') RETURNING id"),
            {"c": concept, "n": f"m-{uuid.uuid4().hex[:8]}"},
        ).scalar_one()
        submission = conn.execute(
            text("INSERT INTO submissions (user_id, problem_id, code) VALUES (:u, :p, 'print(1)') RETURNING id"),
            {"u": user_id, "p": course["problem_id"]},
        ).scalar_one()
        conn.execute(
            text("INSERT INTO run_results (submission_id, status, passed, failed) VALUES (:s, 'failed', 0, 1)"),
            {"s": submission},
        )
        conn.execute(
            text("INSERT INTO explanation_checks (submission_id, check_name, passed, attempt) VALUES (:s, 'x', true, 1)"),
            {"s": submission},
        )
        conn.execute(
            text(
                "INSERT INTO explanation_cache (signature, problem_id, explanation_json, source_submission_id)"
                " VALUES (:g, :p, '{}', :s)"
            ),
            {"g": uuid.uuid4().hex, "p": course["problem_id"], "s": submission},
        )
        conn.execute(text("INSERT INTO chat_messages (user_id, role, content) VALUES (:u, 'user', 'hi')"), {"u": user_id})
        conn.execute(text("INSERT INTO diagnostic_sessions (user_id) VALUES (:u)"), {"u": user_id})
        conn.execute(text("INSERT INTO enrollments (user_id, course_id) VALUES (:u, :c)"), {"u": user_id, "c": course["id"]})
        conn.execute(
            text("INSERT INTO mastery (user_id, concept_id, p_known) VALUES (:u, :c, 0.4)"), {"u": user_id, "c": concept}
        )
        conn.execute(
            text(
                "INSERT INTO mastery_events (user_id, concept_id, p_before, p_after, evidence_type, rule_id, submission_id)"
                " VALUES (:u, :c, 0.3, 0.4, 'submission', 'r', :s)"
            ),
            {"u": user_id, "c": concept, "s": submission},
        )
        conn.execute(
            text("INSERT INTO misconception_state (user_id, misconception_id, probability) VALUES (:u, :m, 0.5)"),
            {"u": user_id, "m": misconception},
        )
    return submission


def rows_of(owner, user_id: int) -> dict[str, int]:
    """Row counts for this user in every table that has a user_id column, found from the schema."""
    with owner.connect() as conn:
        tables = conn.execute(
            text(
                "SELECT table_name FROM information_schema.columns WHERE table_schema = 'public'"
                " AND column_name = 'user_id' AND table_name <> 'erasure_requests'"
            )
        ).scalars().all()
        counts = {t: conn.execute(text(f"SELECT count(*) FROM {t} WHERE user_id = :u"), {"u": user_id}).scalar_one() for t in tables}
        counts["users"] = conn.execute(text("SELECT count(*) FROM users WHERE id = :u"), {"u": user_id}).scalar_one()
        counts["explanation_cache"] = conn.execute(
            text("SELECT count(*) FROM explanation_cache WHERE source_submission_id IN (SELECT id FROM submissions WHERE user_id = :u)"),
            {"u": user_id},
        ).scalar_one()
        return counts


def ask(client, headers, password=PASSWORD):
    return client.post(f"{API}/me/erasure", headers=headers, json={"password": password})


def test_a_request_needs_the_password_and_waits_at_least_48_hours(client, make_user, owner, course):
    user_id, headers = make_user("student")
    fill(owner, user_id, course)
    assert ask(client, headers, "wrong-password").status_code == 403
    assert client.get(f"{API}/me/erasure", headers=headers).json()["pending"] is False

    response = ask(client, headers)
    assert response.status_code == 201
    body = response.json()
    assert body["pending"] and body["kind"] == "requested"
    with owner.connect() as conn:
        hours = conn.execute(
            text("SELECT extract(epoch FROM due_at - notified_at) / 3600 FROM erasure_requests WHERE user_id = :u"),
            {"u": user_id},
        ).scalar_one()
    assert hours >= 48

    assert erasure.run_due(get_engine(), get_redis(), erase_mastery) == 0  # not due yet
    assert all(count > 0 for count in rows_of(owner, user_id).values())
    assert ask(client, headers).status_code == 409


def test_a_cancelled_request_never_runs(client, make_user, owner, course):
    user_id, headers = make_user("student")
    fill(owner, user_id, course)
    ask(client, headers)
    assert client.delete(f"{API}/me/erasure", headers=headers).json()["pending"] is False
    make_due(owner, user_id)
    assert erasure.run_due(get_engine(), get_redis(), erase_mastery) == 0
    assert all(count > 0 for count in rows_of(owner, user_id).values())


def test_erasure_removes_every_row_of_the_student_and_nobody_elses(client, make_user, owner, course):
    gone, headers = make_user("student")
    kept, _ = make_user("student")
    fill(owner, gone, course)
    fill(owner, kept, course)
    before = rows_of(owner, kept)
    assert {"mastery", "mastery_events", "misconception_state", "chat_messages", "submissions", "consents"} <= set(before)

    ask(client, headers)
    make_due(owner, gone)
    assert erasure.run_due(get_engine(), get_redis(), erase_mastery) >= 1

    assert {t: n for t, n in rows_of(owner, gone).items() if n} == {}
    assert rows_of(owner, kept) == before
    with owner.connect() as conn:
        record = conn.execute(
            text("SELECT status, completed_at FROM erasure_requests WHERE user_id = :u"), {"u": gone}
        ).one()
    assert record.status == "done" and record.completed_at is not None
    assert client.get(f"{API}/me/erasure", headers=headers).status_code == 401  # the account is gone


def test_a_student_who_withdrew_can_still_ask_for_deletion(client, make_user):
    _, headers = make_user("student")
    client.post(f"{API}/consent/withdraw", headers=headers)
    assert ask(client, headers).status_code == 201


def test_only_students_can_use_it_and_a_login_is_required(client, make_user):
    _, instructor = make_user("instructor")
    assert ask(client, instructor).status_code == 403
    assert client.get(f"{API}/me/erasure").status_code == 401
    assert client.post(f"{API}/me/erasure", json={"password": PASSWORD}).status_code == 401


def test_a_failure_halfway_changes_nothing_and_the_next_sweep_finishes(client, make_user, owner, course):
    user_id, headers = make_user("student")
    fill(owner, user_id, course)
    ask(client, headers)
    make_due(owner, user_id)

    def unavailable(_user_id):
        raise ConnectionError("mastery service down")

    assert erasure.run_due(get_engine(), get_redis(), unavailable) == 0
    assert all(count > 0 for count in rows_of(owner, user_id).values())
    assert client.get(f"{API}/me/erasure", headers=headers).json()["pending"] is True

    assert erasure.run_due(get_engine(), get_redis(), erase_mastery) >= 1
    assert {t: n for t, n in rows_of(owner, user_id).items() if n} == {}


def test_retention_asks_for_erasure_of_inactive_students_but_does_not_delete_yet(owner, make_user, course):
    idle, _ = make_user("student")
    active, _ = make_user("student")
    fill(owner, idle, course)
    fill(owner, active, course)
    with owner.begin() as conn:
        conn.execute(text("UPDATE users SET created_at = now() - interval '400 days' WHERE id = :u"), {"u": idle})
        conn.execute(text("UPDATE submissions SET created_at = now() - interval '400 days' WHERE user_id = :u"), {"u": idle})
        conn.execute(text("UPDATE chat_messages SET created_at = now() - interval '400 days' WHERE user_id = :u"), {"u": idle})
        conn.execute(text("UPDATE consents SET accepted_at = now() - interval '400 days' WHERE user_id = :u"), {"u": idle})
    with get_engine().begin() as conn:
        erasure.schedule_retention(conn, 365)
        assert erasure.status(conn, idle).kind == "retention"
        assert not erasure.status(conn, active).pending
        assert erasure.schedule_retention(conn, 365) == 0  # asking again adds nothing
    assert all(count > 0 for count in rows_of(owner, idle).values())


def test_no_role_can_delete_mastery_directly_and_only_the_mastery_role_can_call_the_function(owner, make_user):
    user_id, _ = make_user("student")
    mastery_db = create_engine(os.environ["MASTERY_DATABASE_URL"])
    api_db = get_engine()
    for statement in ("DELETE FROM mastery", "DELETE FROM mastery_events", "DELETE FROM misconception_state"):
        for db in (mastery_db, api_db):
            with pytest.raises(ProgrammingError, match="permission denied"):
                with db.begin() as conn:
                    conn.execute(text(statement))
    with mastery_db.begin() as conn:
        conn.execute(text("SELECT erase_user_mastery(:u)"), {"u": user_id})
    with pytest.raises(ProgrammingError, match="permission denied"):
        with api_db.begin() as conn:
            conn.execute(text("SELECT erase_user_mastery(:u)"), {"u": user_id})


def test_the_mastery_endpoint_needs_the_service_token(client):
    from fastapi.testclient import TestClient

    from app.mastery.main import app as mastery_app

    assert TestClient(mastery_app).post("/erase", json={"user_id": 0}).status_code == 401


def test_erasure_also_removes_the_students_copies_in_redis(client, make_user, owner, course):
    gone, headers = make_user("student")
    kept, _ = make_user("student")
    submission = fill(owner, gone, course)
    with owner.connect() as conn:
        session = conn.execute(text("SELECT id FROM diagnostic_sessions WHERE user_id = :u"), {"u": gone}).scalar_one()
    r = get_redis()
    theirs = [f"chat:{gone}:history", f"chat:{gone}:problem", f"explain:{submission}", f"probe:{submission}",
              f"hint:{gone}:{course['problem_id']}", f"diagnostic:{session}"]
    others = [f"chat:{kept}:history", f"hint:{kept}:{course['problem_id']}"]
    for key in theirs + others:
        r.set(key, "x", ex=600)

    ask(client, headers)
    make_due(owner, gone)
    erasure.run_due(get_engine(), r, erase_mastery)

    assert [k for k in theirs if r.exists(k)] == []
    assert all(r.exists(k) for k in others)
    r.delete(*others)
