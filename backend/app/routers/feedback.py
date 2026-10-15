"""Verified feedback endpoints (F-41 to F-45, TR-P-03). Nothing here returns model text unverified."""
import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from app.auth import Conn, CurrentUser, can_access_course, require_role
from app.config import get_settings
from app.db import get_redis
from app.feedback import hints, probe
from app.feedback.context import ExplainContext, NotExplainable, load_context
from app.feedback.explain import Outcome, run_explain
from app.grading import TestSpec, grade
from app.llm.adapter import LLMAdapter, build_adapter
from app.mastery import client as mastery
from app.retrieval.store import Source
from app.sandbox import SandboxUnavailable
from app.schemas import (
    ExplainResponse,
    ExplanationOut,
    HintResponse,
    OptionOut,
    ProbeAnswerRequest,
    ProbeOut,
    ProbeResult,
    Problem,
    ProblemPolicy,
    SourceOut,
)

router = APIRouter(tags=["feedback"])
Student = Annotated[CurrentUser, Depends(require_role("student"))]
EXPLAIN_TTL_SECONDS = 24 * 3600


def llm_adapter() -> LLMAdapter:
    return build_adapter(get_settings())


def _context(conn, submission_id: int, user: CurrentUser) -> ExplainContext:
    try:
        return load_context(conn, submission_id, user.id)
    except NotExplainable as exc:
        raise HTTPException(404 if "not found" in str(exc) else 409, str(exc)) from None


def _source(s: Source) -> SourceOut:
    return SourceOut(chunk_id=s.chunk_id, title=s.title, section=s.section, text=s.text)


def _probe_out(p: probe.Probe | None) -> ProbeOut | None:
    if p is None:
        return None
    return ProbeOut(
        problem_id=p.problem_id, kind=p.kind, title=p.title, statement=p.statement,
        options=[OptionOut(id=i, text=t) for i, t in p.options],
    )


def _response(outcome: Outcome, offered: probe.Probe | None) -> ExplainResponse:
    explanation = None
    if outcome.explanation is not None:
        e = outcome.explanation
        explanation = ExplanationOut(
            claim=e.claim.strip(), line=e.line, concept=outcome.concept_name, hint_level=e.hint_level,
            sources=[_source(s) for s in outcome.sources],
        )
    return ExplainResponse(
        status=outcome.status, attempts=outcome.attempts, explanation=explanation,
        fallback_text=outcome.fallback_text,
        fallback_sources=[_source(s) for s in outcome.sources] if outcome.status == "fallback" else [],
        probe=_probe_out(offered),
    )


@router.post("/submissions/{submission_id}/explain", response_model=ExplainResponse)
def explain(
    submission_id: int, user: Student, conn: Conn, adapter: Annotated[LLMAdapter, Depends(llm_adapter)]
):
    """Runs generation and verification to completion before answering, so no unchecked text is ever shown."""
    redis = get_redis()
    cached = redis.get(f"explain:{submission_id}")
    ctx = _context(conn, submission_id, user)  # ownership is checked before anything stored is returned
    if cached:
        return ExplainResponse(**json.loads(cached))
    outcome = run_explain(conn, ctx, adapter, get_settings().retrieval_min_score)
    offered = probe.select_probe(conn, ctx)
    if offered is not None:
        probe.remember(redis, submission_id, offered.problem_id)
    response = _response(outcome, offered)
    redis.set(f"explain:{submission_id}", response.model_dump_json(), ex=EXPLAIN_TTL_SECONDS)
    return response


@router.post("/submissions/{submission_id}/hint", response_model=HintResponse)
def hint(submission_id: int, user: Student, conn: Conn):
    ctx = _context(conn, submission_id, user)
    max_level = conn.execute(
        text("SELECT max_hint_level FROM problems WHERE id = :p"), {"p": ctx.problem_id}
    ).scalar_one()
    try:
        level = hints.advance(get_redis(), user.id, ctx.problem_id, max_level)
    except hints.NoMoreHints as exc:
        raise HTTPException(409, str(exc)) from None
    return HintResponse(**vars(hints.hint_for_level(conn, ctx, level, max_level)))


@router.post("/probes/{problem_id}/answer", response_model=ProbeResult)
def answer_probe(problem_id: int, body: ProbeAnswerRequest, user: Student, conn: Conn):
    ctx = _context(conn, body.submission_id, user)
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
        except SandboxUnavailable:
            raise HTTPException(503, "sandbox unavailable, try again shortly") from None
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
