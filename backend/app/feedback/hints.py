"""Hint ladder (F-45): concept hint, then location hint, then a worked example on a different problem.

The ladder is built from course notes, run evidence and the vetted bank only, so no level can contain
a full solution to the student's own problem.
"""
import re
from dataclasses import dataclass

import redis
from sqlalchemy import Connection, text

from app.feedback import leak
from app.feedback.context import ExplainContext
from app.retrieval import store

KEY_TTL_SECONDS = 7 * 24 * 3600
TRACEBACK_LINE = re.compile(r'File "[^"]*main\.py", line (\d+)')
JAVA_LINE = re.compile(r"\.java:(\d+)")
C_LINE = re.compile(r"\.c(?:pp)?:([0-9]+)")
LEVEL_KINDS = {1: "concept", 2: "location", 3: "example"}

_REPORTS = {"python": "Python reports", "java": "Java reports", "c": "The compiler reports"}
_CANNOT_READ = {
    "python": "Python could not read the program; start at the first line the error message names.",
    "java": "Java could not compile the program; start at the first line the error message names.",
    "c": "The compiler could not build the program; start at the first line the error message names.",
}


def _line_from_stderr(stderr: str, language: str) -> int | None:
    if language == "java":
        found = JAVA_LINE.findall(stderr)
    elif language == "c":
        found = C_LINE.findall(stderr)
    else:
        found = TRACEBACK_LINE.findall(stderr)
    return int(found[-1]) if found else None


class NoMoreHints(Exception):
    pass


@dataclass
class Hint:
    level: int
    max_level: int
    kind: str
    text: str
    source_title: str | None = None
    example_title: str | None = None
    example_solution: str | None = None


def advance(r: redis.Redis, user_id: int, problem_id: int, max_level: int) -> int:
    """One level per request, never past the problem's maximum."""
    key = f"hint:{user_id}:{problem_id}"
    level = int(r.incr(key))
    r.expire(key, KEY_TTL_SECONDS)
    if level > max_level:
        r.decr(key)
        raise NoMoreHints("you have used every hint for this problem")
    return level


def concept_hint(conn: Connection, ctx: ExplainContext) -> Hint:
    name = (ctx.primary_concept_name or "this topic").replace("_", " ")
    sources = store.search(
        conn, course_id=ctx.course_id, query=ctx.retrieval_query, k=3, min_score=-1.0,
        concept_id=ctx.primary_concept_id,
    )
    # Notes are shown as written, so one that holds this problem's solution (an instructor's worked example) is skipped.
    safe = [
        s for s in sources
        if not leak.copies_reference(s.text, ctx.reference_solution, ctx.leak_threshold, ctx.language)
    ]
    if not safe:
        return Hint(1, 3, "concept", f"Review the course notes on {name}.")
    return Hint(1, 3, "concept", safe[0].text, source_title=f"{safe[0].title} > {safe[0].section}")


def location_hint(ctx: ExplainContext) -> Hint:
    line = _line_from_stderr(ctx.stderr, ctx.language)
    categories = ", ".join(c.replace("_", " ") for c in ctx.failed_categories) or "the examples"
    if line:
        where = f"{_REPORTS.get(ctx.language, _REPORTS['python'])} the problem on line {line} of your code."
    elif ctx.error_type == "syntax_error":
        where = _CANNOT_READ.get(ctx.language, _CANNOT_READ["python"])
    else:
        where = "Your program runs, so trace it by hand on the smallest failing example."
    return Hint(2, 3, "location", f"{where} The tests that fail are in these categories: {categories}.")


def worked_example(conn: Connection, ctx: ExplainContext) -> Hint:
    """The reference solution of a *different* problem on the same concept, never a close copy of this one, and never
    one that is set in an assignment: that would hand over the answer to graded work (F-04). The problem shown is
    recorded, so it is never used afterwards to measure this student as a probe or a placement item."""
    rows = conn.execute(
        text(
            "SELECT p.id, p.title, p.statement, p.reference_solution FROM problems p"
            " JOIN problem_concepts pc ON pc.problem_id = p.id AND pc.concept_id = :c"
            " WHERE p.course_id = :course AND p.id <> :p AND p.kind = 'code' AND p.reference_solution IS NOT NULL"
            " AND NOT EXISTS (SELECT 1 FROM assignment_problems ap WHERE ap.problem_id = p.id)"
            " AND p.archived_at IS NULL"
            " ORDER BY p.difficulty_b, p.id"
        ),
        {"c": ctx.primary_concept_id, "course": ctx.course_id, "p": ctx.problem_id},
    ).all()
    for row in rows:
        if leak.containment(row.reference_solution, ctx.reference_solution, ctx.language) < ctx.leak_threshold:
            conn.execute(
                text(
                    "INSERT INTO worked_examples_seen (user_id, problem_id) VALUES (:u, :p)"
                    " ON CONFLICT DO NOTHING"
                ),
                {"u": ctx.user_id, "p": row.id},
            )
            return Hint(3, 3, "example", f"Here is a worked example on a different problem: {row.title}.",
                        example_title=row.title, example_solution=row.reference_solution)
    return Hint(3, 3, "example", "There is no worked example for this concept yet. Ask your instructor.")


def hint_for_level(conn: Connection, ctx: ExplainContext, level: int, max_level: int) -> Hint:
    builders = {
        1: lambda: concept_hint(conn, ctx),
        2: lambda: location_hint(ctx),
        3: lambda: worked_example(conn, ctx),
    }
    hint = builders[level]()
    hint.level, hint.max_level, hint.kind = level, max_level, LEVEL_KINDS[level]
    return hint
