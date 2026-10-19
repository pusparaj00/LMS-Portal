"""Grading structure (F-87, F-88, F-89): grade categories, rubrics, and audited score overrides.

Categories and rubrics belong to a course and are managed by its teachers. An override replaces one student's score for
one assignment; it always carries a reason, the student sees both, and setting or removing it is written to the audit
trail."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import Connection, text

from app import audit, grading_book
from app.auth import Conn, CurrentUser, can_access_course, current_user, require_role
from app.schemas import (
    CategoryIn,
    CategoryOut,
    OverrideIn,
    RubricCriterionOut,
    RubricIn,
    RubricLevelOut,
    RubricOut,
)

router = APIRouter(prefix="/courses/{course_id}", tags=["grading"])
Instructor = Annotated[CurrentUser, Depends(require_role("instructor"))]
Member = Annotated[CurrentUser, Depends(current_user)]


def _check(conn: Connection, user: CurrentUser, course_id: int) -> None:
    if not can_access_course(conn, user, course_id):
        raise HTTPException(403, "you have no access to this course")


# ---- categories (F-87)

def _categories(conn: Connection, course_id: int) -> list[CategoryOut]:
    rows = conn.execute(
        text(
            "SELECT g.id, g.name, g.weight, (SELECT count(*) FROM assignments a WHERE a.category_id = g.id) AS n"
            " FROM grade_categories g WHERE g.course_id = :c ORDER BY g.position, g.id"
        ),
        {"c": course_id},
    ).all()
    total = sum(r.weight for r in rows)
    return [CategoryOut(id=r.id, name=r.name, weight=r.weight, share=round(r.weight / total * 100, 1) if total else 0,
                        assignments=r.n) for r in rows]


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(course_id: int, user: Member, conn: Conn):
    _check(conn, user, course_id)
    return _categories(conn, course_id)


@router.post("/categories", response_model=list[CategoryOut], status_code=201)
def add_category(course_id: int, body: CategoryIn, user: Instructor, conn: Conn):
    _check(conn, user, course_id)
    taken = conn.execute(
        text("SELECT 1 FROM grade_categories WHERE course_id = :c AND lower(name) = lower(:n)"),
        {"c": course_id, "n": body.name.strip()},
    ).first()
    if taken:
        raise HTTPException(409, "this course already has a category with that name")
    conn.execute(
        text(
            "INSERT INTO grade_categories (course_id, name, weight, position)"
            " VALUES (:c, :n, :w, (SELECT COALESCE(max(position) + 1, 0) FROM grade_categories WHERE course_id = :c))"
        ),
        {"c": course_id, "n": body.name.strip(), "w": body.weight},
    )
    return _categories(conn, course_id)


def _category(conn: Connection, course_id: int, category_id: int) -> None:
    if conn.execute(
        text("SELECT 1 FROM grade_categories WHERE id = :g AND course_id = :c"), {"g": category_id, "c": course_id}
    ).first() is None:
        raise HTTPException(404, "category not found")


@router.put("/categories/{category_id}", response_model=list[CategoryOut])
def change_category(course_id: int, category_id: int, body: CategoryIn, user: Instructor, conn: Conn):
    _check(conn, user, course_id)
    _category(conn, course_id, category_id)
    if conn.execute(
        text("SELECT 1 FROM grade_categories WHERE course_id = :c AND id <> :g AND lower(name) = lower(:n)"),
        {"c": course_id, "g": category_id, "n": body.name.strip()},
    ).first():
        raise HTTPException(409, "this course already has a category with that name")
    conn.execute(
        text("UPDATE grade_categories SET name = :n, weight = :w WHERE id = :g"),
        {"n": body.name.strip(), "w": body.weight, "g": category_id},
    )
    return _categories(conn, course_id)


@router.delete("/categories/{category_id}", response_model=list[CategoryOut])
def remove_category(course_id: int, category_id: int, user: Instructor, conn: Conn):
    """Its assignments stay and become uncategorised, so they stop counting in the weighted grade."""
    _check(conn, user, course_id)
    _category(conn, course_id, category_id)
    conn.execute(text("DELETE FROM grade_categories WHERE id = :g"), {"g": category_id})
    return _categories(conn, course_id)


# ---- score overrides (F-89)

def _assignment(conn: Connection, course_id: int, assignment_id: int):
    row = conn.execute(
        text(
            "SELECT a.id, a.title,"
            " (SELECT COALESCE(sum(points), 0) FROM assignment_problems WHERE assignment_id = a.id)"
            " + (SELECT COALESCE(sum(points), 0) FROM assignment_quizzes WHERE assignment_id = a.id)"
            " + (SELECT COALESCE(sum(points), 0) FROM assignment_work WHERE assignment_id = a.id) AS possible"
            " FROM assignments a WHERE a.id = :a AND a.course_id = :c"
        ),
        {"a": assignment_id, "c": course_id},
    ).first()
    if row is None:
        raise HTTPException(404, "assignment not found")
    return row


def _given(conn: Connection, assignment_id: int, student_id: int) -> bool:
    return conn.execute(
        text(
            "SELECT EXISTS (SELECT 1 FROM enrollments e JOIN users u ON u.id = e.user_id AND u.role = 'student'"
            " JOIN assignments a ON a.course_id = e.course_id WHERE a.id = :a AND e.user_id = :s"
            " AND (NOT EXISTS (SELECT 1 FROM assignment_students g WHERE g.assignment_id = a.id)"
            "  OR EXISTS (SELECT 1 FROM assignment_students g WHERE g.assignment_id = a.id AND g.user_id = e.user_id)))"
        ),
        {"a": assignment_id, "s": student_id},
    ).scalar_one()


@router.put("/assignments/{assignment_id}/students/{student_id}/override", status_code=204)
def set_override(course_id: int, assignment_id: int, student_id: int, body: OverrideIn, user: Instructor, conn: Conn):
    """Replaces the student's score for this assignment, on time and with late work alike, until it is removed."""
    _check(conn, user, course_id)
    assignment = _assignment(conn, course_id, assignment_id)
    if not _given(conn, assignment_id, student_id):
        raise HTTPException(404, "this assignment was not given to that student")
    if body.score > assignment.possible:
        raise HTTPException(422, f"the score cannot be more than the {assignment.possible:g} points it is worth")
    scored = {s.assignment_id: s for s in grading_book.scores(conn, course_id, only_student=student_id)}
    before = scored.get(assignment_id)
    conn.execute(
        text(
            "INSERT INTO score_overrides (assignment_id, user_id, score, reason, set_by) VALUES (:a, :u, :s, :r, :b)"
            " ON CONFLICT (assignment_id, user_id) DO UPDATE SET score = :s, reason = :r, set_by = :b, set_at = now()"
        ),
        {"a": assignment_id, "u": student_id, "s": body.score, "r": body.reason.strip(), "b": user.id},
    )
    audit.record("grade.overridden", user_id=user.id, status=204, conn=conn, detail={
        "course_id": course_id, "assignment_id": assignment_id, "student_id": student_id, "score": body.score,
        "was": before.score if before else None})
    return Response(status_code=204)


