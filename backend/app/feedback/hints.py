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
LEVEL_KINDS = {1: "concept", 2: "location", 3: "example"}


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
        conn, course_id=ctx.course_id, query=ctx.retrieval_query, k=1, min_score=-1.0,
        concept_id=ctx.primary_concept_id,
    )
    if not sources:
        return Hint(1, 3, "concept", f"Review the course notes on {name}.")
    return Hint(1, 3, "concept", sources[0].text, source_title=f"{sources[0].title} > {sources[0].section}")


def location_hint(ctx: ExplainContext) -> Hint:
    line = (TRACEBACK_LINE.findall(ctx.stderr) or [None])[-1]
    categories = ", ".join(c.replace("_", " ") for c in ctx.failed_categories) or "the examples"
    if line:
        where = f"Python reports the problem on line {line} of your code."
    elif ctx.error_type == "syntax_error":
        where = "Python could not read the program; start at the first line the error message names."
    else:
        where = "Your program runs, so trace it by hand on the smallest failing example."
    return Hint(2, 3, "location", f"{where} The tests that fail are in these categories: {categories}.")


def worked_example(conn: Connection, ctx: ExplainContext) -> Hint:
    """The reference solution of a *different* problem on the same concept, never a close copy of this one."""
    rows = conn.execute(
        text(
            "SELECT p.title, p.statement, p.reference_solution FROM problems p"
            " JOIN problem_concepts pc ON pc.problem_id = p.id AND pc.concept_id = :c"
            " WHERE p.course_id = :course AND p.id <> :p AND p.kind = 'code' AND p.reference_solution IS NOT NULL"
            " ORDER BY p.difficulty_b, p.id"
        ),
        {"c": ctx.primary_concept_id, "course": ctx.course_id, "p": ctx.problem_id},
    ).all()
    for row in rows:
        if leak.containment(row.reference_solution, ctx.reference_solution) < leak.SIMILARITY_THRESHOLD:
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
