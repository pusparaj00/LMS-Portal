"""The weighted overall grade (F-87).

A course with grade categories gets, for each student, the weighted mean of their category percentages. A category's
percentage is the on-time score over the points of the assignments in it that were given to that student. A category
with nothing given to the student yet is left out and the weights of the others are scaled up, so an empty category
does not pull the grade down. Assignments with no category are not part of it (the count is shown so that is never
hidden). A course with no categories has no weighted grade; its points total stays the course score.
"""
from collections.abc import Iterable

from sqlalchemy import Connection, text

from app.schemas import Overall, OverallPart


def categories(conn: Connection, course_id: int) -> list:
    return conn.execute(
        text("SELECT id, name, weight FROM grade_categories WHERE course_id = :c ORDER BY position, id"),
        {"c": course_id},
    ).all()


def assignment_categories(conn: Connection, course_id: int) -> dict[int, int | None]:
    return dict(conn.execute(
        text("SELECT id, category_id FROM assignments WHERE course_id = :c"), {"c": course_id}
    ).all())


def compute(
    cats: list, category_of: dict[int, int | None], lines: Iterable[tuple[int, float, float]]
) -> Overall | None:
    """`lines` are (assignment id, score, possible) for one student, only for assignments given to them."""
    if not cats:
        return None
    lines = list(lines)
    sums: dict[int, list[float]] = {c.id: [0.0, 0.0] for c in cats}
    uncategorised = 0
    for assignment_id, score, possible in lines:
        category = category_of.get(assignment_id)
        if category in sums:
            sums[category][0] += score
            sums[category][1] += possible
        else:
            uncategorised += 1
    parts = [
        OverallPart(
            category_id=c.id, name=c.name, weight=c.weight, score=round(sums[c.id][0], 4),
            possible=sums[c.id][1], percent=round(sums[c.id][0] / sums[c.id][1] * 100, 1),
        )
        for c in cats
        if sums[c.id][1] > 0
    ]
    total_weight = sum(p.weight for p in parts)
    percent = round(sum(p.weight * p.percent for p in parts) / total_weight, 1) if total_weight else None
    return Overall(percent=percent, parts=parts, uncategorised=uncategorised)
