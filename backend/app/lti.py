"""LTI 1.3 core launch (TR-A-09, F-70): a teacher or student opens this tool from Moodle (or another LTI platform).

The launch is the OpenID Connect third-party login of LTI 1.3 Core: the platform asks us to start a login, we send the
browser back with a one-time state and nonce, and the platform posts a signed id_token. Everything in the token is
checked before anything is created. Grade passback, roster sync and deep linking are not part of this step.
"""
import hashlib
import json
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import jwt
import redis
from sqlalchemy import Connection, text

from app import lti_grades
from app.auth import hash_password
from app.config import get_settings

CLAIM = "https://purl.imsglobal.org/spec/lti/claim/"
MEMBERSHIP = "http://purl.imsglobal.org/vocab/lis/v2/membership#"
INSTRUCTOR_ROLES = {MEMBERSHIP + "Instructor", MEMBERSHIP + "Administrator"}
LEARNER_ROLES = {MEMBERSHIP + "Learner"}
LTI_DOMAIN = "@lti.local"  # reserved: accounts made by a launch, never by self-registration
STATE_TTL_SECONDS = 600
CODE_TTL_SECONDS = 60
CLOCK_SKEW_SECONDS = 60

# What the person who launched sees, by reason. The reason itself goes to the audit trail.
REFUSALS = {
    "unknown_platform": "This LMS is not registered with the tool. Ask the administrator to register it.",
    "wrong_target": "The launch was for a different address than this tool.",
    "missing_fields": "The launch was incomplete. Open the tool again from your course.",
    "state_mismatch": "The launch could not be matched to this browser. Open the tool again from your course, "
                      "in a new window.",
    "state_unknown": "The launch has expired or was already used. Open the tool again from your course.",
    "keys_unavailable": "The LMS's signing keys could not be fetched. Try again shortly.",
    "invalid_token": "The launch was not correctly signed by the LMS.",
    "nonce_mismatch": "The launch could not be matched to the login it belongs to.",
    "nonce_reused": "This launch was already used. Open the tool again from your course.",
    "unknown_deployment": "This deployment of the tool is not registered. Ask the administrator.",
    "unsupported_message": "This kind of launch is not supported yet.",
    "no_context": "Open the tool from inside a course.",
    "unsupported_role": "Only teachers and students of the course can open this tool.",
    "role_conflict": "Your account here is set up with a different role. Ask the administrator.",
    "account_disabled": "Your account here has been disabled. Ask the administrator.",
    "course_not_ready": "Your teacher has not opened this tool in the course yet. Ask them to open it once first.",
    "second_instructor": "This course is already set up by another teacher, and only one teacher can manage it here.",
}


class LaunchRefused(Exception):
    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail

    @property
    def message(self) -> str:
        return REFUSALS[self.reason]


@dataclass(frozen=True)
class Platform:
    id: int
    issuer: str
    client_id: str
    auth_login_url: str
    jwks_url: str
    deployment_ids: list[str]


@dataclass(frozen=True)
class Launch:
    platform: Platform
    sub: str
    role: str
    context_id: str
    context_title: str
    grade_service: dict  # the Assignment and Grade Services endpoint claim, empty if the LMS offered none


_PLATFORM_COLUMNS = "id, issuer, client_id, auth_login_url, jwks_url, deployment_ids"


def _platform(row) -> Platform:
    return Platform(row.id, row.issuer, row.client_id, row.auth_login_url, row.jwks_url, list(row.deployment_ids))


def find_platform(conn: Connection, issuer: str, client_id: str | None) -> Platform | None:
    """By issuer and client id; a platform that omits the client id must then be the only one with that issuer."""
    rows = conn.execute(
        text(
            f"SELECT {_PLATFORM_COLUMNS} FROM lti_platforms"
            " WHERE issuer = :i AND (CAST(:c AS text) IS NULL OR client_id = :c)"
        ),
        {"i": issuer, "c": client_id},
    ).all()
    return _platform(rows[0]) if len(rows) == 1 else None


def register_platform(
    conn: Connection, *, issuer: str, client_id: str, auth_login_url: str, jwks_url: str, deployment_ids: list[str],
    token_url: str | None = None,
) -> int:
    return conn.execute(
        text(
            "INSERT INTO lti_platforms (issuer, client_id, auth_login_url, jwks_url, deployment_ids, token_url)"
            " VALUES (:i, :c, :a, :j, :d, :t) ON CONFLICT (issuer, client_id) DO UPDATE SET"
            " auth_login_url = excluded.auth_login_url, jwks_url = excluded.jwks_url,"
            " deployment_ids = excluded.deployment_ids, token_url = excluded.token_url RETURNING id"
        ),
        {"i": issuer, "c": client_id, "a": auth_login_url, "j": jwks_url, "d": deployment_ids, "t": token_url},
    ).scalar_one()


