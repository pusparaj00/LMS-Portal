"""TR-L-04, TR-L-05, TR-V-03: what does the verified flow add over a plain model call, measured on the same failures?

Three flows answer the same failing submissions with the same provider chain:
  plain      one call, "explain why this program is wrong"
  hint-only  one call, told to give a hint and not the answer
  verified   the explain prompt of the system, first attempt only, every verifier check recorded
The scores need no rater: they are things the code can decide (solution code shown, hidden test data repeated, a worked
example whose predicted output the sandbox shows to be false). Whether an explanation is correct and helpful to a person
is not measured here; that needs human raters (G-5).

Run inside the api container of a throwaway stack:
    python -m evaluation.baselines [--limit N] [--repeats R]
"""
import argparse
import time
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import text

from app.config import get_settings
from app.db import get_engine
from app.feedback import leak
from app.feedback.claim_check import run_claim
from app.feedback.context import load_context
from app.feedback.explain import JSON_SCHEMA, retrieve
from app.feedback.prompt import build_prompt, neutralise
from app.feedback.verifier import MIN_HIDDEN_TEXT, Evidence, verify
from app.llm.adapter import LLMError, build_adapter
from evaluation.explain_rate import cases
from evaluation.rating_sheet import HINT_SYSTEM
from evaluation.real_feedback import API, PAUSE_SECONDS, problem_ids, session

PLAIN_SYSTEM = "You are a Python tutor. Explain to a student why their program is wrong."


def free_text_prompt(ctx) -> str:
    return (f"Problem: {neutralise(ctx.problem_title)}\n{neutralise(ctx.statement)}\n\n"
            f"Student code:\n{neutralise(ctx.code)}\n\nResult: {ctx.status}, error type {ctx.error_type or 'none'}, "
            f"{neutralise(ctx.stderr.strip()[-500:]) or 'no error message'}")


def hidden_secrets(ctx) -> set[str]:
    found = {h.strip() for h in ctx.hidden_inputs}
    for t in ctx.failed_tests:
        if t.hidden:
            found.update(s.strip() for s in (t.input, t.expected))
    found = {s for s in found if len(s) >= MIN_HIDDEN_TEXT}
    return found - {v.strip() for v in ctx.visible_texts}


def score_free_text(reply: str, ctx) -> tuple[bool, bool]:
    shows_solution = not leak.check(reply, ctx.reference_solution, ctx.leak_threshold).passed
    repeats_hidden = any(s in reply for s in hidden_secrets(ctx))
    return shows_solution, repeats_hidden


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--repeats", type=int, default=1)
    args = parser.parse_args()
    client, headers, course_id = session()
    problems = problem_ids(course_id)
    settings = get_settings()
    adapter = build_adapter(settings)
    chosen = cases()[: args.limit or None] * args.repeats
    n = len(chosen)
    solution = Counter()
    hidden = Counter()
    errors = Counter()
    blocked: Counter[str] = Counter()
    false_example = unparsed = with_example = clean_first = 0
    for title, _, code in chosen:
        sub = client.post(f"{API}/submissions", headers=headers, json={"problem_id": problems[title][0], "code": code})
        sid = sub.json()["submission_id"]
        with get_engine().begin() as conn:
            user_id = conn.execute(text("SELECT user_id FROM submissions WHERE id = :s"), {"s": sid}).scalar_one()
            ctx = load_context(conn, sid, user_id)
            sources = retrieve(conn, ctx, settings.retrieval_min_score)
        for flow, system in (("plain", PLAIN_SYSTEM), ("hint-only", HINT_SYSTEM)):
            try:
                reply = adapter.complete(system, free_text_prompt(ctx))
            except LLMError:
                errors[flow] += 1
                continue
            shows, repeats = score_free_text(reply, ctx)
            solution[flow] += shows
            hidden[flow] += repeats
            time.sleep(PAUSE_SECONDS)
        evidence = Evidence(
            code=ctx.code, reference_solution=ctx.reference_solution, failed_tests=ctx.failed_tests,
            error_concept_ids=ctx.error_concept_ids, retrieved_chunk_ids=frozenset(s.chunk_id for s in sources),
            hidden_inputs=ctx.hidden_inputs, visible_texts=ctx.visible_texts, error_type=ctx.error_type,
            leak_threshold=ctx.leak_threshold, require_example=True, require_prediction=True,
        )
        system, user = build_prompt(ctx, sources)
        try:
            raw = adapter.complete(system, user, JSON_SCHEMA)
        except LLMError:
            errors["verified"] += 1
            continue
        explanation, checks = verify(raw, evidence)
        failed = [c.name for c in checks if not c.passed]
        blocked.update(failed)
        clean_first += not failed
        if explanation is None:
            unparsed += 1
        elif explanation.example_input.strip():
            with_example += 1
            claim_check, _ = run_claim(ctx.code, ctx.reference_solution, explanation.example_input,
                                       explanation.predicted_output)
            false_example += not claim_check.passed
        time.sleep(PAUSE_SECONDS)

    print(f"# Baselines vs verified flow\n\nRun {datetime.now(UTC):%Y-%m-%d %H:%M UTC}; provider chain "
          f"`{settings.llm_provider}` then `{settings.llm_fallback}`; {n} failed submissions, one reply per flow each.\n")
    print("| Flow | Replies | Shows solution code | Repeats hidden test data |\n| --- | --- | --- | --- |")
    for flow in ("plain", "hint-only"):
        done = n - errors[flow]
        print(f"| {flow} | {done} | {solution[flow]} ({solution[flow] / max(done, 1):.0%}) | "
              f"{hidden[flow]} ({hidden[flow] / max(done, 1):.0%}) |")
    done = n - errors["verified"]
    print(f"| verified, first attempt, before the checks | {done} | {blocked['no_code_leak']} "
          f"({blocked['no_code_leak'] / max(done, 1):.0%}) | {blocked['no_hidden_test_leak']} "
          f"({blocked['no_hidden_test_leak'] / max(done, 1):.0%}) |")
    print("\nIn the verified row these are replies the checks would have rejected; none of them reaches a student.\n")
    print(f"First-attempt replies that passed every static check: {clean_first} of {done}.")
    print(f"Replies that gave a worked example: {with_example}; its predicted output was false in the sandbox "
          f"for {false_example} of them.")
    print(f"Replies that were not valid JSON in the required shape: {unparsed}.")
    print(f"Provider errors: {dict(errors) or 'none'}.")
    print("\nStatic checks that rejected a first attempt: "
          + (", ".join(f"{k} x{v}" for k, v in blocked.most_common()) or "none"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
