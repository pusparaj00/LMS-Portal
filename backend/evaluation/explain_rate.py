"""G-1: how often does the real model's explanation pass the verifier, on varied failures?

Each wrong submission is made through the API by a fresh throwaway student, then generation and verification run
directly (`run_explain`), so no stored explanation can stand in for the model and nothing is stored or shown. Every
attempt's checks are logged in explanation_checks as in production. Run inside the api container, which holds the
provider keys:
    python -m evaluation.explain_rate [--limit N]
"""
import argparse
import time
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import text

from app.config import get_settings
from app.db import get_engine
from app.feedback.context import load_context
from app.feedback.explain import run_explain
from app.llm.adapter import build_adapter
from evaluation.rating_sheet import SUBMISSIONS
from evaluation.real_feedback import API, PAUSE_SECONDS, checks_for, problem_ids, session

# Other kinds of failure than a wrong answer: the error types the verifier and the fallback treat differently.
OTHER_FAILURES = [
    ("Sum from 1 to n", "syntax error", "n = int(input()\nprint(n)\n"),
    ("Sum from 1 to n", "name error", "n = int(input())\nprint(total)\n"),
    ("Sum from 1 to n", "time limit", "n = int(input())\nwhile True:\n    n += 1\n"),
    ("Sum from 1 to n", "value error", "n = int(input())\nprint(int('x') + n)\n"),
    ("Sum from 1 to n", "index error", "n = int(input())\nvalues = [n]\nprint(values[3])\n"),
    ("Sum from 1 to n", "empty program", "pass\n"),
    ("Sum from 1 to n", "prints a word", "print('hello')\n"),
]


def cases() -> list[tuple[str, str, str]]:
    return [(title, "wrong answer", code) for title, code in SUBMISSIONS] + OTHER_FAILURES


def failed_checks(rows, attempt: int) -> list[str]:
    return [c + (f" ({d})" if d else "") for a, c, ok, d in rows if a == attempt and not ok and c != "final"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    client, headers, course_id = session()
    problems = problem_ids(course_id)
    settings = get_settings()
    adapter = build_adapter(settings)
    chosen = cases()[: args.limit or None]
    print(f"# Explanation verify rate\n\nRun {datetime.now(UTC):%Y-%m-%d %H:%M UTC}; configured provider "
          f"`{settings.llm_provider}`, fallbacks `{settings.llm_fallback}`; stored explanations are bypassed.\n")
    print("| # | Problem | Failure | Result | Attempts | Seconds | Failed checks (attempt 1) | (attempt 2) |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    verified = first_try = provider_down = 0
    reasons: Counter[str] = Counter()
    seconds: list[float] = []
    for number, (title, kind, code) in enumerate(chosen, 1):
        sub = client.post(f"{API}/submissions", headers=headers, json={"problem_id": problems[title][0], "code": code})
        sid = sub.json()["submission_id"]
        started = time.monotonic()
        with get_engine().begin() as conn:
            user_id = conn.execute(text("SELECT user_id FROM submissions WHERE id = :s"), {"s": sid}).scalar_one()
            outcome = run_explain(
                conn, load_context(conn, sid, user_id), adapter, settings.retrieval_min_score, settings.explain_budget_s
            )
        took = time.monotonic() - started
        rows = checks_for(sid)
        first, second = failed_checks(rows, 1), failed_checks(rows, 2)
        seconds.append(took)
        ok = outcome.status == "verified"
        verified += ok
        first_try += ok and outcome.attempts == 1
        # a provider outage says nothing about the verifier: count it apart
        provider_down += any(c.startswith(("llm_call", "time_budget")) for c in first + second) and not ok
        for check in first + second:
            reasons[check.split(" (")[0]] += 1
        print(f"| {number} | {title} | {kind} | {outcome.status} | {outcome.attempts} | {took:.1f} | "
              f"{'; '.join(c[:90] for c in first) or '-'} | {'; '.join(c[:90] for c in second) or '-'} |", flush=True)
        time.sleep(PAUSE_SECONDS)
    total = len(chosen)
    print(f"\nVerified: {verified} of {total} ({verified / total * 100:.0f}%). "
          f"Verified on the first attempt: {first_try} of {total} ({first_try / total * 100:.0f}%).")
    print(f"Fallbacks caused by an unreachable or rate-limited provider (not by the verifier): {provider_down}.")
    reachable = total - provider_down
    if reachable:
        print(f"Verified among the {reachable} runs where a provider answered: {verified} of {reachable} "
              f"({verified / reachable * 100:.0f}%).")
    print(f"Seconds per explanation: median {sorted(seconds)[len(seconds) // 2]:.1f}, max {max(seconds):.1f}.")
    print("\nChecks that failed (all attempts): " + (", ".join(f"{k} x{v}" for k, v in reasons.most_common()) or "none"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