def is_this_tool(url: str, base_url: str) -> bool:
    """`base_url` itself or a path under it; a bare prefix test would accept https://tool.example.evil.test."""
    return url == base_url or url.startswith(base_url + "/") or url.startswith(base_url + "?")


def state_cookie_name(state: str) -> str:
    """One cookie per login in progress, so two launches in parallel do not overwrite each other's state."""
    return "lti_" + hashlib.sha256(state.encode()).hexdigest()[:16]


def start_login(conn: Connection, r: redis.Redis, params: dict[str, str], base_url: str) -> tuple[str, str]:
    """The platform's login initiation: returns where to send the browser, and the state to bind to it."""
    issuer, login_hint, target = params.get("iss"), params.get("login_hint"), params.get("target_link_uri")
    if not (issuer and login_hint and target):
        raise LaunchRefused("missing_fields")
    platform = find_platform(conn, issuer, params.get("client_id"))
    if platform is None:
        raise LaunchRefused("unknown_platform", issuer)
    if not is_this_tool(target, base_url):
        raise LaunchRefused("wrong_target", target)
    state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    r.set(f"lti:state:{state}", json.dumps({"platform_id": platform.id, "nonce": nonce}), ex=STATE_TTL_SECONDS)
    query = {
        "scope": "openid", "response_type": "id_token", "response_mode": "form_post", "prompt": "none",
        "client_id": platform.client_id, "redirect_uri": f"{base_url}/api/v1/lti/launch", "login_hint": login_hint,
        "state": state, "nonce": nonce,
    }
    if params.get("lti_message_hint"):
        query["lti_message_hint"] = params["lti_message_hint"]
    joiner = "&" if "?" in platform.auth_login_url else "?"
    return f"{platform.auth_login_url}{joiner}{urlencode(query)}", state


_key_sets: dict[str, jwt.PyJWKClient] = {}


def signing_key(jwks_url: str, token: str):
    client = _key_sets.get(jwks_url)
    if client is None:
        timeout = get_settings().lti_keys_timeout_s
        client = _key_sets[jwks_url] = jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=3600, timeout=timeout)
    try:
        return client.get_signing_key_from_jwt(token).key
    except jwt.PyJWKClientConnectionError as exc:
        raise LaunchRefused("keys_unavailable", str(exc)[:200]) from None
    except (jwt.PyJWKClientError, jwt.DecodeError) as exc:
        raise LaunchRefused("invalid_token", f"key: {str(exc)[:200]}") from None


def validate(
    conn: Connection, r: redis.Redis, form: dict[str, str], cookies: dict[str, str], base_url: str
) -> Launch:
    """Every check from LTI 1.3 Core's launch validation that applies to a resource link launch."""
    state, token = form.get("state"), form.get("id_token")
    if not state or not token:
        raise LaunchRefused("missing_fields")
    if cookies.get(state_cookie_name(state)) != state:
        raise LaunchRefused("state_mismatch")
    raw = r.getdel(f"lti:state:{state}")  # one use only, whatever happens next
    if raw is None:
        raise LaunchRefused("state_unknown")
    stored = json.loads(raw)
    row = conn.execute(
        text(f"SELECT {_PLATFORM_COLUMNS} FROM lti_platforms WHERE id = :p"), {"p": stored["platform_id"]}
    ).one()
    platform = _platform(row)

    try:
        claims = jwt.decode(
            token, signing_key(platform.jwks_url, token), algorithms=["RS256"], audience=platform.client_id,
            issuer=platform.issuer, leeway=CLOCK_SKEW_SECONDS,
            options={"require": ["exp", "iat", "iss", "aud", "sub", "nonce"]},
        )
    except jwt.InvalidTokenError as exc:
        raise LaunchRefused("invalid_token", f"{type(exc).__name__}: {str(exc)[:200]}") from None
    audiences = claims["aud"] if isinstance(claims["aud"], list) else [claims["aud"]]
    if len(audiences) > 1 and claims.get("azp") != platform.client_id:
        raise LaunchRefused("invalid_token", "azp does not name this tool")
    if claims["nonce"] != stored["nonce"]:
        raise LaunchRefused("nonce_mismatch")
    if not r.set(f"lti:nonce:{platform.id}:{claims['nonce']}", "1", nx=True, ex=STATE_TTL_SECONDS + 3600):
        raise LaunchRefused("nonce_reused")
    if claims.get(CLAIM + "deployment_id") not in platform.deployment_ids:
        raise LaunchRefused("unknown_deployment", str(claims.get(CLAIM + "deployment_id")))
    if claims.get(CLAIM + "message_type") != "LtiResourceLinkRequest" or claims.get(CLAIM + "version") != "1.3.0":
        kind = f"{claims.get(CLAIM + 'message_type')} {claims.get(CLAIM + 'version')}"
        raise LaunchRefused("unsupported_message", kind)
    if not is_this_tool(str(claims.get(CLAIM + "target_link_uri", "")), base_url):
        raise LaunchRefused("wrong_target", str(claims.get(CLAIM + "target_link_uri")))
    context = claims.get(CLAIM + "context") or {}
    if not context.get("id"):
        raise LaunchRefused("no_context")
    roles = set(claims.get(CLAIM + "roles") or [])
    if roles & INSTRUCTOR_ROLES:
        role = "instructor"
    elif roles & LEARNER_ROLES:
        role = "student"
    else:
        raise LaunchRefused("unsupported_role", " ".join(sorted(roles))[:200])
    title = str(context.get("title") or context.get("label") or "Course from the LMS")[:200]
    service = claims.get(lti_grades.ENDPOINT_CLAIM)
    service = service if isinstance(service, dict) else {}
    return Launch(platform, str(claims["sub"]), role, str(context["id"]), title, service)


