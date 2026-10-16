"""TR-A-09, F-70: LTI 1.3 launch, against a fake platform that signs launches with its own key and publishes its key
set over HTTP, so the tool fetches and checks keys exactly as it would from Moodle."""
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import lti
from app.config import get_settings
from app.db import get_engine
from app.main import app

API = "/api/v1"
ROLE = {
    "instructor": [lti.MEMBERSHIP + "Instructor"],
    "student": [lti.MEMBERSHIP + "Learner"],
    "observer": ["http://purl.imsglobal.org/vocab/lis/v2/membership#Mentor"],
}


def new_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def platform(owner):
    """A registered platform whose key set is served from a local HTTP server."""
    key, kid = new_key(), uuid.uuid4().hex
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    keys = {"keys": [{**public, "kid": kid, "alg": "RS256", "use": "sig"}]}

    class KeySet(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps(keys).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), KeySet)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    tag = uuid.uuid4().hex[:8]
    info = {
        "issuer": f"https://moodle-{tag}.test", "client_id": f"client-{tag}", "key": key, "kid": kid,
        "auth": f"https://moodle-{tag}.test/mod/lti/auth.php", "deployment": "1",
    }
    with get_engine().begin() as conn:
        info["id"] = lti.register_platform(
            conn, issuer=info["issuer"], client_id=info["client_id"], auth_login_url=info["auth"],
            jwks_url=f"http://127.0.0.1:{server.server_port}/certs", deployment_ids=[info["deployment"]],
        )
    yield info
    server.shutdown()
    with owner.begin() as conn:
        users = "SELECT user_id FROM lti_users WHERE platform_id = :p"
        courses = "SELECT course_id FROM lti_contexts WHERE platform_id = :p"
        for sql in (
            f"DELETE FROM enrollments WHERE course_id IN ({courses}) OR user_id IN ({users})",
            f"DELETE FROM consents WHERE user_id IN ({users})",
            "CREATE TEMP TABLE gone_users AS " + users,
            "CREATE TEMP TABLE gone_courses AS " + courses,
            "DELETE FROM lti_contexts WHERE platform_id = :p",
            "DELETE FROM lti_users WHERE platform_id = :p",
            "DELETE FROM courses WHERE id IN (SELECT course_id FROM gone_courses)",
            "DELETE FROM users WHERE id IN (SELECT user_id FROM gone_users)",
            "DELETE FROM lti_platforms WHERE id = :p",
        ):
            conn.execute(text(sql), {"p": info["id"]})


def base() -> str:
    return get_settings().tool_base_url.rstrip("/")


def start(client, platform, **changes):
    """The platform's login initiation; returns the state and nonce the tool sent to the platform."""
    params = {"iss": platform["issuer"], "login_hint": "hint", "target_link_uri": base() + "/",
              "client_id": platform["client_id"], "lti_message_hint": "msg", **changes}
    response = client.get(f"{API}/lti/login", params=params)
    assert response.status_code == 302, response.text
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert response.headers["location"].startswith(platform["auth"] + "?")
    assert query["redirect_uri"] == [base() + "/api/v1/lti/launch"] and query["response_mode"] == ["form_post"]
    assert query["lti_message_hint"] == ["msg"] and query["prompt"] == ["none"]
    return query["state"][0], query["nonce"][0]


def id_token(platform, nonce, *, sub="teacher-1", roles="instructor", context="ctx-1", key=None, **changes):
    now = int(time.time())
    claims = {
        "iss": platform["issuer"], "aud": platform["client_id"], "sub": sub, "iat": now, "exp": now + 300,
        "nonce": nonce,
        lti.CLAIM + "deployment_id": platform["deployment"],
        lti.CLAIM + "message_type": "LtiResourceLinkRequest",
        lti.CLAIM + "version": "1.3.0",
        lti.CLAIM + "target_link_uri": base() + "/",
        lti.CLAIM + "roles": ROLE[roles],
        lti.CLAIM + "context": {"id": context, "title": "Python 101 (Moodle)"},
        lti.CLAIM + "resource_link": {"id": "link-1"},
        "name": "Real Name", "email": "real.person@example.edu",
        **changes,
    }
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key or platform["key"], algorithm="RS256", headers={"kid": platform["kid"]})


def launch(client, platform, **token_args):
    state, nonce = start(client, platform)
    return client.post(f"{API}/lti/launch", data={"state": state, "id_token": id_token(platform, nonce, **token_args)})


def session(client, response):
    assert response.status_code == 303, response.text
    location = response.headers["location"]
    assert location.startswith(base() + "/#/lti/")
    return client.post(f"{API}/lti/session", json={"code": location.rsplit("/", 1)[1]})


@pytest.fixture
def browser():
    """A fresh browser: its own cookie jar, and redirects are inspected rather than followed."""
    return TestClient(app, follow_redirects=False)


