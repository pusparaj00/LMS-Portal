"""Which provider should be primary? Same submissions through the verified flow, per provider, no fallback (TR-P-03).

Usage (inside the api container, which holds the keys): python -m evaluation.provider_compare gemini groq
For each wrong submission the providers take turns, so a slow minute on the network affects both alike.
Prints a markdown table; every number is measured in this run.
"""
import os
import statistics
import sys
import time
import uuid
from datetime import UTC, datetime

os.environ["DEMO_CACHE_DIR"] = ""  # before the app is imported: measure the model, not the demo cache

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import get_engine  # noqa: E402
from app.llm.adapter import OPENAI_COMPATIBLE, build_adapter  # noqa: E402
from app.main import app  # noqa: E402
from app.routers.feedback import llm_adapter  # noqa: E402
from evaluation.real_feedback import WRONG_SUBMISSIONS  # noqa: E402

API = "/api/v1"
PAUSE_SECONDS = 4  # stay under the free tier per-minute limits


def settings_for(provider: str):
    base = get_settings()
    model = base.llm_model if provider == base.llm_provider else getattr(base, OPENAI_COMPATIBLE[provider][2])
    return base.model_copy(update={"llm_provider": provider, "llm_model": model, "llm_fallback": ""})


def main(providers: list[str]) -> int:
    client = TestClient(app)
    token = client.post(
        f"{API}/auth/register", json={"email": f"compare-{uuid.uuid4().hex[:8]}@eval.local", "password": "compare-pass-1"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    with get_engine().connect() as conn:
        course = conn.execute(
            text("SELECT id FROM courses WHERE title = 'Python Fundamentals' ORDER BY id DESC LIMIT 1")
        ).scalar_one()
        problems = dict(conn.execute(text("SELECT title, id FROM problems WHERE course_id = :c"), {"c": course}).all())
    client.post(f"{API}/courses/{course}/enroll", headers=headers)
    configs = {p: settings_for(p) for p in providers}
    results: dict[str, list[tuple[float, str, int]]] = {p: [] for p in providers}
    for title, code in WRONG_SUBMISSIONS:
        for provider in providers:
            app.dependency_overrides[llm_adapter] = lambda s=configs[provider]: build_adapter(s)
            # a unique comment makes every submission new, so no cached reply is reused
            body = {"problem_id": problems[title], "code": code + f"# {provider} {uuid.uuid4().hex[:6]}\n"}
            sid = client.post(f"{API}/submissions", headers=headers, json=body).json()["submission_id"]
            started = time.perf_counter()
            reply = client.post(f"{API}/submissions/{sid}/explain", headers=headers).json()
            results[provider].append((time.perf_counter() - started, reply["status"], reply["attempts"]))
            print(f"{title} / {provider}: {reply['status']} after {reply['attempts']}", file=sys.stderr)
            time.sleep(PAUSE_SECONDS)
    app.dependency_overrides.clear()

    print(f"# Primary provider comparison\n\nRun {datetime.now(UTC):%Y-%m-%d %H:%M UTC}, {len(WRONG_SUBMISSIONS)} wrong "
          "submissions per provider (the Step 4 set), verified flow, no fallback, demo cache off.\n")
    print("| Provider and model | Verified | Verified on attempt 1 | Template | Median s | Max s | Within 15 s |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for provider, rows in results.items():
        seconds = [s for s, _, _ in rows]
        verified = sum(st == "verified" for _, st, _ in rows)
        first = sum(st == "verified" and a == 1 for _, st, a in rows)
        print(f"| {provider} `{configs[provider].llm_model}` | {verified} of {len(rows)} | {first} of {len(rows)} | "
              f"{len(rows) - verified} | {statistics.median(seconds):.2f} | {max(seconds):.2f} | "
              f"{sum(s <= 15 for s in seconds)} of {len(rows)} |")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["gemini", "groq"]))
