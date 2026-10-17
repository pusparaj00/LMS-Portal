from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Connection, text

from app import difficulty
from app.auth import Conn, CurrentUser, can_access_course, current_user, require_role
from app.errors import sandbox_error
from app.sandbox import SandboxUnavailable
from app.schemas import Problem, ProblemCreate, ProblemDetail, ProblemList, ProblemSource
from app.services import problems as repo
from app.services.validation import validate_code_problem

router = APIRouter(prefix="/problems", tags=["problems"])
Instructor = Annotated[CurrentUser, Depends(require_role("instructor"))]


@router.get("", response_model=ProblemList)
def list_problems(course_id: int, user: Annotated[CurrentUser, Depends(current_user)], conn: Conn):
    """Students see live problems only; staff also see archived ones, marked as such."""
    if not can_access_course(conn, user, course_id):
        raise HTTPException(403, "you have no access to this course")
    problems = repo.list_problems(conn, course_id, include_archived=user.role != "student")
    if user.role == "student":
        mine = repo.statuses_for(conn, user.id, course_id)
        for problem in problems:
            problem.my_status = mine.get(problem.id, "new")
    return ProblemList(problems=problems)


@router.get("/{problem_id}", response_model=ProblemDetail)
def get_problem(problem_id: int, user: Annotated[CurrentUser, Depends(current_user)], conn: Conn):
    problem = repo.get_problem(conn, problem_id)
    if problem is None or not can_access_course(conn, user, problem.course_id):
        raise HTTPException(404, "problem not found")
    if problem.archived and user.role == "student":
        raise HTTPException(404, "problem not found")
    return problem


def _validated(conn: Connection, body: ProblemCreate) -> tuple[list[dict], list[tuple[int, float]], list[str]]:
    """The checks every coding problem passes before it is saved (TR-D-04): concepts of this course, categories, and a
    reference solution that passes every test in the sandbox."""
    known = {
        r.id: r.name
        for r in conn.execute(text("SELECT id, name FROM concepts WHERE course_id = :c"), {"c": body.course_id})
    }
    names = [known.get(c.concept_id, f"#{c.concept_id}") for c in body.concepts]
    tests = [t.model_dump() for t in body.test_cases]
    try:
        errors = validate_code_problem(
            concept_names=names, known_concepts=set(known.values()), reference_solution=body.reference_solution,
            tests=tests,
        )
    except SandboxUnavailable as exc:
        raise sandbox_error(exc) from None
    if errors:
        raise HTTPException(422, "; ".join(errors))
    return tests, [(c.concept_id, c.weight) for c in body.concepts], names


def _difficulty(body: ProblemCreate, concept_names: list[str]) -> tuple[float, str]:
    """The teacher's choice, or an estimate from the text and the course's own concept names when it is empty (F-23)."""
    if body.difficulty_b is not None:
        return body.difficulty_b, "prior"
    try:
        value = difficulty.estimate(body.statement, body.reference_solution, concept_names)
    except difficulty.NoBank as exc:
        raise HTTPException(422, str(exc)) from None
    return value, "estimated"


def _title_taken(conn: Connection, course_id: int, title: str, other_than: int | None = None) -> None:
    taken = conn.execute(
        text("SELECT 1 FROM problems WHERE course_id = :c AND title = :t AND id IS DISTINCT FROM :p"),
        {"c": course_id, "t": title, "p": other_than},
    ).first()
    if taken:
        raise HTTPException(409, f"this course already has a problem called '{title}'")


@router.post("", response_model=Problem, status_code=201)
def create_problem(body: ProblemCreate, user: Instructor, conn: Conn):
    if not can_access_course(conn, user, body.course_id):
        raise HTTPException(403, "not your course")
    # save_problem replaces a same-titled problem (for re-importing the bank); here that would silently overwrite one.
    _title_taken(conn, body.course_id, body.title)
    tests, weights, names = _validated(conn, body)
    difficulty_b, source = _difficulty(body, names)
    problem_id, _ = repo.save_problem(
        conn,
        course_id=body.course_id,
        title=body.title,
        statement=body.statement,
        kind="code",
        difficulty_b=difficulty_b,
        discrimination_a=body.discrimination_a,
        param_source=source,
        reference_solution=body.reference_solution,
        concept_weights=weights,
        tests=tests,
        options=[],
    )
    return repo.get_problem(conn, problem_id)


def _own_problem(conn: Connection, user: CurrentUser, problem_id: int) -> Problem:
    problem = repo.get_problem(conn, problem_id)
    if problem is None or not can_access_course(conn, user, problem.course_id):
        raise HTTPException(404, "problem not found")
    return problem


@router.get("/{problem_id}/source", response_model=ProblemSource)
def problem_source(problem_id: int, user: Instructor, conn: Conn):
    """The full problem for its editor, hidden tests and reference solution included."""
    _own_problem(conn, user, problem_id)
    found = repo.source(conn, problem_id)
    if found is None:
        raise HTTPException(409, "only coding problems can be edited here; multiple-choice items come from the bank")
    return found


@router.put("/{problem_id}", response_model=Problem)
def edit_problem(problem_id: int, body: ProblemCreate, user: Instructor, conn: Conn):
    """Checked in the sandbox exactly like a new problem, then marked for review again. Past submissions keep the
    results they had."""
    problem = _own_problem(conn, user, problem_id)
    if problem.kind != "code":
        raise HTTPException(409, "only coding problems can be edited here; multiple-choice items come from the bank")
    if body.course_id != problem.course_id:
        raise HTTPException(422, "a problem cannot be moved to another course")
    _title_taken(conn, problem.course_id, body.title, other_than=problem_id)
    tests, weights, names = _validated(conn, body)
    difficulty_b, source = _difficulty(body, names)
    repo.update_code_problem(
        conn, problem_id, title=body.title, statement=body.statement, difficulty_b=difficulty_b,
        discrimination_a=body.discrimination_a, reference_solution=body.reference_solution, concept_weights=weights,
        tests=tests, param_source=source,
    )
    return repo.get_problem(conn, problem_id)


def _set(conn: Connection, problem_id: int, assignment: str) -> None:
    conn.execute(text(f"UPDATE problems SET {assignment} WHERE id = :p"), {"p": problem_id})


@router.post("/{problem_id}/archive", response_model=Problem)
def archive_problem(problem_id: int, user: Instructor, conn: Conn):
    """Hidden from students and never chosen again; submissions, history and existing assignments keep it."""
    _own_problem(conn, user, problem_id)
    _set(conn, problem_id, "archived_at = COALESCE(archived_at, now())")
    return repo.get_problem(conn, problem_id)


@router.post("/{problem_id}/restore", response_model=Problem)
def restore_problem(problem_id: int, user: Instructor, conn: Conn):
    _own_problem(conn, user, problem_id)
    _set(conn, problem_id, "archived_at = NULL")
    return repo.get_problem(conn, problem_id)


@router.post("/{problem_id}/review", response_model=Problem)
def mark_reviewed(problem_id: int, user: Instructor, conn: Conn):
    """The instructor has read the problem and its tests; this clears the 'needs human review' flag."""
    _own_problem(conn, user, problem_id)
    _set(conn, problem_id, "review_status = 'reviewed'")
    return repo.get_problem(conn, problem_id)
