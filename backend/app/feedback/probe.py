"""Probe questions (F-42, TR-L-10): one vetted bank item for the weak concept, graded here, sent to mastery."""
import json
import math
import random
from dataclasses import dataclass

import redis
from sqlalchemy import Connection, text

from app.feedback.context import ExplainContext

KEY_TTL_SECONDS = 24 * 3600
MIN_CONCEPT_WEIGHT = 0.5


@dataclass(frozen=True)
class Probe:
    problem_id: int
    kind: str
    title: str
    statement: str
    options: list[tuple[int, str]]


def _logit(p: float) -> float:
    p = min(0.99, max(0.01, p))
    return math.log(p / (1 - p))


def select_probe(conn: Connection, ctx: ExplainContext) -> Probe | None:
    """The unanswered bank item on the concept whose difficulty is closest to the student's current level."""
    if ctx.primary_concept_id is None:
        return None
    p_known = conn.execute(
        text(
            "SELECT COALESCE(m.p_known, c.prior) FROM concepts c"
            " LEFT JOIN mastery m ON m.concept_id = c.id AND m.user_id = :u WHERE c.id = :c"
        ),
        {"u": ctx.user_id, "c": ctx.primary_concept_id},
    ).scalar_one()
    rows = conn.execute(
        text(
            "SELECT p.id, p.kind, p.title, p.statement, p.difficulty_b FROM problems p"
            " JOIN problem_concepts pc ON pc.problem_id = p.id AND pc.concept_id = :c AND pc.weight >= :w"
            " WHERE p.course_id = :course AND p.id <> :cur AND p.archived_at IS NULL AND NOT EXISTS ("
            "   SELECT 1 FROM mastery_events e WHERE e.user_id = :u AND e.evidence_ref LIKE 'probe:%:' || p.id)"
            " AND NOT EXISTS (SELECT 1 FROM submissions s JOIN run_results r ON r.submission_id = s.id"
            "   WHERE s.user_id = :u AND s.problem_id = p.id AND r.status = 'passed')"
        ),
        {"c": ctx.primary_concept_id, "w": MIN_CONCEPT_WEIGHT, "course": ctx.course_id, "cur": ctx.problem_id,
         "u": ctx.user_id},
    ).all()
    if not rows:
        return None
    target = _logit(p_known)
    chosen = min(rows, key=lambda r: (abs(r.difficulty_b - target), r.id))
    options = [
        (o.id, o.option_text)
        for o in conn.execute(
            text("SELECT id, option_text FROM item_options WHERE problem_id = :p ORDER BY id"), {"p": chosen.id}
        )
    ]
    random.Random(f"{ctx.submission_id}:{chosen.id}").shuffle(options)
    return Probe(chosen.id, chosen.kind, chosen.title, chosen.statement, options)


def remember(r: redis.Redis, submission_id: int, problem_id: int) -> None:
    r.set(f"probe:{submission_id}", json.dumps({"problem_id": problem_id}), ex=KEY_TTL_SECONDS)


def offered(r: redis.Redis, submission_id: int) -> int | None:
    raw = r.get(f"probe:{submission_id}")
    return json.loads(raw)["problem_id"] if raw else None