@router.delete("/assignments/{assignment_id}/students/{student_id}/override", status_code=204)
def remove_override(course_id: int, assignment_id: int, student_id: int, user: Instructor, conn: Conn):
    _check(conn, user, course_id)
    _assignment(conn, course_id, assignment_id)
    removed = conn.execute(
        text("DELETE FROM score_overrides WHERE assignment_id = :a AND user_id = :u RETURNING score"),
        {"a": assignment_id, "u": student_id},
    ).first()
    if removed is None:
        raise HTTPException(404, "there is no override to remove")
    audit.record("grade.override_removed", user_id=user.id, status=204, conn=conn, detail={
        "course_id": course_id, "assignment_id": assignment_id, "student_id": student_id, "was": removed.score})
    return Response(status_code=204)


# ---- rubrics (F-88)

def rubric_out(conn: Connection, rubric_id: int, chosen: dict[int, int] | None = None) -> RubricOut:
    head = conn.execute(
        text("SELECT id, title, (SELECT count(*) FROM assignment_work w WHERE w.rubric_id = r.id) AS used_by"
             " FROM rubrics r WHERE id = :r"),
        {"r": rubric_id},
    ).one()
    criteria = conn.execute(
        text("SELECT id, title, description FROM rubric_criteria WHERE rubric_id = :r ORDER BY position, id"),
        {"r": rubric_id},
    ).all()
    levels = conn.execute(
        text(
            "SELECT l.id, l.criterion_id, l.label, l.points FROM rubric_levels l"
            " JOIN rubric_criteria c ON c.id = l.criterion_id WHERE c.rubric_id = :r ORDER BY l.position, l.id"
        ),
        {"r": rubric_id},
    ).all()
    out = []
    for c in criteria:
        mine = [RubricLevelOut(id=lv.id, label=lv.label, points=lv.points) for lv in levels if lv.criterion_id == c.id]
        out.append(RubricCriterionOut(
            id=c.id, title=c.title, description=c.description, levels=mine,
            chosen_level_id=(chosen or {}).get(c.id),
        ))
    return RubricOut(
        id=head.id, title=head.title, used_by=head.used_by, criteria=out,
        max_points=sum(max(lv.points for lv in c.levels) for c in out),
    )


