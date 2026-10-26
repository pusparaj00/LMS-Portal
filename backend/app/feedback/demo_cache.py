"""Cached demo explanations (TR-P-07, TR-L-12): the demo keeps working with the model switched off.

`data/demo/explanations.json` holds explanations that the real verified flow produced once for the scripted demo
submissions. When a student submits exactly that code, the cached explanation is used, but it is NOT trusted blindly:
it is checked again by the same verifier against this submission's own run evidence, and it is labelled `cached` in the
API response, in the interface and in explanation_checks. If anything does not match, the normal live flow runs.
It is separate from the failure-signature cache of F-46 (app.feedback.signature_cache) and is tried first.
"""
import hashlib
import json
import logging
import os
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Connection, text

from app.feedback.context import ExplainContext
from app.feedback.verifier import Evidence, all_passed, verify
from app.schemas import ExplainResponse, ExplanationOut, SourceOut

log = logging.getLogger("app.feedback")
MODEL_LABEL = "cached-demo"
PROMPT_LABEL = "demo-v1"


def _directory() -> Path | None:
    configured = os.environ.get("DEMO_CACHE_DIR")
    if configured is not None:
        return Path(configured) if configured else None
    for candidate in (Path("/srv/data/demo"), Path(__file__).resolve().parents[3] / "data" / "demo"):
        if candidate.exists():
            return candidate
    return None


def code_key(code: str) -> str:
    normalised = "\n".join(line.rstrip() for line in code.strip().splitlines())
    return hashlib.sha256(normalised.encode()).hexdigest()


@lru_cache
def _entries() -> dict[tuple[str, str], dict]:
    directory = _directory()
    path = directory / "explanations.json" if directory else None
    if path is None or not path.exists():
        return {}
    return {(e["problem"], code_key(e["code"])): e for e in json.loads(path.read_text(encoding="utf-8"))["entries"]}


def _sources(conn: Connection, ctx: ExplainContext, refs: list[dict]) -> list[SourceOut]:
    found = []
    for ref in refs:
        row = conn.execute(
            text(
                "SELECT c.id, c.text FROM chunks c JOIN documents d ON d.id = c.document_id"
                " WHERE d.course_id = :course AND d.title = :t AND c.section = :s AND d.status = 'ready' LIMIT 1"
            ),
            {"course": ctx.course_id, "t": ref["title"], "s": ref["section"]},
        ).first()
        if row:
            found.append(SourceOut(chunk_id=row.id, title=ref["title"], section=ref["section"], text=row.text))
    return found


def serve(conn: Connection, ctx: ExplainContext) -> ExplainResponse | None:
    """The cached explanation for this exact code, if it still verifies against this submission's evidence."""
    entry = _entries().get((ctx.problem_title, code_key(ctx.code)))
    if entry is None or not ctx.failed_tests:
        return None
    concept_id = next((cid for cid, name in ctx.concepts.items() if name == entry["concept"]), None)
    if concept_id is None:
        return None
    sources = _sources(conn, ctx, entry.get("sources", []))
    raw = json.dumps(
        {
            "failing_test_id": ctx.failed_tests[0].id, "line": entry["line"], "concept_id": concept_id,
            "claim": entry["claim"], "source_chunk_ids": [s.chunk_id for s in sources], "hint_level": 2,
        }
    )
    evidence = Evidence(
        code=ctx.code, reference_solution=ctx.reference_solution, failed_tests=ctx.failed_tests,
        error_concept_ids=ctx.error_concept_ids, retrieved_chunk_ids=frozenset(s.chunk_id for s in sources),
        hidden_inputs=ctx.hidden_inputs, visible_texts=ctx.visible_texts, error_type=ctx.error_type,
        leak_threshold=ctx.leak_threshold,
    )
    explanation, checks = verify(raw, evidence)
    if explanation is None or not all_passed(checks):
        log.warning("cached demo explanation no longer verifies", extra={"fields": {"submission": ctx.submission_id}})
        return None
    for check in [*checks, ("final", True, "verified from the cached demo explanation, no model call")]:
        name, passed, detail = (check.name, check.passed, check.detail) if hasattr(check, "name") else check
        conn.execute(
            text(
                "INSERT INTO explanation_checks"
                " (submission_id, check_name, passed, attempt, model, prompt_version, detail)"
                " VALUES (:s, :n, :p, 0, :m, :v, :d)"
            ),
            {"s": ctx.submission_id, "n": name, "p": passed, "m": MODEL_LABEL, "v": PROMPT_LABEL,
             "d": detail or ("cached demo explanation" if name == "json_valid" else None)},
        )
    log.info("served cached demo explanation", extra={"fields": {"submission": ctx.submission_id, "cached": True}})
    return ExplainResponse(
        status="verified", attempts=0, cached=True, fallback_text=None, fallback_sources=[], probe=None,
        explanation=ExplanationOut(
            claim=entry["claim"], line=entry["line"], concept=entry["concept"], hint_level=2, sources=sources
        ),
    )
