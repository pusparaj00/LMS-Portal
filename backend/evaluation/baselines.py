"""TR-L-04, TR-L-05, TR-V-03: what does the verified flow add over a plain model call, measured on the same failures?

Flows answer the same failing submissions with the same provider chain:
  plain         one call, "explain why this program is wrong"
  hint-only     one call, told to give a hint and not the answer
  plain-strong  the plain call to a stronger model, when --strong provider:model is given
  verified      the explain prompt of the system, first attempt only, every verifier check recorded
The scores need no rater: they are things the code can decide (solution code shown, hidden test data repeated, a worked
example whose predicted output the sandbox shows to be false). Whether an explanation is correct and helpful to a person
is not measured here; that needs human raters (G-5).

Each share comes with a 95% interval from a bootstrap that resamples whole FAILURES (all repeats of a failure move
together), so repeating the same 28 failures does not make the interval look narrower than the data allow. The ablation
table says, for every check, how many first attempts it rejected and how many only it rejected: those are the replies
that would have reached a student had the check been switched off.

Run inside the api container of a throwaway stack:
    python -m evaluation.baselines [--limit N] [--repeats R] [--strong provider:model]
"""
import argparse
import time
from collections import Counter
from datetime import UTC, datetime

import numpy as np
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
BOOTSTRAPS = 2000


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


def share_interval(records: list[dict], flag: str, rng: np.random.Generator, bootstraps: int = BOOTSTRAPS):
    """(share, low, high, replies): the share of replies with `flag` set and a 95% interval from resampling whole
    failures. None when there are no replies."""
    if not records:
        return None
    by_case: dict[int, list[int]] = {}
    for record in records:
        by_case.setdefault(record["case"], []).append(int(bool(record[flag])))
    hits = np.array([sum(v) for v in by_case.values()])
    sizes = np.array([len(v) for v in by_case.values()])
    shares = []
    for _ in range(bootstraps):
        chosen = rng.integers(0, len(hits), len(hits))
        shares.append(hits[chosen].sum() / sizes[chosen].sum())
    low, high = np.percentile(shares, [2.5, 97.5])
    return float(hits.sum() / sizes.sum()), float(low), float(high), int(sizes.sum())


def ablation(verified: list[dict]) -> list[tuple[str, int, int]]:
    """(check, first attempts it rejected, first attempts rejected by it alone), most active first."""
    rejected: Counter[str] = Counter()
    alone: Counter[str] = Counter()
    for record in verified:
        failed = set(record["failed"])
        rejected.update(failed)
        if len(failed) == 1:
            alone.update(failed)
    return [(name, count, alone[name]) for name, count in rejected.most_common()]


def format_share(result) -> str:
    if result is None:
        return "no replies"
    point, low, high, total = result
    return f"{point:.0%} ({low:.0%} to {high:.0%}), {total} replies"


def collect(args, adapter, strong, client, headers, problems, settings) -> list[dict]:
    records: list[dict] = []
    chosen = cases()[: args.limit or None]
    for repeat in range(args.repeats):
        for case, (title, _, code) in enumerate(chosen):
            sub = client.post(f"{API}/submissions", headers=headers,
                              json={"problem_id": problems[title][0], "code": code})
            sid = sub.json()["submission_id"]
            with get_engine().begin() as conn:
                user_id = conn.execute(text("SELECT user_id FROM submissions WHERE id = :s"), {"s": sid}).scalar_one()
                ctx = load_context(conn, sid, user_id)
                sources = retrieve(conn, ctx, settings.retrieval_min_score)
            free = [("plain", PLAIN_SYSTEM, adapter), ("hint-only", HINT_SYSTEM, adapter)]
            if strong is not None:
                free.append(("plain-strong", PLAIN_SYSTEM, strong))
            for flow, system, caller in free:
                try:
                    reply = caller.complete(system, free_text_prompt(ctx))
                except LLMError:
                    records.append({"case": case, "flow": flow, "replied": False})
                    continue
                shows, repeats_hidden = score_free_text(reply, ctx)
                records.append({"case": case, "flow": flow, "replied": True, "shows_solution": shows,
                                "repeats_hidden": repeats_hidden})
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
                records.append({"case": case, "flow": "verified", "replied": False})
                continue
            explanation, checks = verify(raw, evidence)
            failed = [c.name for c in checks if not c.passed]
            record = {"case": case, "flow": "verified", "replied": True, "failed": failed, "clean": not failed,
                      "unparsed": explanation is None, "with_example": False, "false_example": False,
                      "shows_solution": "no_code_leak" in failed, "repeats_hidden": "no_hidden_test_leak" in failed}
            if explanation is not None and explanation.example_input.strip():
                record["with_example"] = True
                claim_check, _ = run_claim(ctx.code, ctx.reference_solution, explanation.example_input,
                                           explanation.predicted_output)
                record["false_example"] = not claim_check.passed
            records.append(record)
            time.sleep(PAUSE_SECONDS)
        print(f"repeat {repeat + 1} of {args.repeats} done", flush=True)
    return records


