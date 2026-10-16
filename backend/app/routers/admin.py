"""User administration for the admin role (F-01): find people, create staff, reset passwords, disable and change roles.

There is no email service, so a reset gives the admin a one-time temporary password to pass on; the user must replace
it at their next login. An admin cannot lock themselves out, and the last enabled admin cannot be removed.
"""
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from app import audit, ratelimit
from app.auth import Conn, CurrentUser, hash_password, require_role
from app.lti import LTI_DOMAIN
from app.schemas import AdminUser, RoleChange, StaffCreate, TemporaryPassword
from app.synthetic import SYNTHETIC_DOMAIN

router = APIRouter(prefix="/admin/users", tags=["admin"])
Admin = Annotated[CurrentUser, Depends(require_role("admin"))]
LIST_LIMIT = 200

_SELECT = (
    "SELECT u.id, u.email, u.role, u.display_name, u.disabled_at IS NOT NULL AS disabled, u.must_change_password,"
    " EXISTS (SELECT 1 FROM lti_users l WHERE l.user_id = u.id) AS opened_from_lms, u.created_at FROM users u"
)


def _one(conn: Connection, user_id: int) -> AdminUser:
    row = conn.execute(text(_SELECT + " WHERE u.id = :u"), {"u": user_id}).mappings().first()
    if row is None:
        raise HTTPException(404, "user not found")
    return AdminUser(**row)


def _temporary() -> str:
    return secrets.token_urlsafe(9)  # 12 characters; replaced at the next login


def _last_admin(conn: Connection, user: AdminUser) -> bool:
    if user.role != "admin" or user.disabled:
        return False
    others = conn.execute(
        text("SELECT count(*) FROM users WHERE role = 'admin' AND disabled_at IS NULL AND id <> :u"), {"u": user.id}
    ).scalar_one()
    return others == 0


@router.get("", response_model=list[AdminUser])
def list_users(user: Admin, conn: Conn, q: Annotated[str, Query(max_length=100)] = "",
               role: Annotated[str | None, Query(pattern="^(student|instructor|admin)$")] = None):
    """Matches email or name; synthetic demo students are left out. At most 200, newest first."""
    rows = conn.execute(
        text(
            _SELECT + " WHERE (u.email ILIKE :q OR u.display_name ILIKE :q)"
            " AND (CAST(:r AS text) IS NULL OR u.role = :r)"
            " AND u.email NOT LIKE :synthetic ORDER BY u.id DESC LIMIT :n"
        ),
        {"q": f"%{q.strip()}%", "r": role, "synthetic": f"%{SYNTHETIC_DOMAIN}", "n": LIST_LIMIT},
    ).mappings()
    return [AdminUser(**r) for r in rows]


@router.post("", response_model=TemporaryPassword, status_code=201)
def create_staff(body: StaffCreate, request: Request, user: Admin, conn: Conn):
    email = body.email.strip().lower()
    if "@" not in email or email.endswith((SYNTHETIC_DOMAIN, LTI_DOMAIN)):
        raise HTTPException(422, "give a real email address")
    password = _temporary()
    try:
        new_id = conn.execute(
            text(
                "INSERT INTO users (email, password_hash, role, display_name, must_change_password)"
                " VALUES (:e, :h, :r, :n, true) RETURNING id"
            ),
            {"e": email, "h": hash_password(password), "r": body.role, "n": body.display_name},
        ).scalar_one()
    except IntegrityError:
        raise HTTPException(409, "an account with that email already exists") from None
    audit.record("staff.created", user_id=new_id, ip=ratelimit.client_ip(request), conn=conn,
                 detail={"role": body.role, "via": "admin page", "by": user.id})
    return TemporaryPassword(user=_one(conn, new_id), temporary_password=password)


@router.post("/{user_id}/reset-password", response_model=TemporaryPassword)
def reset_password(user_id: int, request: Request, user: Admin, conn: Conn):
    """A one-time password for the admin to pass on in person; every existing session of that user ends."""
    target = _one(conn, user_id)
    if target.opened_from_lms:
        raise HTTPException(409, "this account signs in through the LMS, so it has no password here")
    password = _temporary()
    conn.execute(
        text(
            "UPDATE users SET password_hash = :h, must_change_password = true,"
            " credentials_changed_at = date_trunc('second', now()) WHERE id = :u"
        ),
        {"h": hash_password(password), "u": user_id},
    )
    audit.record("account.password_reset", user_id=user_id, ip=ratelimit.client_ip(request), conn=conn,
                 detail={"by": user.id})
    return TemporaryPassword(user=_one(conn, user_id), temporary_password=password)


@router.post("/{user_id}/disable", response_model=AdminUser)
def disable(user_id: int, request: Request, user: Admin, conn: Conn):
    """The account can no longer sign in and its sessions end. Its data is kept; enabling it restores access."""
    target = _one(conn, user_id)
    if user_id == user.id:
        raise HTTPException(409, "you cannot disable your own account")
    if _last_admin(conn, target):
        raise HTTPException(409, "this is the last enabled admin")
    conn.execute(text("UPDATE users SET disabled_at = COALESCE(disabled_at, now()) WHERE id = :u"), {"u": user_id})
    audit.record("account.disabled", user_id=user_id, ip=ratelimit.client_ip(request), conn=conn,
                 detail={"by": user.id})
    return _one(conn, user_id)


@router.post("/{user_id}/enable", response_model=AdminUser)
def enable(user_id: int, request: Request, user: Admin, conn: Conn):
    _one(conn, user_id)
    conn.execute(text("UPDATE users SET disabled_at = NULL WHERE id = :u"), {"u": user_id})
    audit.record("account.enabled", user_id=user_id, ip=ratelimit.client_ip(request), conn=conn, detail={"by": user.id})
    return _one(conn, user_id)


@router.patch("/{user_id}/role", response_model=AdminUser)
def change_role(user_id: int, body: RoleChange, request: Request, user: Admin, conn: Conn):
    """Takes effect at once: roles are read from the database on every request, not from the token."""
    target = _one(conn, user_id)
    if user_id == user.id:
        raise HTTPException(409, "you cannot change your own role")
    if body.role != "admin" and _last_admin(conn, target):
        raise HTTPException(409, "this is the last enabled admin")
    if target.opened_from_lms:
        raise HTTPException(409, "the LMS decides this account's role at each launch")
    conn.execute(text("UPDATE users SET role = :r WHERE id = :u"), {"r": body.role, "u": user_id})
    audit.record("account.role_changed", user_id=user_id, ip=ratelimit.client_ip(request), conn=conn,
                 detail={"from": target.role, "to": body.role, "by": user.id})
    return _one(conn, user_id)