def _rubric(conn: Connection, course_id: int, rubric_id: int) -> None:
    if conn.execute(
        text("SELECT 1 FROM rubrics WHERE id = :r AND course_id = :c"), {"r": rubric_id, "c": course_id}
    ).first() is None:
        raise HTTPException(404, "rubric not found")


def _save_criteria(conn: Connection, rubric_id: int, body: RubricIn) -> None:
    for position, criterion in enumerate(body.criteria):
        criterion_id = conn.execute(
            text(
                "INSERT INTO rubric_criteria (rubric_id, position, title, description)"
                " VALUES (:r, :p, :t, :d) RETURNING id"
            ),
            {"r": rubric_id, "p": position, "t": criterion.title.strip(), "d": criterion.description},
        ).scalar_one()
        for level_position, level in enumerate(sorted(criterion.levels, key=lambda lv: -lv.points)):
            conn.execute(
                text("INSERT INTO rubric_levels (criterion_id, position, label, points) VALUES (:c, :p, :l, :x)"),
                {"c": criterion_id, "p": level_position, "l": level.label.strip(), "x": level.points},
            )


@router.get("/rubrics", response_model=list[RubricOut])
def list_rubrics(course_id: int, user: Instructor, conn: Conn):
    _check(conn, user, course_id)
    ids = conn.execute(text("SELECT id FROM rubrics WHERE course_id = :c ORDER BY id"), {"c": course_id}).scalars()
    return [rubric_out(conn, i) for i in list(ids)]


@router.post("/rubrics", response_model=RubricOut, status_code=201)
def create_rubric(course_id: int, body: RubricIn, user: Instructor, conn: Conn):
    _check(conn, user, course_id)
    rubric_id = conn.execute(
        text("INSERT INTO rubrics (course_id, title) VALUES (:c, :t) RETURNING id"),
        {"c": course_id, "t": body.title.strip()},
    ).scalar_one()
    _save_criteria(conn, rubric_id, body)
    return rubric_out(conn, rubric_id)


def _graded_with(conn: Connection, rubric_id: int) -> bool:
    return conn.execute(
        text("SELECT EXISTS (SELECT 1 FROM work_rubric_scores s JOIN rubric_criteria c ON c.id = s.criterion_id"
             " WHERE c.rubric_id = :r)"),
        {"r": rubric_id},
    ).scalar_one()


@router.put("/rubrics/{rubric_id}", response_model=RubricOut)
def change_rubric(course_id: int, rubric_id: int, body: RubricIn, user: Instructor, conn: Conn):
    """A rubric that has been used to grade work is locked, because every stored choice refers to its levels."""
    _check(conn, user, course_id)
    _rubric(conn, course_id, rubric_id)
    if _graded_with(conn, rubric_id):
        raise HTTPException(409, "work has been graded with this rubric, so it can no longer change; make a new one")
    top = sum(max(lv.points for lv in c.levels) for c in body.criteria)
    attached = conn.execute(
        text("SELECT points FROM assignment_work WHERE rubric_id = :r AND points <> :top"),
        {"r": rubric_id, "top": top},
    ).first()
    if attached is not None:
        raise HTTPException(
            409, f"an assignment using this rubric is worth {attached.points:g} points; keep the top score the same"
        )
    conn.execute(text("UPDATE rubrics SET title = :t WHERE id = :r"), {"t": body.title.strip(), "r": rubric_id})
    conn.execute(text("DELETE FROM rubric_criteria WHERE rubric_id = :r"), {"r": rubric_id})
    _save_criteria(conn, rubric_id, body)
    return rubric_out(conn, rubric_id)


@router.delete("/rubrics/{rubric_id}", status_code=204)
def delete_rubric(course_id: int, rubric_id: int, user: Instructor, conn: Conn):
    _check(conn, user, course_id)
    _rubric(conn, course_id, rubric_id)
    used = rubric_out(conn, rubric_id).used_by
    if used:
        raise HTTPException(409, "an assignment uses this rubric; take it off the assignment first")
    conn.execute(text("DELETE FROM rubrics WHERE id = :r"), {"r": rubric_id})
    return Response(status_code=204)
