from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import audit, ratelimit
from app.auth import Conn, create_token, hash_password, verify_password
from app.schemas import LoginRequest, RegisterRequest, TokenResponse
from app.synthetic import SYNTHETIC_DOMAIN

router = APIRouter(prefix="/auth", tags=["auth"])

# Checked when the email is unknown, so a login takes the same time either way.
_DUMMY_HASH = hash_password("dummy-password-for-timing")


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(body: RegisterRequest, request: Request, conn: Conn):
    """Self-registration always creates a student; staff accounts come from app.manage."""
    ratelimit.check("register_ip", ratelimit.client_ip(request))
    if body.email.lower().endswith(SYNTHETIC_DOMAIN):
        raise HTTPException(422, "this email domain is reserved for the labelled synthetic class")
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
    audit.record("auth.register", user_id=user_id, ip=ratelimit.client_ip(request), status=201)
    return TokenResponse(
        access_token=create_token(user_id, "student"), token_type="bearer", role="student"
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, conn: Conn):
    ratelimit.check("login_ip", ratelimit.client_ip(request))
    ratelimit.check("login_email", body.email.strip().lower()[:254])
    row = conn.execute(
        text("SELECT id, password_hash, role FROM users WHERE email = lower(:e)"), {"e": body.email}
    ).first()
    ip = ratelimit.client_ip(request)
    if row is None:
        verify_password(body.password, _DUMMY_HASH)
    if row is None or not verify_password(body.password, row.password_hash):
        audit.record(
            "auth.login_failed", user_id=row.id if row else None, ip=ip, status=401,
            detail={"email_tag": audit.email_tag(body.email), "known_account": row is not None},
        )
        raise HTTPException(401, "wrong email or password")
    audit.record("auth.login", user_id=row.id, ip=ip, status=200)
    return TokenResponse(
        access_token=create_token(row.id, row.role), token_type="bearer", role=row.role
    )
