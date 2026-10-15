from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.auth import Conn, create_token, hash_password, verify_password
from app.schemas import LoginRequest, RegisterRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])

# Checked when the email is unknown, so a login takes the same time either way.
_DUMMY_HASH = hash_password("dummy-password-for-timing")


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(body: RegisterRequest, conn: Conn):
    """Self-registration always creates a student; staff accounts come from app.manage."""
    try:
        user_id = conn.execute(
            text(
                "INSERT INTO users (email, password_hash, role)"
                " VALUES (lower(:e), :h, 'student') RETURNING id"
            ),
            {"e": body.email, "h": hash_password(body.password)},
        ).scalar_one()
    except IntegrityError:
        raise HTTPException(409, "email already registered") from None
    return TokenResponse(
        access_token=create_token(user_id, "student"), token_type="bearer", role="student"
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, conn: Conn):
    row = conn.execute(
        text("SELECT id, password_hash, role FROM users WHERE email = lower(:e)"), {"e": body.email}
    ).first()
    if row is None:
        verify_password(body.password, _DUMMY_HASH)
        raise HTTPException(401, "wrong email or password")
    if not verify_password(body.password, row.password_hash):
        raise HTTPException(401, "wrong email or password")
    return TokenResponse(
        access_token=create_token(row.id, row.role), token_type="bearer", role=row.role
    )
