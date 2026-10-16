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
    expires = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode(
        {"sub": str(user_id), "role": role, "exp": expires}, settings.jwt_secret, "HS256"
    )


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
    role = conn.execute(text("SELECT role FROM users WHERE id = :id"), {"id": user_id}).scalar()
    if role is None:
        raise HTTPException(401, "unknown user")
    request.state.user_id = user_id  # read by the request log and the audit trail (TR-S-08)
    return CurrentUser(user_id, role)


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