def summarise(records: list[dict], settings, args) -> str:
    rng = np.random.default_rng(0)
    flows = [f for f in ("plain", "hint-only", "plain-strong", "verified") if any(r["flow"] == f for r in records)]
    replied = {f: [r for r in records if r["flow"] == f and r["replied"]] for f in flows}
    out = [f"# Baselines vs verified flow\n\nRun {datetime.now(UTC):%Y-%m-%d %H:%M UTC}; provider chain "
           f"`{settings.llm_provider}` then `{settings.llm_fallback}`"
           + (f"; strong model `{args.strong}`" if args.strong else "")
           + f"; {args.repeats} repeat(s) of {len({r['case'] for r in records})} failures.\n"
           "Intervals: 95%, bootstrap over failures.\n",
           "| Flow | Shows solution code | Repeats hidden test data |", "| --- | --- | --- |"]
    for flow in flows:
        label = "verified, first attempt, before the checks" if flow == "verified" else flow
        out.append(f"| {label} | {format_share(share_interval(replied[flow], 'shows_solution', rng))} | "
                   f"{format_share(share_interval(replied[flow], 'repeats_hidden', rng))} |")
    out.append("\nIn the verified row these are replies the checks would have rejected; none reaches a student.\n")
    verified = replied.get("verified", [])
    if verified:
        out += ["## Verified flow, first attempt\n",
                f"- Passed every static check: {format_share(share_interval(verified, 'clean', rng))}",
                f"- Not valid JSON in the required shape: {format_share(share_interval(verified, 'unparsed', rng))}"]
        with_example = [r for r in verified if r["with_example"]]
        out.append("- Worked example whose predicted output was false in the sandbox, among replies that gave one: "
                   + format_share(share_interval(with_example, "false_example", rng)))
        out += ["\n## Ablation: what each static check rejected\n",
                "| Check | First attempts rejected | Rejected by this check alone |", "| --- | --- | --- |"]
        out += [f"| {name} | {count} | {alone} |" for name, count, alone in ablation(verified)] or ["| (none) | 0 | 0 |"]
        out.append("\nThe sandbox check of the worked example runs after the static ones, so it is counted above "
                   "only among replies that gave an example, not in this table.")
    missing = {f: sum(1 for r in records if r["flow"] == f and not r["replied"]) for f in flows}
    out.append(f"\nProvider errors (no reply): {missing}.")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--strong", default="", help="provider:model for the stronger plain baseline")
    args = parser.parse_args()
    client, headers, course_id = session()
    problems = problem_ids(course_id)
    settings = get_settings()
    adapter = build_adapter(settings)
    strong = None
    if args.strong:
        provider, _, model = args.strong.partition(":")
        strong = build_adapter(settings.model_copy(update={"llm_provider": provider, "llm_model": model,
                                                           "llm_fallback": ""}))
    print(summarise(collect(args, adapter, strong, client, headers, problems, settings), settings, args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
