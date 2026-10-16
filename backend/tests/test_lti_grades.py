"""TR-A-09, F-04: sending gradebook scores to the LMS (LTI Assignment and Grade Services), against a fake LMS that
checks the tool's signed token request and records every grade column and score it receives."""
import json
import threading
import uuid
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import lti, lti_grades
from app.config import get_settings
from app.db import get_engine
from app.main import app
from tests.test_lti import id_token, new_key, session

API = "/api/v1"
ENDPOINT = lti_grades.ENDPOINT_CLAIM


@pytest.fixture
def tool_key(monkeypatch):
    raw = lti_grades.new_tool_key()
    monkeypatch.setattr(get_settings(), "lti_tool_private_key", raw)
    return raw


@pytest.fixture(scope="module")
def lms(owner):
    """A fake LMS on a local port: launch keys, token endpoint, grade columns and scores."""
    key, kid = new_key(), uuid.uuid4().hex
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    state = {"tokens": [], "columns": {}, "scores": [], "puts": [], "fail_scores_for": set()}

    class LMS(BaseHTTPRequestHandler):
        def _send(self, status, body=None):
            data = json.dumps(body).encode() if body is not None else b""
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)

        def _body(self):
            return self.rfile.read(int(self.headers.get("Content-Length", 0)))

        def _authorised(self):
            return self.headers.get("Authorization") == "Bearer lms-token"

        def do_GET(self):
            self._send(200, {"keys": [{**public, "kid": kid, "alg": "RS256", "use": "sig"}]})

        def do_POST(self):
            path = urlsplit(self.path)
            if path.path == "/token":
                form = {k: v[0] for k, v in parse_qs(self._body().decode()).items()}
                tool_public = lti_grades.public_jwks()["keys"]
                try:
                    signer = jwt.PyJWK(tool_public[0]).key
                    claims = jwt.decode(form["client_assertion"], signer, algorithms=["RS256"],
                                        audience=info["token_url"], issuer=info["client_id"])
                except Exception as exc:  # the tool's signature or claims are wrong
                    state["tokens"].append({"refused": str(exc)})
                    return self._send(401, {"error": "invalid_client"})
                state["tokens"].append({"claims": claims, "scope": form.get("scope")})
                return self._send(200, {"access_token": "lms-token", "token_type": "Bearer", "expires_in": 3600})
            if not self._authorised():
                return self._send(401, {"error": "no token"})
            if path.path == "/lineitems":
                body = json.loads(self._body())
                number = len(state["columns"]) + 1
                column = f"{info['base']}/lineitems/{number}/lineitem?type_id=1"
                state["columns"][column] = body
                return self._send(201, {**body, "id": column})
            if path.path.endswith("/scores"):
                body = json.loads(self._body())
                if body["userId"] in state["fail_scores_for"]:
                    return self._send(500, {"error": "boom"})
                state["scores"].append({"path": self.path, **body})
                return self._send(200, {})
            return self._send(404, {})

        def do_PUT(self):
            state["puts"].append({"path": self.path, **json.loads(self._body())})
            self._send(200, {})

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), LMS)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    tag = uuid.uuid4().hex[:8]
    info = {"base": base, "issuer": base, "client_id": f"client-{tag}", "key": key, "kid": kid,
            "auth": f"{base}/auth", "token_url": f"{base}/token", "deployment": "1", "state": state}
    with get_engine().begin() as conn:
        info["id"] = lti.register_platform(
            conn, issuer=base, client_id=info["client_id"], auth_login_url=info["auth"], jwks_url=f"{base}/certs",
            deployment_ids=["1"], token_url=info["token_url"],
        )
    yield info
    server.shutdown()
    with owner.begin() as conn:
        users = "SELECT user_id FROM lti_users WHERE platform_id = :p"
        courses = "SELECT course_id FROM lti_contexts WHERE platform_id = :p"
        for sql in (
            "CREATE TEMP TABLE g_users AS " + users,
            "CREATE TEMP TABLE g_courses AS " + courses,
            "DELETE FROM lti_line_items WHERE platform_id = :p",
            "DELETE FROM assignments WHERE course_id IN (SELECT course_id FROM g_courses)",
            "DELETE FROM mastery_events WHERE user_id IN (SELECT user_id FROM g_users)",
            "DELETE FROM mastery WHERE user_id IN (SELECT user_id FROM g_users)",
            "DELETE FROM misconception_state WHERE user_id IN (SELECT user_id FROM g_users)",
            "DELETE FROM concepts WHERE course_id IN (SELECT course_id FROM g_courses)",
            "DELETE FROM run_results WHERE submission_id IN (SELECT s.id FROM submissions s JOIN problems p"
            " ON p.id = s.problem_id WHERE p.course_id IN (SELECT course_id FROM g_courses))",
            "DELETE FROM submissions WHERE problem_id IN (SELECT id FROM problems WHERE course_id IN"
            " (SELECT course_id FROM g_courses))",
            "DELETE FROM problems WHERE course_id IN (SELECT course_id FROM g_courses)",
            "DELETE FROM enrollments WHERE course_id IN (SELECT course_id FROM g_courses)",
            "DELETE FROM consents WHERE user_id IN (SELECT user_id FROM g_users)",
            "DELETE FROM lti_contexts WHERE platform_id = :p",
            "DELETE FROM lti_users WHERE platform_id = :p",
            "DELETE FROM courses WHERE id IN (SELECT course_id FROM g_courses)",
            "DELETE FROM users WHERE id IN (SELECT user_id FROM g_users)",
            "DELETE FROM lti_platforms WHERE id = :p",
        ):
            conn.execute(text(sql), {"p": info["id"]})


