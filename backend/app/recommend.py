"""The next problem and why, by one rule for the dashboard and the assistant (F-29, F-52, TR-M-17).

The rule itself is the database function next_step, so the two cannot drift apart.
"""
from dataclasses import dataclass

from sqlalchemy import Connection, text


@dataclass(frozen=True)
class Step:
    concept_id: int
    concept: str
    p: float
    problem_id: int
    title: str
    because_id: int | None  # the concept that builds on `concept`, when a weak prerequisite is revised first
    because: str | None
    because_p: float | None

    @property
    def reason(self) -> str:
        name = self.concept.replace("_", " ")
        if self.because is None:
            return f"{name} is your weakest area ({_pct(self.p)} mastery)"
        needs = self.because.replace("_", " ")
        return f"{name} ({_pct(self.p)}) comes before {needs}, which builds on it, so revise it first"


def _pct(p: float) -> str:
    return f"{round(p * 100)}%"


def next_step(conn: Connection, user_id: int, course_id: int) -> Step | None:
    row = conn.execute(
        text("SELECT * FROM next_step(:u, :c)"), {"u": user_id, "c": course_id}
    ).first()
    return Step(*row) if row else None
