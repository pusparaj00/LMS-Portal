"""The verified explain and hint flows, shared by the feedback endpoints and the chat handlers.

Both callers get the same checks, so chat can never show model text the verifier has not passed.
"""
import json

from sqlalchemy import Connection, text

from app.config import get_settings
from app.db import get_redis
from app.feedback import demo_cache, hints, probe, signature_cache
from app.feedback.context import ExplainContext, load_context
from app.feedback.explain import Outcome, run_explain
from app.llm.adapter import LLMAdapter
from app.retrieval.store import Source
from app.schemas import ExplainResponse, ExplanationOut, HintResponse, OptionOut, ProbeOut, SourceOut

EXPLAIN_TTL_SECONDS = 24 * 3600


def source_out(s: Source) -> SourceOut:
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
            sources=[source_out(s) for s in outcome.sources],
            example_input=outcome.example.input if outcome.example else None,
            example_output=outcome.example.student_output if outcome.example else None,
        )
    return ExplainResponse(
        status=outcome.status, attempts=outcome.attempts, explanation=explanation,
        fallback_text=outcome.fallback_text,
        fallback_sources=[source_out(s) for s in outcome.sources] if outcome.status == "fallback" else [],
        probe=_probe_out(offered),
    )


def explain_submission(conn: Connection, user_id: int, submission_id: int, adapter: LLMAdapter) -> ExplainResponse:
    """Generate, verify and return an explanation; a repeat request returns the stored result."""
    redis = get_redis()
    ctx = load_context(conn, submission_id, user_id)  # raises NotExplainable unless it is the caller's failed run
    cached = redis.get(f"explain:{submission_id}")
    if cached:
        return ExplainResponse(**json.loads(cached))
    stored = demo_cache.serve(conn, ctx) or signature_cache.serve(conn, ctx)
    if stored is not None:
        response, offered = stored, probe.select_probe(conn, ctx)
        response.probe = _probe_out(offered)
    else:
        settings = get_settings()
        outcome = run_explain(conn, ctx, adapter, settings.retrieval_min_score, settings.explain_budget_s)
        if outcome.explanation is not None:
            signature_cache.store(conn, ctx, outcome.explanation, [s.chunk_id for s in outcome.sources])
        offered = probe.select_probe(conn, ctx)
        response = _response(outcome, offered)
    if offered is not None:
        probe.remember(redis, submission_id, offered.problem_id)
    redis.set(f"explain:{submission_id}", response.model_dump_json(), ex=EXPLAIN_TTL_SECONDS)
    return response


def next_hint(conn: Connection, user_id: int, submission_id: int) -> HintResponse:
    """One level per request, never past the problem's maximum (raises hints.NoMoreHints)."""
    ctx: ExplainContext = load_context(conn, submission_id, user_id)
    max_level = conn.execute(
        text("SELECT max_hint_level FROM problems WHERE id = :p"), {"p": ctx.problem_id}
    ).scalar_one()
    level = hints.advance(get_redis(), user_id, ctx.problem_id, max_level)
    return HintResponse(**vars(hints.hint_for_level(conn, ctx, level, max_level)))


def latest_failed_submission(conn: Connection, user_id: int, problem_id: int) -> int | None:
    return conn.execute(
        text(
            "SELECT s.id FROM submissions s JOIN run_results r ON r.submission_id = s.id"
            " WHERE s.user_id = :u AND s.problem_id = :p AND r.status <> 'passed' ORDER BY s.id DESC LIMIT 1"
        ),
        {"u": user_id, "p": problem_id},
    ).scalar()
