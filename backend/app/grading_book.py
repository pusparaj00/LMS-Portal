"""Assignment scores (F-04), computed from the stored run results every time they are read.

A problem scores its points times the fraction of tests (hidden ones included) its best on-time submission passed.
A submission at the due time exactly is on time. Late work is never counted in the score; `with_late` shows what the
score would be with late attempts, so the instructor can decide. No penalty is applied.
"""
from dataclasses import dataclass

from sqlalchemy import Connection, text

from app.synthetic import is_synthetic

_SCORES = """
WITH items AS (
    SELECT a.id AS assignment_id, a.due_at, ap.problem_id, ap.points
    FROM assignments a JOIN assignment_problems ap ON ap.assignment_id = a.id WHERE a.course_id = :c
),
students AS (
    SELECT u.id, u.email, u.display_name FROM enrollments e JOIN users u ON u.id = e.user_id
    WHERE e.course_id = :c AND u.role = 'student' AND (CAST(:only AS integer) IS NULL OR u.id = :only)
),
attempts AS (
    SELECT i.assignment_id, i.problem_id, s.user_id,
           max(r.passed::float / NULLIF(r.passed + r.failed, 0)) FILTER (WHERE s.created_at <= i.due_at) AS on_time,
           max(r.passed::float / NULLIF(r.passed + r.failed, 0)) FILTER (WHERE s.created_at > i.due_at) AS late,
           bool_or(s.created_at <= i.due_at) AS tried_on_time,
           bool_or(s.created_at > i.due_at) AS tried_late
    FROM items i JOIN submissions s ON s.problem_id = i.problem_id JOIN run_results r ON r.submission_id = s.id
    WHERE s.user_id IN (SELECT id FROM students)
    GROUP BY i.assignment_id, i.problem_id, s.user_id
)
SELECT st.id AS student_id, st.email, st.display_name, i.assignment_id,
       sum(i.points * COALESCE(a.on_time, 0)) AS score,
       sum(i.points * GREATEST(COALESCE(a.on_time, 0), COALESCE(a.late, 0))) AS with_late,
       sum(i.points) AS possible,
       COALESCE(bool_or(a.tried_on_time), false) AS tried_on_time,
       COALESCE(bool_or(a.tried_late), false) AS tried_late,
       bool_and(now() > i.due_at) AS past_due
FROM students st CROSS JOIN items i
LEFT JOIN attempts a ON a.assignment_id = i.assignment_id AND a.problem_id = i.problem_id AND a.user_id = st.id
GROUP BY st.id, st.email, st.display_name, i.assignment_id
ORDER BY COALESCE(st.display_name, st.email), i.assignment_id
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
