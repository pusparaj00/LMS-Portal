"""Privacy notice, agreement and withdrawal (TR-S-05)."""
from typing import Annotated

from fastapi import APIRouter, Depends

from app import consent
from app.auth import Conn, CurrentUser, current_user, require_role
from app.schemas import ConsentAccept, ConsentNotice, ConsentStatus

router = APIRouter(prefix="/consent", tags=["consent"])
Student = Annotated[CurrentUser, Depends(require_role("student"))]


@router.get("/notice", response_model=ConsentNotice)
def read_notice(user: Annotated[CurrentUser, Depends(current_user)]):
    """The current notice, with the model providers that are actually configured."""
    return consent.current_notice()


@router.get("", response_model=ConsentStatus)
def my_consent(user: Student, conn: Conn):
    return consent.status(conn, user.id)


@router.post("/accept", response_model=ConsentStatus)
def accept(body: ConsentAccept, user: Student, conn: Conn):
    return consent.accept(conn, user.id, body.version, body.adult)


@router.post("/withdraw", response_model=ConsentStatus)
def withdraw(user: Student, conn: Conn):
    """From now on nothing of this student's is processed until they agree again."""
    return consent.withdraw(conn, user.id)
