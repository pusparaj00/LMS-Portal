"""The signed-in user's own account (F-01, TR-S-01): profile name and password."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import Connection, text

from app import audit, ratelimit
from app.auth import Conn, CurrentUser, create_token, current_user, hash_password, verify_password
from app.schemas import Me, PasswordChange, ProfileUpdate, TokenResponse

router = APIRouter(prefix="/me", tags=["account"])
Signed = Annotated[CurrentUser, Depends(current_user)]


def me(conn: Connection, user_id: int) -> Me:
    row = conn.execute(
        text(
            "SELECT u.id, u.email, u.role, u.display_name, u.must_change_password,"
            " EXISTS (SELECT 1 FROM lti_users l WHERE l.user_id = u.id) AS opened_from_lms FROM users u WHERE u.id = :u"
        ),
        {"u": user_id},
    ).mappings().one()
    return Me(**row)


@router.get("", response_model=Me)
def read_me(user: Signed, conn: Conn):
    return me(conn, user.id)


@router.patch("", response_model=Me)
def update_profile(body: ProfileUpdate, user: Signed, conn: Conn):
    """The name teachers see in the class view and gradebook. It is never sent to the AI model (TR-S-06)."""
    name = body.display_name.strip() if body.display_name else None
    conn.execute(text("UPDATE users SET display_name = :n WHERE id = :u"), {"n": name or None, "u": user.id})
    return me(conn, user.id)


@router.post("/password", response_model=TokenResponse)
def change_password(body: PasswordChange, request: Request, user: Signed, conn: Conn):
    """Signs out every other session; the reply carries a fresh token so this one carries on."""
    ratelimit.check("login_email", f"password:{user.id}")
    if me(conn, user.id).opened_from_lms:
        raise HTTPException(409, "this account signs in through your LMS, so it has no password here")
    current = conn.execute(text("SELECT password_hash FROM users WHERE id = :u"), {"u": user.id}).scalar_one()
    if not verify_password(body.current_password, current):
        raise HTTPException(403, "the current password is wrong")
    if body.new_password == body.current_password:
        raise HTTPException(422, "choose a password different from the current one")
    conn.execute(
        text(
            "UPDATE users SET password_hash = :h, must_change_password = false,"
            " credentials_changed_at = date_trunc('second', now()) WHERE id = :u"
        ),
        {"h": hash_password(body.new_password), "u": user.id},
    )
    audit.record("account.password_changed", user_id=user.id, ip=ratelimit.client_ip(request), conn=conn)
    return TokenResponse(access_token=create_token(user.id, user.role), token_type="bearer", role=user.role)
