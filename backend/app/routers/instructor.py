"""Instructor dashboard data (F-61, DRD section 10): the class mastery heatmap and misconception counts."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from app.auth import Conn, CurrentUser, can_access_course, require_role
from app.schemas import ClassMastery, ClassMisconception, ClassStudent, ConceptMastery
from app.synthetic import is_synthetic

router = APIRouter(prefix="/courses/{course_id}", tags=["instructor"])
Instructor = Annotated[CurrentUser, Depends(require_role("instructor", "admin"))]
SUSPECTED_ABOVE = 0.3  # the same threshold the student dashboard uses


def _check(conn, user: CurrentUser, course_id: int) -> None:
    if not can_access_course(conn, user, course_id):
        raise HTTPException(403, "not your course")


@router.get("/class-mastery", response_model=ClassMastery)
def class_mastery(course_id: int, user: Instructor, conn: Conn):
    _check(conn, user, course_id)
    concepts = conn.execute(
        text("SELECT id, name, prior FROM concepts WHERE course_id = :c ORDER BY id"), {"c": course_id}
    ).all()
    students = conn.execute(
        text(
            "SELECT u.id, u.email FROM enrollments e JOIN users u ON u.id = e.user_id"
            " WHERE e.course_id = :c AND u.role = 'student' ORDER BY u.email"
        ),
        {"c": course_id},
    ).all()
    known = {
        (r.user_id, r.concept_id): r.p_known
        for r in conn.execute(
            text(
                "SELECT m.user_id, m.concept_id, m.p_known FROM mastery m JOIN concepts c ON c.id = m.concept_id"
                " WHERE c.course_id = :c"
            ),
            {"c": course_id},
        )
    }
    rows = [
        ClassStudent(
            student_id=s.id,
            label=s.email.split("@")[0],
            synthetic=is_synthetic(s.email),
            mastery=[
                ConceptMastery(concept_id=c.id, name=c.name, p_known=known.get((s.id, c.id), c.prior))
                for c in concepts
            ],
        )
        for s in students
    ]
    averages = [
        ConceptMastery(
            concept_id=c.id,
            name=c.name,
            p_known=sum(r.mastery[i].p_known for r in rows) / len(rows) if rows else c.prior,
        )
        for i, c in enumerate(concepts)
    ]
    return ClassMastery(concepts=averages, students=rows)


@router.get("/misconceptions", response_model=list[ClassMisconception])
def misconceptions(course_id: int, user: Instructor, conn: Conn):
    _check(conn, user, course_id)
    rows = conn.execute(
        text(
            "SELECT m.name, m.description, c.name AS concept,"
            " count(*) FILTER (WHERE s.probability > :min) AS students,"
            " COALESCE(avg(s.probability), 0) AS mean_probability"
            " FROM misconceptions m JOIN concepts c ON c.id = m.concept_id"
            " LEFT JOIN misconception_state s ON s.misconception_id = m.id"
            " AND s.user_id IN (SELECT user_id FROM enrollments WHERE course_id = :course)"
            " WHERE c.course_id = :course GROUP BY m.id, c.name ORDER BY students DESC, mean_probability DESC, m.name"
        ),
        {"course": course_id, "min": SUSPECTED_ABOVE},
    ).mappings()
    return [ClassMisconception(**r) for r in rows]
