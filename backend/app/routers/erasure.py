"""A student's request to delete their data, and the 48-hour notice before it happens (TR-S-07)."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from app import erasure, ratelimit
from app.auth import Conn, CurrentUser, require_role, verify_password
from app.schemas import ErasureRequest, ErasureStatus

router = APIRouter(prefix="/me/erasure", tags=["erasure"])
# Not the consented student: someone who withdrew must still be able to ask for deletion.
Student = Annotated[CurrentUser, Depends(require_role("student"))]


@router.get("", response_model=ErasureStatus)
def my_erasure(user: Student, conn: Conn):
    return erasure.status(conn, user.id)


@router.post("", response_model=ErasureStatus, status_code=201)
def request_erasure(body: ErasureRequest, user: Student, conn: Conn):
    """Schedules deletion of the whole account, its submissions, chat and mastery, 48 hours from now."""
    ratelimit.check("login_email", f"erase:{user.id}")
    if erasure.opened_from_lms(conn, user.id):
        # The account's password is random and unknown: the LMS sign-in is the proof, the confirmation the intent.
        if not body.confirm:
            raise HTTPException(422, "confirm that you want your data deleted")
    else:
        password_hash = conn.execute(
            text("SELECT password_hash FROM users WHERE id = :u"), {"u": user.id}
        ).scalar_one()
        if body.password is None or not verify_password(body.password, password_hash):
            raise HTTPException(403, "wrong password")
    if not erasure.request(conn, user.id, "requested"):
        raise HTTPException(409, "deletion is already scheduled")
    return erasure.status(conn, user.id)


@router.delete("", response_model=ErasureStatus)
def cancel_erasure(user: Student, conn: Conn):
    erasure.cancel(conn, user.id)
    return erasure.status(conn, user.id)
