"""Instructor insight (F-90, F-91, F-92): at-risk alerts with their reasons, quiz question analysis, and a report that
sets lesson completion beside scores and mastery. Read-only, for a course's own teachers (and admins)."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app import insight
from app.auth import Conn, CurrentUser, can_access_course, require_role
from app.schemas import AtRiskReport, ContentReport, QuizReport

router = APIRouter(prefix="/courses/{course_id}", tags=["insight"])
Staff = Annotated[CurrentUser, Depends(require_role("instructor", "admin"))]


def _check(conn, user: CurrentUser, course_id: int) -> None:
    if not can_access_course(conn, user, course_id):
        raise HTTPException(403, "you have no access to this course")


@router.get("/at-risk", response_model=AtRiskReport)
def at_risk(course_id: int, user: Staff, conn: Conn):
    """Students with at least one warning sign, each with the facts that raised it, most signs first."""
    _check(conn, user, course_id)
    return insight.at_risk(conn, course_id)


@router.get("/quizzes/{quiz_id}/report", response_model=QuizReport)
def quiz_report(course_id: int, quiz_id: int, user: Staff, conn: Conn):
    _check(conn, user, course_id)
    report = insight.quiz_report(conn, course_id, quiz_id)
    if report is None:
        raise HTTPException(404, "quiz not found")
    return report


@router.get("/content-report", response_model=ContentReport)
def content_report(course_id: int, user: Staff, conn: Conn):
    """For each lesson item: how many students finished it and how those who did compare with those who did not. It is
    an association, not proof that the item made the difference."""
    _check(conn, user, course_id)
    return insight.content_report(conn, course_id)
