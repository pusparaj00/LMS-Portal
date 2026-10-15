"""Verified feedback endpoints (F-41 to F-45, TR-P-03). Nothing here returns model text unverified."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from app import ratelimit
from app.auth import Conn, CurrentUser, can_access_course, require_role
from app.config import get_settings
from app.consent import consented_student
from app.db import get_redis
from app.errors import sandbox_error
from app.feedback import hints, probe, review, service
from app.feedback.context import NotExplainable, load_context
from app.grading import TestSpec, grade
from app.llm.adapter import LLMAdapter, build_adapter
from app.mastery import client as mastery
from app.sandbox import SandboxUnavailable
from app.schemas import (
    ExplainResponse,
    ExplanationDecision,
    HintResponse,
    ProbeAnswerRequest,
    ProbeResult,
    Problem,
    ProblemPolicy,
    StoredExplanation,
)

router = APIRouter(tags=["feedback"])
Student = Annotated[CurrentUser, Depends(consented_student)]


def llm_adapter() -> LLMAdapter:
    return build_adapter(get_settings())


def not_explainable(exc: NotExplainable) -> HTTPException:
    return HTTPException(404 if "not found" in str(exc) else 409, str(exc))


@router.post("/submissions/{submission_id}/explain", response_model=ExplainResponse)
def explain(
    submission_id: int, user: Student, conn: Conn, adapter: Annotated[LLMAdapter, Depends(llm_adapter)]
):
    """Runs generation and verification to completion before answering, so no unchecked text is ever shown."""
    ratelimit.check("explain", user.id)
    try:
        return service.explain_submission(conn, user.id, submission_id, adapter)
    except NotExplainable as exc:
        raise not_explainable(exc) from None


@router.post("/submissions/{submission_id}/hint", response_model=HintResponse)
def hint(submission_id: int, user: Student, conn: Conn):
    ratelimit.check("hint", user.id)
    try:
        return service.next_hint(conn, user.id, submission_id)
    except NotExplainable as exc:
        raise not_explainable(exc) from None
    except hints.NoMoreHints as exc:
        raise HTTPException(409, str(exc)) from None


@router.post("/probes/{problem_id}/answer", response_model=ProbeResult)
def answer_probe(problem_id: int, body: ProbeAnswerRequest, user: Student, conn: Conn):
    ratelimit.check("probe", user.id)
    try:
        ctx = load_context(conn, body.submission_id, user.id)
    except NotExplainable as exc:
        raise not_explainable(exc) from None
    if probe.offered(get_redis(), body.submission_id) != problem_id:
        raise HTTPException(409, "this is not the probe offered for that submission")
    kind = conn.execute(text("SELECT kind FROM problems WHERE id = :p"), {"p": problem_id}).scalar_one()
    option_id = None
    if kind == "mcq":
        if body.option_id is None:
            raise HTTPException(422, "choose one of the options")
        row = conn.execute(
            text("SELECT is_correct FROM item_options WHERE id = :o AND problem_id = :p"),
            {"o": body.option_id, "p": problem_id},
        ).first()
        if row is None:
            raise HTTPException(422, "that option does not belong to this probe")
        correct, option_id = bool(row.is_correct), body.option_id
    else:
        if body.code is None:
            raise HTTPException(422, "send your code")
        tests = [
            TestSpec(r.id, r.input, r.expected, r.hidden, r.category)
            for r in conn.execute(
                text("SELECT id, input, expected, hidden, category FROM test_cases WHERE problem_id = :p ORDER BY id"),
                {"p": problem_id},
            )
        ]
        try:
            correct = grade(body.code, tests).status == "passed"
        except SandboxUnavailable as exc:
            raise sandbox_error(exc) from None
    try:
        changes = mastery.record_answer(
            user_id=user.id, problem_id=problem_id, correct=correct,
            evidence_type="probe_mcq" if kind == "mcq" else "probe_code",
            evidence_ref=f"probe:{ctx.submission_id}:{problem_id}", option_id=option_id,
        )
    except mastery.MasteryUnavailable:
        raise HTTPException(503, "mastery service unavailable, try again shortly") from None
    return ProbeResult(correct=correct, mastery_changes=changes)


@router.put("/problems/{problem_id}/policy", response_model=Problem)
def set_policy(
    problem_id: int, body: ProblemPolicy, conn: Conn,
    user: Annotated[CurrentUser, Depends(require_role("instructor"))],
):
    from app.services import problems as repo

    problem = repo.get_problem(conn, problem_id)
    if problem is None or not can_access_course(conn, user, problem.course_id):
        raise HTTPException(404, "problem not found")
    conn.execute(
        text("UPDATE problems SET max_hint_level = :m WHERE id = :p"), {"m": body.max_hint_level, "p": problem_id}
    )
    return problem


@router.post("/explanations/{signature}/approve", response_model=StoredExplanation)
def decide_explanation(
    signature: str, body: ExplanationDecision, conn: Conn,
    user: Annotated[CurrentUser, Depends(require_role("instructor"))],
):
    """Approve a stored explanation, approve an edited claim, or reject it (F-62)."""
    try:
        return review.decide(conn, user, signature, body)
    except review.ReviewError as exc:
        raise HTTPException(exc.status, str(exc)) from None
