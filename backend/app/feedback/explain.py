"""Verified explanations (F-40 to F-43, TR-L-03, TR-L-04, TR-L-11, TR-L-12).

An explanation reaches the student only after every check passes. After two failed attempts, or when the time budget
runs out (TR-P-03), the student gets a template hint instead. Nothing is shown or streamed before the verdict.
"""
import logging
import time
from dataclasses import dataclass, field

from sqlalchemy import Connection, text

from app.feedback import fallback
from app.feedback.claim_check import ExampleRun, verify_with_example
from app.feedback.context import ExplainContext
from app.feedback.prompt import PROMPT_VERSION, build_prompt
from app.feedback.verifier import JSON_SCHEMA, Check, Evidence, Explanation, all_passed
from app.llm.adapter import MIN_USEFUL_SECONDS, LLMAdapter, LLMError, deadline_within
from app.retrieval import store
from app.retrieval.store import Source

log = logging.getLogger("app.feedback")
MAX_ATTEMPTS = 2  # one try and one retry (TR-L-04, TR-P-08)
SOURCES_PER_QUESTION = 3
# Kept back from the model for checking its answer, the example run in the sandbox included (measured under 0.5 s).
CHECK_RESERVE_S = 1.5


@dataclass
class Outcome:
    status: str  # "verified" or "fallback"
    attempts: int
    explanation: Explanation | None = None
    concept_name: str | None = None
    sources: list[Source] = field(default_factory=list)
    fallback_text: str | None = None
    example: ExampleRun | None = None  # an input the sandbox showed the program to fail on (TR-L-05)


def retrieve(conn: Connection, ctx: ExplainContext, min_score: float) -> list[Source]:
    """Notes for the failing concept first, then any note in the course; none below the minimum score."""
    query = ctx.retrieval_query
    for concept_id in (ctx.primary_concept_id, None):
        found = store.search(
            conn, course_id=ctx.course_id, query=query, k=SOURCES_PER_QUESTION,
            min_score=min_score, concept_id=concept_id,
        )
        if found:
            return found
    return []


def log_checks(
    conn: Connection, submission_id: int, attempt: int, adapter: LLMAdapter, checks: list[Check]
) -> None:
    """Every attempt is stored with the model, prompt version and each check's verdict (TR-L-11)."""
    for check in checks:
        conn.execute(
            text(
                "INSERT INTO explanation_checks"
                " (submission_id, check_name, passed, attempt, model, prompt_version, detail)"
                " VALUES (:s, :n, :p, :a, :m, :v, :d)"
            ),
            {
                "s": submission_id, "n": check.name, "p": check.passed, "a": attempt,
                "m": adapter.config.model, "v": PROMPT_VERSION, "d": check.detail or None,
            },
        )


def run_explain(
    conn: Connection, ctx: ExplainContext, adapter: LLMAdapter, min_score: float, budget_s: float
) -> Outcome:
    started = time.monotonic()
    sources = retrieve(conn, ctx, min_score)
    evidence = Evidence(
        code=ctx.code, reference_solution=ctx.reference_solution, failed_tests=ctx.failed_tests,
        error_concept_ids=ctx.error_concept_ids, retrieved_chunk_ids=frozenset(s.chunk_id for s in sources),
        hidden_inputs=ctx.hidden_inputs, error_type=ctx.error_type, leak_threshold=ctx.leak_threshold,
        language=ctx.language,
    )
    previous: list[Check] | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        system, user = build_prompt(ctx, sources, previous)
        explanation: Explanation | None = None
        example: ExampleRun | None = None
        left = budget_s - (time.monotonic() - started) - CHECK_RESERVE_S
        if left < MIN_USEFUL_SECONDS:
            log_checks(conn, ctx.submission_id, attempt, adapter,
                       [Check("time_budget", False, f"{budget_s:g} s used up before attempt {attempt}")])
            break
        try:
            with deadline_within(left):
                raw = adapter.complete(system, user, JSON_SCHEMA)
            explanation, checks, example = verify_with_example(raw, evidence)
        except LLMError as exc:
            checks = [Check("llm_call", False, str(exc))]
        log_checks(conn, ctx.submission_id, attempt, adapter, checks)
        if explanation is not None and all_passed(checks):
            cited = [s for s in sources if s.chunk_id in set(explanation.source_chunk_ids)]
            log_checks(conn, ctx.submission_id, attempt, adapter, [Check("final", True, "verified")])
            return Outcome(
                "verified", attempt, explanation, ctx.concepts.get(explanation.concept_id), cited, example=example
            )
        previous = checks

    text_hint = fallback.template_hint(ctx.error_type, ctx.primary_concept_name, ctx.failed_categories, ctx.language)
    log_checks(conn, ctx.submission_id, MAX_ATTEMPTS, adapter, [Check("final", False, "fallback")])
    return Outcome("fallback", MAX_ATTEMPTS, concept_name=ctx.primary_concept_name, sources=sources[:1],
                   fallback_text=text_hint)
