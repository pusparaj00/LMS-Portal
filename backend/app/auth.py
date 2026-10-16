from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Connection, text

from app.config import get_settings
from app.db import get_engine

bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    encoded = password.encode()
    if len(encoded) > 72:  # bcrypt cannot have hashed it, so it cannot match
        return False
    return bcrypt.checkpw(encoded, password_hash.encode())


def create_token(user_id: int, role: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode(
        {"sub": str(user_id), "role": role, "iat": int(now.timestamp()), "exp": expires}, settings.jwt_secret, "HS256"
    )


# While a user must choose a new password, these are the only requests they can make.
PASSWORD_CHANGE_PATHS = {"/api/v1/me", "/api/v1/me/password"}


def get_conn() -> Iterator[Connection]:
    with get_engine().connect() as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


# "function" scope commits before the response is sent. The default ends the dependency after sending, so a client
# could act on a 201 before its row was committed, and a failed commit would follow a success reply.
Conn = Annotated[Connection, Depends(get_conn, scope="function")]


class CurrentUser:
    def __init__(self, id: int, role: str) -> None:
        self.id = id
        self.role = role


def current_user(
    request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)], conn: Conn
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(401, "authentication required")
    try:
        claims = jwt.decode(credentials.credentials, get_settings().jwt_secret, ["HS256"])
        user_id = int(claims["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(401, "invalid or expired token") from None
    # The role comes from the database, not the token, so a role change takes effect at once.
    row = conn.execute(
        text("SELECT role, disabled_at, must_change_password, credentials_changed_at FROM users WHERE id = :id"),
        {"id": user_id},
    ).first()
    if row is None:
        raise HTTPException(401, "unknown user")
    if row.disabled_at is not None:
        raise HTTPException(401, "this account is disabled; ask an administrator")
    # A token issued before the password last changed (or was reset) no longer counts: every old session ends.
    if row.credentials_changed_at is not None and claims.get("iat", 0) < int(row.credentials_changed_at.timestamp()):
        raise HTTPException(401, "you were signed out because your password changed; please log in again")
    request.state.user_id = user_id  # read by the request log and the audit trail (TR-S-08)
    if row.must_change_password and request.url.path not in PASSWORD_CHANGE_PATHS:
        raise HTTPException(403, "choose a new password first (Account in the top bar)")
    return CurrentUser(user_id, row.role)


def require_role(*roles: str):
    def check(user: Annotated[CurrentUser, Depends(current_user)]) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(403, "insufficient role")
        return user

    return check


def can_access_course(conn: Connection, user: CurrentUser, course_id: int) -> bool:
    """Admins see everything, instructors their own courses, students their enrolments."""
    if user.role == "admin":
        return True
    if user.role == "instructor":
        query = "SELECT 1 FROM courses WHERE id = :c AND instructor_id = :u"
    else:
        query = "SELECT 1 FROM enrollments WHERE course_id = :c AND user_id = :u"
    return conn.execute(text(query), {"c": course_id, "u": user.id}).first() is not None
