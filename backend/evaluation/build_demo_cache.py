"""Generate data/demo/explanations.json with the REAL verified flow (needs a model key).

Usage (from backend/, inside the api container): python -m evaluation.build_demo_cache /tmp/explanations.json
(then copy the file out: the data folder is mounted read-only in the container)
Only explanations that pass the verifier on the first or second attempt are kept. The demo cache is switched off for
this run so the results come from the model, not from an earlier cache.
"""
import json
import os
import re
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

os.environ["DEMO_CACHE_DIR"] = ""  # before the app is imported: generate, do not read the cache

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import get_engine  # noqa: E402
from app.main import app  # noqa: E402
from evaluation.consent import agree

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = next(p for p in (ROOT / "data" / "demo", ROOT.parent / "data" / "demo") if p.exists()) / "scenarios.json"
API = "/api/v1"
TEST_ID = re.compile(r"tests? \d+")  # database-specific numbers must not travel with a cached claim


def main() -> None:
    client = TestClient(app)
    token = client.post(
        f"{API}/auth/register", json={"email": f"demo-cache-{uuid.uuid4().hex[:8]}@eval.local", "password": "cache-build-1"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    agree(client, API, headers)
    with get_engine().connect() as conn:
        course_id = conn.execute(text("SELECT id FROM courses WHERE title = 'Python Fundamentals' ORDER BY id LIMIT 1")).scalar_one()
        problems = dict(
            conn.execute(text("SELECT title, id FROM problems WHERE course_id = :c AND kind = 'code'"), {"c": course_id}).all()
        )
    client.post(f"{API}/courses/{course_id}/enroll", headers=headers)
    entries = []
    for scenario in json.loads(SCENARIOS.read_text(encoding="utf-8")):
        submitted = client.post(
            f"{API}/submissions", headers=headers, json={"problem_id": problems[scenario["problem"]], "code": scenario["code"]}
        ).json()
        reply = client.post(f"{API}/submissions/{submitted['submission_id']}/explain", headers=headers).json()
        explanation = reply["explanation"]
        print(f"{scenario['problem']}: {reply['status']} after {reply['attempts']} attempt(s)", file=sys.stderr)
        if reply["status"] != "verified" or reply["cached"]:
            continue
        entries.append(
            {
                "problem": scenario["problem"], "code": scenario["code"], "claim": TEST_ID.sub("a failing test", explanation["claim"]),
                "line": explanation["line"], "concept": explanation["concept"],
                "sources": [{"title": s["title"], "section": s["section"]} for s in explanation["sources"]],
            }
        )
    settings = get_settings()
    result = {
        "generated": datetime.now(UTC).strftime("%Y-%m-%d"),
        "model": f"{settings.llm_provider}:{settings.llm_model}",
        "about": "Produced by the real verified flow; re-verified against each submission before it is shown.",
        "entries": entries,
    }
    with open(sys.argv[1], "w", encoding="utf-8") as out:
        json.dump(result, out, indent=2, ensure_ascii=False)
        out.write("\n")


if __name__ == "__main__":
    main()