def test_a_teacher_launch_creates_the_course_and_a_student_launch_enrols(browser, platform, owner):
    context = f"ctx-{uuid.uuid4().hex[:6]}"
    teacher = session(browser, launch(browser, platform, sub="t-1", context=context)).json()
    assert teacher["role"] == "instructor"
    course = teacher["course_id"]
    headers = {"Authorization": f"Bearer {teacher['access_token']}"}
    assert browser.get(f"{API}/courses/{course}/class-mastery", headers=headers).status_code == 200

    student = session(browser, launch(browser, platform, sub="s-1", roles="student", context=context)).json()
    assert student["role"] == "student" and student["course_id"] == course
    again = session(browser, launch(browser, platform, sub="s-1", roles="student", context=context)).json()
    with owner.connect() as conn:
        accounts = conn.execute(
            text("SELECT u.email FROM lti_users l JOIN users u ON u.id = l.user_id WHERE l.platform_id = :p"
                 " AND l.sub IN ('t-1', 's-1')"), {"p": platform["id"]},
        ).scalars().all()
        title = conn.execute(text("SELECT title FROM courses WHERE id = :c"), {"c": course}).scalar_one()
        enrolled = conn.execute(
            text("SELECT count(*) FROM enrollments WHERE course_id = :c"), {"c": course}
        ).scalar_one()
    assert again["course_id"] == course and len(accounts) == 2 and enrolled == 1
    assert all(a.endswith(lti.LTI_DOMAIN) and "real" not in a for a in accounts)  # no name or email kept
    assert title == "Python 101 (Moodle)"
    student_headers = {"Authorization": f"Bearer {student['access_token']}"}
    assert browser.get(f"{API}/consent", headers=student_headers).json()["accepted"] is False  # notice comes first


def refused(response, reason):
    assert response.status_code == 403, response.text
    assert lti.REFUSALS[reason] in response.text.replace("&#x27;", "'")


@pytest.mark.parametrize(
    ("token_args", "reason"),
    [
        ({"key": new_key()}, "invalid_token"),
        ({"iss": "https://elsewhere.test"}, "invalid_token"),
        ({"aud": "another-tool"}, "invalid_token"),
        ({"exp": int(time.time()) - 600}, "invalid_token"),
        ({"nonce": "not-the-nonce"}, "nonce_mismatch"),
        ({lti.CLAIM + "deployment_id": "99"}, "unknown_deployment"),
        ({lti.CLAIM + "message_type": "LtiDeepLinkingRequest"}, "unsupported_message"),
        ({lti.CLAIM + "version": "1.1"}, "unsupported_message"),
        ({lti.CLAIM + "target_link_uri": "https://evil.test/"}, "wrong_target"),
        ({lti.CLAIM + "context": None}, "no_context"),
        ({"roles": "observer"}, "unsupported_role"),
    ],
)
def test_a_launch_that_fails_any_check_is_refused_and_creates_nothing(browser, platform, owner, token_args, reason):
    sub = f"x-{uuid.uuid4().hex[:6]}"
    state, nonce = start(browser, platform)
    args = {"sub": sub, **token_args}
    if "nonce" in args:
        nonce = args.pop("nonce")
    response = browser.post(f"{API}/lti/launch", data={"state": state, "id_token": id_token(platform, nonce, **args)})
    refused(response, reason)
    with owner.connect() as conn:
        assert conn.execute(
            text("SELECT count(*) FROM lti_users WHERE platform_id = :p AND sub = :s"), {"p": platform["id"], "s": sub}
        ).scalar_one() == 0
        event = conn.execute(
            text("SELECT detail FROM audit_events WHERE event = 'lti.launch_refused' ORDER BY id DESC LIMIT 1")
        ).scalar_one()
    assert event["reason"] == reason


def test_a_launch_is_bound_to_the_browser_and_usable_once(browser, platform):
    state, nonce = start(browser, platform)
    token = id_token(platform, nonce, sub="once")
    stranger = TestClient(app, follow_redirects=False)  # same token and state, but not the browser that logged in
    refused(stranger.post(f"{API}/lti/launch", data={"state": state, "id_token": token}), "state_mismatch")
    first = browser.post(f"{API}/lti/launch", data={"state": state, "id_token": token})
    assert first.status_code == 303
    browser.cookies.set(lti.state_cookie_name(state), state, path="/api/v1/lti")
    refused(browser.post(f"{API}/lti/launch", data={"state": state, "id_token": token}), "state_unknown")

    code = first.headers["location"].rsplit("/", 1)[1]
    assert browser.post(f"{API}/lti/session", json={"code": code}).status_code == 200
    assert browser.post(f"{API}/lti/session", json={"code": code}).status_code == 404


def test_login_initiation_checks_the_platform_and_the_target(browser, platform):
    refused(browser.get(f"{API}/lti/login", params={"iss": "https://unknown.test", "login_hint": "h",
                                                     "target_link_uri": base() + "/"}), "unknown_platform")
    refused(browser.get(f"{API}/lti/login", params={"iss": platform["issuer"], "login_hint": "h",
                                                     "target_link_uri": "https://evil.test/"}), "wrong_target")
    refused(browser.get(f"{API}/lti/login", params={"iss": platform["issuer"]}), "missing_fields")
    form = {"iss": platform["issuer"], "login_hint": "h", "target_link_uri": base() + "/"}  # Moodle may POST it
    assert browser.post(f"{API}/lti/login", data=form).status_code == 302


def test_one_teacher_per_course_a_student_needs_the_course_first_and_roles_do_not_switch(browser, platform):
    context = f"ctx-{uuid.uuid4().hex[:6]}"
    refused(launch(browser, platform, sub="early", roles="student", context=context), "course_not_ready")
    session(browser, launch(browser, platform, sub="owner", context=context))
    refused(launch(browser, platform, sub="co-teacher", context=context), "second_instructor")
    session(browser, launch(browser, platform, sub="learner", roles="student", context=context))
    refused(launch(browser, platform, sub="learner", context=f"{context}-other"), "role_conflict")


def test_the_lms_account_domain_cannot_be_registered_directly(client):
    response = client.post(f"{API}/auth/register", json={"email": "x@lti.local", "password": "a-long-password"})
    assert response.status_code == 422