def service(lms, lineitems=None, scope=None):
    return {"scope": scope or lti_grades.NEEDED_SCOPES, "lineitems": lineitems or f"{lms['base']}/lineitems?type_id=1"}


def launched(browser, lms, sub, role, context, grade_service):
    params = {"iss": lms["issuer"], "login_hint": "h", "target_link_uri": get_settings().tool_base_url + "/",
              "client_id": lms["client_id"]}
    location = browser.get(f"{API}/lti/login", params=params).headers["location"]
    nonce, state = parse_qs(urlsplit(location).query)["nonce"][0], parse_qs(urlsplit(location).query)["state"][0]
    extra = {ENDPOINT: grade_service} if grade_service is not None else {}
    token = id_token(lms, nonce, sub=sub, roles=role, context=context, **extra)
    body = session(browser, browser.post(f"{API}/lti/launch", data={"state": state, "id_token": token})).json()
    return body["course_id"], {"Authorization": f"Bearer {body['access_token']}"}


@pytest.fixture
def course(lms, owner):
    """An LMS course with a teacher, two LMS students, one coding problem and one assignment with points 2."""
    browser = TestClient(app, follow_redirects=False)
    context = f"ctx-{uuid.uuid4().hex[:6]}"
    course_id, teacher = launched(browser, lms, f"t-{context}", "instructor", context, service(lms))
    _, alice = launched(browser, lms, f"alice-{context}", "student", context, service(lms))
    _, bob = launched(browser, lms, f"bob-{context}", "student", context, service(lms))
    with owner.begin() as conn:
        problem = conn.execute(
            text("INSERT INTO problems (course_id, title, statement, kind, difficulty_b, discrimination_a)"
                 " VALUES (:c, 'Add one', 's', 'code', 0, 1) RETURNING id"), {"c": course_id},
        ).scalar_one()
        users = dict(conn.execute(
            text("SELECT sub, user_id FROM lti_users WHERE platform_id = :p AND sub LIKE :s"),
            {"p": lms["id"], "s": f"%{context}"},
        ).all())
        sid = conn.execute(
            text("INSERT INTO submissions (user_id, problem_id, code) VALUES (:u, :p, 'x') RETURNING id"),
            {"u": users[f"alice-{context}"], "p": problem},
        ).scalar_one()
        conn.execute(text("INSERT INTO run_results (submission_id, status, passed, failed) VALUES (:s, 'failed', 3, 1)"),
                     {"s": sid})
    made = browser.post(f"{API}/courses/{course_id}/assignments", headers=teacher, json={
        "title": "Week 1", "due_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        "problems": [{"problem_id": problem, "points": 2}],
    })
    assert made.status_code == 201, made.text
    return {"id": course_id, "teacher": teacher, "alice": f"alice-{context}", "bob": f"bob-{context}",
            "assignment": made.json(), "problem": problem, "context": context, "student": alice, "browser": browser}


def send(client, course):
    return client.post(f"{API}/courses/{course['id']}/gradebook/send", headers=course["teacher"])


def test_the_tool_publishes_its_public_key_only(client, tool_key):
    keys = client.get(f"{API}/lti/jwks").json()["keys"]
    assert len(keys) == 1 and keys[0]["alg"] == "RS256" and keys[0]["kid"]
    assert "d" not in keys[0] and "p" not in keys[0]  # no private parts
    assert tool_key not in json.dumps(keys)