def provision(conn: Connection, launch: Launch) -> tuple[int, int]:
    """The account and course for a launch, creating them on first use. Returns (user id, course id)."""
    p = launch.platform
    found = conn.execute(
        text(
            "SELECT u.id, u.role, u.disabled_at FROM lti_users l JOIN users u ON u.id = l.user_id"
            " WHERE l.platform_id = :p AND l.sub = :s"
        ),
        {"p": p.id, "s": launch.sub},
    ).first()
    if found is not None and found.disabled_at is not None:
        raise LaunchRefused("account_disabled")
    if found is not None and found.role != launch.role:
        raise LaunchRefused("role_conflict", f"account is {found.role}, launch says {launch.role}")
    course = conn.execute(
        text("SELECT c.id, c.instructor_id FROM lti_contexts x JOIN courses c ON c.id = x.course_id"
             " WHERE x.platform_id = :p AND x.context_id = :c"),
        {"p": p.id, "c": launch.context_id},
    ).first()
    if course is None and launch.role == "student":
        raise LaunchRefused("course_not_ready")

    if found is None:
        tag = hashlib.sha256(f"{p.issuer}|{launch.sub}".encode()).hexdigest()[:20]
        user_id = conn.execute(
            text("INSERT INTO users (email, password_hash, role) VALUES (:e, :h, :r) RETURNING id"),
            {"e": f"lti-{p.id}-{tag}{LTI_DOMAIN}", "h": hash_password(secrets.token_urlsafe(32)), "r": launch.role},
        ).scalar_one()
        conn.execute(
            text("INSERT INTO lti_users (platform_id, sub, user_id) VALUES (:p, :s, :u)"),
            {"p": p.id, "s": launch.sub, "u": user_id},
        )
    else:
        user_id = found.id

    if course is None:
        course_id = conn.execute(
            text("INSERT INTO courses (title, instructor_id) VALUES (:t, :u) RETURNING id"),
            {"t": launch.context_title, "u": user_id},
        ).scalar_one()
        conn.execute(
            text("INSERT INTO lti_contexts (platform_id, context_id, course_id) VALUES (:p, :c, :course)"),
            {"p": p.id, "c": launch.context_id, "course": course_id},
        )
        lti_grades.remember_service(conn, p.id, launch.context_id, launch.grade_service)
        return user_id, course_id
    if launch.role == "instructor":
        if course.instructor_id != user_id:
            raise LaunchRefused("second_instructor")
        lti_grades.remember_service(conn, p.id, launch.context_id, launch.grade_service)
    else:
        conn.execute(
            text("INSERT INTO enrollments (user_id, course_id) VALUES (:u, :c) ON CONFLICT DO NOTHING"),
            {"u": user_id, "c": course.id},
        )
    return user_id, course.id


def issue_code(r: redis.Redis, user_id: int, role: str, course_id: int) -> str:
    """A one-time code for the browser to swap for a session, so no token travels in a URL."""
    code = secrets.token_urlsafe(32)
    r.set(f"lti:code:{code}", json.dumps({"user_id": user_id, "role": role, "course_id": course_id}),
          ex=CODE_TTL_SECONDS)
    return code


def redeem_code(r: redis.Redis, code: str) -> dict | None:
    raw = r.getdel(f"lti:code:{code}")
    return json.loads(raw) if raw else None
