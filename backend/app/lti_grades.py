"""Sending gradebook scores to the LMS (LTI Assignment and Grade Services; TR-A-09, F-04).

The tool signs a request for an access token with its own key (the LMS checks it against /api/v1/lti/jwks), makes one
grade column per assignment, and posts each LMS student's on-time score. Only the on-time score is sent: the same
number this app's gradebook counts. Every URL called must be on the LMS's own address, so a launch cannot point the
server at anything else.
"""
import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import Connection, text

from app.config import get_settings

AGS = "https://purl.imsglobal.org/spec/lti-ags/"
ENDPOINT_CLAIM = AGS + "claim/endpoint"
SCOPE_LINEITEM = AGS + "scope/lineitem"
SCOPE_SCORE = AGS + "scope/score"
NEEDED_SCOPES = [SCOPE_LINEITEM, SCOPE_SCORE]
LINEITEM_TYPE = "application/vnd.ims.lis.v2.lineitem+json"
SCORE_TYPE = "application/vnd.ims.lis.v1.score+json"
TAG = "adaptive-lms"
PROGRESS = {
    "complete": "Completed", "in_progress": "InProgress", "late": "InProgress",
    "missing": "Initialized", "not_started": "Initialized",
}


class GradeSyncError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def new_tool_key() -> str:
    """A fresh private key for the tool, as the single line `.env` needs (base64 of the PEM)."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    return base64.b64encode(pem).decode()


@lru_cache
def _load(raw: str):
    key = serialization.load_pem_private_key(base64.b64decode(raw), password=None)
    der = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return key, hashlib.sha256(der).hexdigest()[:16]


def tool_key():
    raw = get_settings().lti_tool_private_key
    return _load(raw) if raw else None


def public_jwks() -> dict:
    """The tool's public key, which the LMS uses to check the tool's token requests. Empty until a key is set."""
    loaded = tool_key()
    if loaded is None:
        return {"keys": []}
    key, kid = loaded
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    return {"keys": [{**jwk, "kid": kid, "alg": "RS256", "use": "sig"}]}


def same_origin(url: str, reference: str) -> bool:
    a, b = urlsplit(url), urlsplit(reference)
    return (a.scheme, a.netloc) == (b.scheme, b.netloc) and a.scheme in ("http", "https")


def remember_service(conn: Connection, platform_id: int, context_id: str, endpoint: dict) -> None:
    """Keep the grade service the LMS offered at this launch (it may change between launches), to send grades later."""
    conn.execute(
        text("UPDATE lti_contexts SET ags_lineitems = :l, ags_scopes = :s WHERE platform_id = :p AND context_id = :c"),
        {"l": endpoint.get("lineitems"), "s": list(endpoint.get("scope") or []), "p": platform_id, "c": context_id},
    )


@dataclass
class Link:
    platform_id: int
    context_id: str
    client_id: str
    token_url: str | None
    lineitems: str | None
    scopes: list[str]


def link(conn: Connection, course_id: int) -> Link | None:
    row = conn.execute(
        text(
            "SELECT x.platform_id, x.context_id, p.client_id, p.token_url, x.ags_lineitems, x.ags_scopes"
            " FROM lti_contexts x JOIN lti_platforms p ON p.id = x.platform_id WHERE x.course_id = :c"
        ),
        {"c": course_id},
    ).first()
    return Link(row.platform_id, row.context_id, row.client_id, row.token_url, row.ags_lineitems,
                list(row.ags_scopes)) if row else None


def readiness(found: Link | None) -> str:
    """none: not opened from an LMS; not_allowed: the LMS gave no grade service; ready."""
    if found is None:
        return "none"
    if not found.lineitems or not found.token_url or not set(NEEDED_SCOPES) <= set(found.scopes):
        return "not_allowed"
    return "ready"


def _timeout() -> float:
    return get_settings().lti_keys_timeout_s


def access_token(found: Link) -> str:
    loaded = tool_key()
    if loaded is None:
        raise GradeSyncError(503, "the tool has no signing key yet; the administrator must set LTI_TOOL_PRIVATE_KEY")
    key, kid = loaded
    now = int(time.time())
    assertion = jwt.encode(
        {"iss": found.client_id, "sub": found.client_id, "aud": found.token_url, "iat": now, "exp": now + 300,
         "jti": secrets.token_urlsafe(16)},
        key, algorithm="RS256", headers={"kid": kid},
    )
    try:
        response = httpx.post(found.token_url, timeout=_timeout(), data={
            "grant_type": "client_credentials",
            "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
            "client_assertion": assertion, "scope": " ".join(NEEDED_SCOPES),
        })
        token = response.json().get("access_token") if response.status_code == 200 else None
    except (httpx.HTTPError, ValueError) as exc:
        raise GradeSyncError(502, f"the LMS could not be reached for a token: {type(exc).__name__}") from None
    if not token:
        raise GradeSyncError(502, f"the LMS refused the token request (HTTP {response.status_code})")
    return token


def _call(method: str, url: str, token: str, media: str, body: dict) -> httpx.Response:
    return httpx.request(method, url, timeout=_timeout(), content=json.dumps(body), headers={
        "Authorization": f"Bearer {token}", "Content-Type": media, "Accept": LINEITEM_TYPE,
    })


def scores_url(lineitem_url: str) -> str:
    """The scores endpoint is the line item's path plus /scores, keeping its query (Moodle puts the tool type there)."""
    parts = urlsplit(lineitem_url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/") + "/scores", parts.query, ""))


@dataclass
class SendResult:
    assignments: int = 0
    scores_sent: int = 0
    students_not_from_lms: int = 0
    failures: list[dict] = field(default_factory=list)


def _line_item(conn: Connection, found: Link, token: str, assignment, result: SendResult) -> str | None:
    row = conn.execute(
        text("SELECT lineitem_url, score_maximum FROM lti_line_items"
             " WHERE platform_id = :p AND context_id = :c AND assignment_id = :a"),
        {"p": found.platform_id, "c": found.context_id, "a": assignment.id},
    ).first()
    body = {"scoreMaximum": assignment.possible, "label": assignment.title, "resourceId": f"assignment-{assignment.id}",
            "tag": TAG}
    try:
        if row is None:
            response = _call("POST", found.lineitems, token, LINEITEM_TYPE, body)
            url = response.json().get("id") if response.status_code in (200, 201) else None
            if not url or not same_origin(url, found.token_url):
                raise GradeSyncError(502, f"the LMS did not create the grade column (HTTP {response.status_code})")
            conn.execute(
                text("INSERT INTO lti_line_items (platform_id, context_id, assignment_id, lineitem_url, score_maximum)"
                     " VALUES (:p, :c, :a, :u, :m)"),
                {"p": found.platform_id, "c": found.context_id, "a": assignment.id, "u": url, "m": assignment.possible},
            )
            return url
        if row.score_maximum != assignment.possible:  # points changed: the column's maximum must follow
            response = _call("PUT", row.lineitem_url, token, LINEITEM_TYPE, {**body, "id": row.lineitem_url})
            if response.status_code not in (200, 201):
                raise GradeSyncError(502, f"the LMS did not update the grade column (HTTP {response.status_code})")
            conn.execute(
                text("UPDATE lti_line_items SET score_maximum = :m"
                     " WHERE platform_id = :p AND context_id = :c AND assignment_id = :a"),
                {"m": assignment.possible, "p": found.platform_id, "c": found.context_id, "a": assignment.id},
            )
        return row.lineitem_url
    except (GradeSyncError, httpx.HTTPError, ValueError) as exc:
        result.failures.append({"assignment_id": assignment.id, "student_id": None, "error": str(exc)[:200]})
        return None


def send(conn: Connection, course_id: int, book) -> SendResult:
    """Post every LMS student's on-time score for every assignment. A failure is listed, never hidden."""
    found = link(conn, course_id)
    state = readiness(found)
    if state == "none":
        raise GradeSyncError(409, "this course was not opened from an LMS, so there is nowhere to send grades")
    if state == "not_allowed":
        raise GradeSyncError(409, "the LMS has not allowed this tool to send grades; turn on grade sync for the tool"
                                  " in the LMS and open the tool from the course again")
    if not same_origin(found.lineitems, found.token_url):
        raise GradeSyncError(409, "the LMS's grade service is not on the LMS's own address")
    token = access_token(found)
    subs = dict(conn.execute(
        text("SELECT user_id, sub FROM lti_users WHERE platform_id = :p"), {"p": found.platform_id}
    ).all())
    result = SendResult(students_not_from_lms=sum(1 for s in book.students if s.student_id not in subs))
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for assignment in book.assignments:
        url = _line_item(conn, found, token, assignment, result)
        if url is None:
            continue
        result.assignments += 1
        for row in book.students:
            if row.student_id not in subs:
                continue
            cell = next((c for c in row.cells if c.assignment_id == assignment.id), None)
            if cell is None:  # the assignment was not given to this student
                continue
            score = {"userId": subs[row.student_id], "scoreGiven": cell.score, "scoreMaximum": assignment.possible,
                     "activityProgress": PROGRESS[cell.status], "gradingProgress": "FullyGraded", "timestamp": stamp}
            try:
                response = _call("POST", scores_url(url), token, SCORE_TYPE, score)
                ok = response.status_code in (200, 201, 202, 204)
                error = None if ok else f"HTTP {response.status_code}"
            except httpx.HTTPError as exc:
                ok, error = False, type(exc).__name__
            if ok:
                result.scores_sent += 1
            else:
                result.failures.append({"assignment_id": assignment.id, "student_id": row.student_id, "error": error})
    return result
