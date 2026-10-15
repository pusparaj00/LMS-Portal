"""Model calls per 100 explained failures, and the share served from a cache (TR-P-08).

Usage (inside the api container): python -m evaluation.llm_usage [--since YYYY-MM-DD]

Read from `explanation_checks`, which stores every attempt: attempt 1 and 2 are live model calls (a failed call
counts, the provider was still asked), attempt 0 is a stored explanation (model `cache` or `cached-demo`). Nothing here
is estimated. The counts cover every explained submission in the database since the date, test accounts included.
"""
import argparse
import sys
from datetime import UTC, date, datetime

from sqlalchemy import text

from app.db import get_engine

STORED_MODELS = {"cache": "failure-signature cache", "cached-demo": "prepared demo explanations"}


def summarise(rows: list[tuple[int, int, str, str, bool]]) -> dict:
    """rows are (submission_id, attempt, model, check_name, passed) from explanation_checks."""
    submissions: dict[int, dict] = {}
    for submission, attempt, model, check, passed in rows:
        entry = submissions.setdefault(submission, {"live_attempts": set(), "stored": None, "fallback": False})
        if attempt >= 1:
            entry["live_attempts"].add(attempt)
        elif model in STORED_MODELS:
            entry["stored"] = model
        if check == "final" and not passed:
            entry["fallback"] = True
    total = len(submissions)
    live_calls = sum(len(s["live_attempts"]) for s in submissions.values())
    stored = {m: sum(s["stored"] == m for s in submissions.values()) for m in STORED_MODELS}
    return {
        "explained": total,
        "live_calls": live_calls,
        "calls_per_100": 100 * live_calls / total if total else None,
        "stored": stored,
        "stored_share": sum(stored.values()) / total if total else None,
        "fallback": sum(s["fallback"] for s in submissions.values()),
        "max_calls_for_one_submission": max((len(s["live_attempts"]) for s in submissions.values()), default=0),
    }


def report(result: dict, since: date | None) -> str:
    if not result["explained"]:
        return "No explained submissions in this period."
    lines = [
        f"# Model usage per explained failure (TR-P-08)\n\nRun {datetime.now(UTC):%Y-%m-%d %H:%M UTC}"
        + (f", submissions since {since}" if since else ", all submissions in the database") + ".\n",
        "| Measure | Value |", "| --- | --- |",
        f"| Failed submissions explained | {result['explained']} |",
        f"| Live model calls (attempts) | {result['live_calls']} |",
        f"| **Model calls per 100 failed submissions** | **{result['calls_per_100']:.1f}** |",
        f"| Most calls for one submission (limit: 2) | {result['max_calls_for_one_submission']} |",
    ]
    for model, label in STORED_MODELS.items():
        lines.append(f"| Served from the {label} | {result['stored'][model]} |")
    lines.append(f"| **Share served without a model call** | **{result['stored_share']:.0%}** |")
    lines.append(f"| Ended as a template hint (verifier rejected twice or the model failed) | {result['fallback']} |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", type=date.fromisoformat)
    args = parser.parse_args()
    query = "SELECT submission_id, attempt, model, check_name, passed FROM explanation_checks"
    params = {}
    if args.since:
        query += " WHERE created_at >= :since"
        params["since"] = args.since
    with get_engine().connect() as conn:
        rows = [tuple(r) for r in conn.execute(text(query), params)]
    result = summarise(rows)
    print(report(result, args.since))
    return 0 if result["max_calls_for_one_submission"] <= 2 else 1


if __name__ == "__main__":
    sys.exit(main())
