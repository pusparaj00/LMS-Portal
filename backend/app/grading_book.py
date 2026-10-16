"""Assignment scores (F-04), computed from the stored run results every time they are read.

A problem scores its points times the fraction of tests (hidden ones included) its best on-time submission passed.
A submission at the due time exactly is on time. Late work is never counted in the score; `with_late` shows what the
score would be with late attempts, so the instructor can decide. No penalty is applied.
"""
from dataclasses import dataclass

from sqlalchemy import Connection, text

from app.synthetic import is_synthetic

# The rule itself is the database function assignment_scores (migration 0017), shared with the assistant's lms route.
_SCORES = """
SELECT s.student_id, u.email, u.display_name, s.assignment_id, s.score, s.with_late, s.possible,
       s.tried_on_time, s.tried_late, s.past_due
FROM assignment_scores(:c, CAST(:only AS integer)) s JOIN users u ON u.id = s.student_id
ORDER BY COALESCE(u.display_name, u.email), s.assignment_id
"""


def label(email: str, display_name: str | None) -> str:
    """How a teacher sees a student: their chosen name, else the part of their email before the @."""
    return display_name or email.split("@")[0]


@dataclass(frozen=True)
class Score:
    student_id: int
    label: str
    synthetic: bool
    assignment_id: int
    score: float
    with_late: float
    possible: float
    status: str


def status(score: float, with_late: float, possible: float, tried_on_time: bool, tried_late: bool,
           past_due: bool) -> str:
    """complete, in_progress, late (late work would raise the score), missing (due and never tried), not_started."""
    if score >= possible:
        return "complete"
    if tried_late and with_late > score:
        return "late"
    if tried_on_time or tried_late:
        return "in_progress"
    return "missing" if past_due else "not_started"


def scores(conn: Connection, course_id: int, only_student: int | None = None) -> list[Score]:
    rows = conn.execute(text(_SCORES), {"c": course_id, "only": only_student}).all()
    return [
        Score(
            student_id=r.student_id, label=label(r.email, r.display_name), synthetic=is_synthetic(r.email),
            assignment_id=r.assignment_id, score=round(r.score, 4), with_late=round(r.with_late, 4),
            possible=r.possible,
            status=status(r.score, r.with_late, r.possible, r.tried_on_time, r.tried_late, r.past_due),
        )
        for r in rows
    ]