def test_scores_reach_the_lms_once_per_student_and_columns_are_reused(client, lms, course, tool_key):
    before = len(lms["state"]["scores"])
    result = send(client, course).json()
    assert result == {"assignments": 1, "scores_sent": 2, "students_not_from_lms": 0, "failures": []}
    token = lms["state"]["tokens"][-1]
    assert token["claims"]["aud"] == lms["token_url"] and token["claims"]["iss"] == lms["client_id"]
    assert token["scope"] == " ".join(lti_grades.NEEDED_SCOPES)
    columns = [c for c, body in lms["state"]["columns"].items() if body["resourceId"] == f"assignment-{course['assignment']['id']}"]
    assert len(columns) == 1 and lms["state"]["columns"][columns[0]]["scoreMaximum"] == 2
    sent = {s["userId"]: s for s in lms["state"]["scores"][before:]}
    assert sent[course["alice"]]["scoreGiven"] == 1.5 and sent[course["alice"]]["activityProgress"] == "InProgress"
    assert sent[course["bob"]]["scoreGiven"] == 0 and sent[course["bob"]]["activityProgress"] == "Initialized"
    assert all(s["path"].startswith(urlsplit(columns[0]).path + "/scores?type_id=1") for s in sent.values())
    assert all(s["gradingProgress"] == "FullyGraded" and s["scoreMaximum"] == 2 for s in sent.values())

    again = send(client, course).json()  # the same column is used again
    assert again["scores_sent"] == 2 and len([c for c, b in lms["state"]["columns"].items()
                                              if b["resourceId"] == f"assignment-{course['assignment']['id']}"]) == 1
    a = course["assignment"]
    client.put(f"{API}/courses/{course['id']}/assignments/{a['id']}", headers=course["teacher"],
               json={"title": a["title"], "due_at": a["due_at"], "problems": [{"problem_id": course["problem"], "points": 4}]})
    send(client, course)
    assert lms["state"]["puts"][-1]["scoreMaximum"] == 4


def test_a_failed_score_is_listed_and_audited_not_hidden(client, lms, course, tool_key, owner):
    lms["state"]["fail_scores_for"].add(course["bob"])
    try:
        result = send(client, course).json()
    finally:
        lms["state"]["fail_scores_for"].discard(course["bob"])
    assert result["scores_sent"] == 1 and len(result["failures"]) == 1
    assert result["failures"][0]["error"] == "HTTP 500"
    with owner.connect() as conn:
        detail = conn.execute(text("SELECT detail FROM audit_events WHERE event = 'lti.grades_sent' ORDER BY id DESC LIMIT 1")).scalar_one()
    assert detail["failures"] == 1 and detail["course_id"] == course["id"]


def test_students_without_an_lms_account_are_counted_not_sent(client, course, make_user, tool_key):
    _, local = make_user("student")
    client.post(f"{API}/courses/{course['id']}/enroll", headers=local)
    result = send(client, course).json()
    assert result["students_not_from_lms"] == 1 and result["scores_sent"] == 2


def test_sending_is_refused_with_a_reason_when_it_cannot_work(client, lms, course, monkeypatch, owner, make_user):
    monkeypatch.setattr(get_settings(), "lti_tool_private_key", "")
    response = send(client, course)
    assert response.status_code == 503 and "LTI_TOOL_PRIVATE_KEY" in response.text
    monkeypatch.setattr(get_settings(), "lti_tool_private_key", lti_grades.new_tool_key())

    # the LMS offered no grade service at the last launch
    browser = course["browser"]
    launched(browser, lms, f"t-{course['context']}", "instructor", course["context"], None)
    assert client.get(f"{API}/courses/{course['id']}/gradebook", headers=course["teacher"]).json()["lms_grades"] == "not_allowed"
    assert send(client, course).status_code == 409

    # a grade service on another address is never called
    launched(browser, lms, f"t-{course['context']}", "instructor", course["context"],
             service(lms, lineitems="http://169.254.169.254/latest/lineitems"))
    refused = send(client, course)
    assert refused.status_code == 409 and "own address" in refused.text

    # a course that was not opened from an LMS
    teacher_id, teacher = make_user("instructor")
    plain = client.post(f"{API}/courses", headers=teacher, json={"title": "Plain"}).json()
    assert client.get(f"{API}/courses/{plain['id']}/gradebook", headers=teacher).json()["lms_grades"] == "none"
    assert client.post(f"{API}/courses/{plain['id']}/gradebook/send", headers=teacher).status_code == 409
    with owner.connect() as conn:
        reasons = conn.execute(text("SELECT count(*) FROM audit_events WHERE event = 'lti.grades_refused'"
                                    " AND (detail->>'course_id')::int = ANY(:c)"), {"c": [course["id"], plain["id"]]}).scalar_one()
    assert reasons >= 4


def test_only_the_courses_teacher_can_send(client, course, make_user, tool_key):
    _, other = make_user("instructor")
    assert client.post(f"{API}/courses/{course['id']}/gradebook/send", headers=course["student"]).status_code == 403
    assert client.post(f"{API}/courses/{course['id']}/gradebook/send", headers=other).status_code == 403
