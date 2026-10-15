from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from app.auth import Conn, CurrentUser, can_access_course, current_user, require_role
from app.errors import sandbox_error
from app.sandbox import SandboxUnavailable
from app.schemas import Problem, ProblemCreate, ProblemDetail, ProblemList
from app.services import problems as repo
from app.services.validation import validate_code_problem

router = APIRouter(prefix="/problems", tags=["problems"])


@router.get("", response_model=ProblemList)
def list_problems(course_id: int, user: Annotated[CurrentUser, Depends(current_user)], conn: Conn):
    if not can_access_course(conn, user, course_id):
        raise HTTPException(403, "you have no access to this course")
    return ProblemList(problems=repo.list_problems(conn, course_id))


@router.get("/{problem_id}", response_model=ProblemDetail)
def get_problem(problem_id: int, user: Annotated[CurrentUser, Depends(current_user)], conn: Conn):
    problem = repo.get_problem(conn, problem_id)
    if problem is None or not can_access_course(conn, user, problem.course_id):
        raise HTTPException(404, "problem not found")
    return problem


@router.post("", response_model=Problem, status_code=201)
def create_problem(
    body: ProblemCreate,
    user: Annotated[CurrentUser, Depends(require_role("instructor"))],
    conn: Conn,
):
    if not can_access_course(conn, user, body.course_id):
        raise HTTPException(403, "not your course")
    known = {
        r.id: r.name
        for r in conn.execute(
            text("SELECT id, name FROM concepts WHERE course_id = :c"), {"c": body.course_id}
        )
    }
    names = [known.get(c.concept_id, f"#{c.concept_id}") for c in body.concepts]
    tests = [t.model_dump() for t in body.test_cases]
    try:
        errors = validate_code_problem(
            concept_names=names,
            known_concepts=set(known.values()),
            reference_solution=body.reference_solution,
            tests=tests,
        )
    except SandboxUnavailable as exc:
        raise sandbox_error(exc) from None
    if errors:
        raise HTTPException(422, "; ".join(errors))
    problem_id, _ = repo.save_problem(
        conn,
        course_id=body.course_id,
        title=body.title,
        statement=body.statement,
        kind="code",
        difficulty_b=body.difficulty_b,
        discrimination_a=body.discrimination_a,
        param_source="prior",
        reference_solution=body.reference_solution,
        concept_weights=[(c.concept_id, c.weight) for c in body.concepts],
        tests=tests,
        options=[],
    )
    return repo.get_problem(conn, problem_id)
