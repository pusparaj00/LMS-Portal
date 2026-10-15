"""Failure-signature cache of verified explanations (F-46, TR-L-09, TR-V-11).

A verified explanation is stored under the signature of the failure: the problem, the sorted failed test categories,
the error type and the normalised error message. A later submission with the same signature gets the stored
explanation without a model call, but only if
  * the entry has not been rejected by an instructor,
  * the line it points at reads the same in the new code (same failure, different code must not get a wrong line),
  * and the verifier passes it again against the new submission's own evidence.
Otherwise the live flow runs. Every reuse is logged in explanation_checks with model `cache`.
"""
import hashlib
import json
import logging
import re

from sqlalchemy import Connection, text

from app.feedback.claim_check import ExampleRun, verify_with_example
from app.feedback.context import ExplainContext
from app.feedback.verifier import Check, Evidence, Explanation, all_passed
from app.schemas import ExplainResponse, ExplanationOut, SourceOut

log = logging.getLogger("app.feedback")
MODEL_LABEL = "cache"
PROMPT_LABEL = "cache-v1"
_PATH = re.compile(r'File "[^"]*"')
_NUMBER = re.compile(r"\d+")


def normalise_message(stderr: str) -> str:
    """The last error line without file paths or numbers, which differ between runs of the same mistake."""
    last = next((line for line in reversed(stderr.strip().splitlines()) if line.strip()), "")
    return " ".join(_NUMBER.sub("#", _PATH.sub("File", last)).split())


def signature(ctx: ExplainContext) -> str:
    key = [ctx.problem_id, sorted(ctx.failed_categories), ctx.error_type or "", normalise_message(ctx.stderr)]
    return hashlib.sha256(json.dumps(key).encode()).hexdigest()


def line_text(code: str, line: int) -> str | None:
    lines = code.splitlines()
    return " ".join(lines[line - 1].split()) if 1 <= line <= len(lines) else None


def store(conn: Connection, ctx: ExplainContext, explanation: Explanation, chunk_ids: list[int]) -> None:
    """Keep a verified explanation for later students with the same failure; the first one stored wins."""
    test = next((t for t in ctx.failed_tests if t.id == explanation.failing_test_id), None)
    if test is None:
        return
    payload = {
        "claim": explanation.claim.strip(), "line": explanation.line,
        "line_text": line_text(ctx.code, explanation.line),
        "concept_id": explanation.concept_id, "hint_level": explanation.hint_level, "test_category": test.category,
        "chunk_ids": chunk_ids, "example_input": explanation.example_input,
    }
    conn.execute(
        text(
            "INSERT INTO explanation_cache (signature, problem_id, explanation_json, source_submission_id)"
            " VALUES (:s, :p, CAST(:j AS jsonb), :sub) ON CONFLICT (signature) DO NOTHING"
        ),
        {"s": signature(ctx), "p": ctx.problem_id, "j": json.dumps(payload), "sub": ctx.submission_id},
    )


def check_against(
    conn: Connection, ctx: ExplainContext, payload: dict
) -> tuple[Explanation | None, list[Check], list[SourceOut], ExampleRun | None]:
    """Run the verifier on a stored explanation as if it had been written for this submission.

    A stored example input is tried again on THIS student's code, so a student whose program already handles it is not
    shown a claim that does not apply to them."""
    test = next((t for t in ctx.failed_tests if t.category == payload["test_category"]), None)
    if test is None:
        return None, [Check("test_exists", False, f"no failed test in category {payload['test_category']}")], [], None
    rows = conn.execute(
        text(
            "SELECT c.id, d.title, c.section, c.text FROM chunks c JOIN documents d ON d.id = c.document_id"
            " WHERE c.id = ANY(:ids) AND d.course_id = :course AND d.status = 'ready' ORDER BY c.id"
        ),
        {"ids": payload["chunk_ids"], "course": ctx.course_id},
    ).all()
    sources = [SourceOut(chunk_id=r.id, title=r.title, section=r.section, text=r.text) for r in rows]
    raw = json.dumps({
        "failing_test_id": test.id, "line": payload["line"], "concept_id": payload["concept_id"],
        "claim": payload["claim"], "source_chunk_ids": payload["chunk_ids"], "hint_level": payload["hint_level"],
        "example_input": payload.get("example_input", ""),
    })
    evidence = Evidence(
        code=ctx.code, reference_solution=ctx.reference_solution, failed_tests=ctx.failed_tests,
        error_concept_ids=ctx.error_concept_ids, retrieved_chunk_ids=frozenset(s.chunk_id for s in sources),
        hidden_inputs=ctx.hidden_inputs,
    )
    explanation, checks, example = verify_with_example(raw, evidence)
    return explanation, checks, sources, example


def serve(conn: Connection, ctx: ExplainContext) -> ExplainResponse | None:
    entry = conn.execute(
        text("SELECT id, explanation_json, status FROM explanation_cache WHERE signature = :s"), {"s": signature(ctx)}
    ).first()
    if entry is None or entry.status == "rejected":
        return None
    payload = entry.explanation_json
    if line_text(ctx.code, payload["line"]) != payload["line_text"]:
        return None
    explanation, checks, sources, example = check_against(conn, ctx, payload)
    if explanation is None or not all_passed(checks):
        log.info("stored explanation does not fit this submission", extra={"fields": {"entry": entry.id}})
        return None
    conn.execute(text("UPDATE explanation_cache SET hit_count = hit_count + 1 WHERE id = :i"), {"i": entry.id})
    final = Check("final", True, f"served from the failure-signature cache, entry {entry.id} ({entry.status})")
    for check in [*checks, final]:
        conn.execute(
            text(
                "INSERT INTO explanation_checks"
                " (submission_id, check_name, passed, attempt, model, prompt_version, detail)"
                " VALUES (:s, :n, :p, 0, :m, :v, :d)"
            ),
            {"s": ctx.submission_id, "n": check.name, "p": check.passed, "m": MODEL_LABEL, "v": PROMPT_LABEL,
             "d": check.detail or None},
        )
    return ExplainResponse(
        status="verified", attempts=0, cached=True, fallback_text=None, fallback_sources=[], probe=None,
        explanation=ExplanationOut(
            claim=payload["claim"], line=payload["line"], concept=ctx.concepts.get(payload["concept_id"], ""),
            hint_level=payload["hint_level"], sources=[s for s in sources if s.chunk_id in set(payload["chunk_ids"])],
            example_input=example.input if example else None,
            example_output=example.student_output if example else None,
        ),
    )
