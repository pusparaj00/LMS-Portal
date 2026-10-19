"""What a student still has to do (F-78) and when things are due (F-79), from data the system already holds.

An assignment is done when its score is complete, or when it asks only for handed-in work and the work is turned in
(the instructor's grading is a separate step). Otherwise it is missing once the due time has passed and assigned before.
"""
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Connection, text

from app import grading_book

_ASSIGNMENTS = """
SELECT a.id, a.course_id, c.title AS course_title, a.title, a.due_at, a.due_at < now() AS past_due,
       (EXISTS (SELECT 1 FROM assignment_problems p WHERE p.assignment_id = a.id)
        OR EXISTS (SELECT 1 FROM assignment_quizzes q WHERE q.assignment_id = a.id)) AS has_auto,
       aw.assignment_id IS NOT NULL AS has_work, ws.status AS work_status
FROM enrollments e JOIN courses c ON c.id = e.course_id AND c.archived_at IS NULL
JOIN assignments a ON a.course_id = c.id
LEFT JOIN assignment_work aw ON aw.assignment_id = a.id
LEFT JOIN work_submissions ws ON ws.assignment_id = a.id AND ws.user_id = e.user_id
WHERE e.user_id = :u AND (CAST(:course AS integer) IS NULL OR c.id = :course)
ORDER BY a.due_at, a.id
"""


@dataclass(frozen=True)
class TodoItem:
    assignment_id: int
    course_id: int
    course_title: str
    title: str
    due_at: datetime
    state: str  # assigned, missing or done
    score: float
    possible: float
    has_work: bool


def items(conn: Connection, user_id: int, course_id: int | None = None) -> list[TodoItem]:
    rows = conn.execute(text(_ASSIGNMENTS), {"u": user_id, "course": course_id}).all()
    scores: dict[tuple[int, int], grading_book.Score] = {}
    for course in {r.course_id for r in rows}:
        for s in grading_book.scores(conn, course, only_student=user_id):
            scores[(course, s.assignment_id)] = s
    out = []
    for r in rows:
        s = scores.get((r.course_id, r.id))
        complete = s is not None and s.status == "complete"
        handed_in = r.has_work and not r.has_auto and r.work_status == "turned_in"
        state = "done" if complete or handed_in else "missing" if r.past_due else "assigned"
        out.append(TodoItem(
            assignment_id=r.id, course_id=r.course_id, course_title=r.course_title, title=r.title, due_at=r.due_at,
            state=state, score=s.score if s else 0.0, possible=s.possible if s else 0.0, has_work=r.has_work,
        ))
    return out
