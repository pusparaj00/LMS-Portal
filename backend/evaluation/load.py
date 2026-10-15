"""Load and reliability checks (TR-V-10, TR-P-01 to TR-P-04, TR-P-06, TR-P-07). Run inside the api container.

  python -m evaluation.load concurrent 10   # 10 students at once, each doing the whole demo flow
  python -m evaluation.load runs 10         # the whole demo flow, one student after another
  python -m evaluation.load timings         # sandbox run, item selection and explanation latency
  python -m evaluation.load prepare         # restart test, part 1: a placement test left half done (prints a handle)
  python -m evaluation.load verify HANDLE   # restart test, part 2: finish it after the services were restarted

Every number printed is measured by this script in this run. A step "fails" on any HTTP error or unexpected answer.
"""
import json
import statistics
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx
from sqlalchemy import text

from app.db import get_engine
from app.seed import ensure_user

API = "http://localhost:8000/api/v1"
COURSE_TITLE = "Python Fundamentals"
DEMO_PROBLEM = "Sum from 1 to n"
DEMO_CODE = "n = int(input())\ntotal = 0\nfor i in range(n):\n    total += i\nprint(total)\n"
CORRECT_SUM = "print(sum(range(1, int(input()) + 1)))\n"


@dataclass
class Flow:
    steps: list[tuple[str, float, bool, str]] = field(default_factory=list)  # name, seconds, ok, note

    def timed(self, name, call, check=lambda r: True):
        started = time.perf_counter()
        try:
            response = call()
            ok = check(response)
            note = "" if ok else f"{response.status_code} {response.text[:80]}"
        except Exception as exc:  # a dropped connection is a failed step, not a crashed test
            response, ok, note = None, False, f"{type(exc).__name__}: {exc}"[:90]
        self.steps.append((name, time.perf_counter() - started, ok, note))
        return response

    @property
    def failed(self):
        return [s for s in self.steps if not s[2]]


def course_ids():
    with get_engine().connect() as conn:
        course = conn.execute(text("SELECT id FROM courses WHERE title = :t ORDER BY id DESC LIMIT 1"), {"t": COURSE_TITLE}).scalar_one()
        problem = conn.execute(text("SELECT id FROM problems WHERE course_id = :c AND title = :t"), {"c": course, "t": DEMO_PROBLEM}).scalar_one()
    return course, problem


def admin_headers() -> dict:
    with get_engine().begin() as conn:
        ensure_user(conn, "load-admin@eval.local", "admin", "load-admin-pass-1")
    token = httpx.post(f"{API}/auth/login", json={"email": "load-admin@eval.local", "password": "load-admin-pass-1"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def demo_flow(label: str, cached: bool, admin: dict) -> Flow:
    """The PRD demo script as API calls: placement, dashboard, wrong code, explanation, probe, chat, instructor view."""
    flow, client = Flow(), httpx.Client(timeout=120)
    course, problem = course_ids()
    email = f"load-{label}-{uuid.uuid4().hex[:6]}@eval.local"
    ok = lambda code=200: (lambda r: r.status_code == code)  # noqa: E731
    reply = flow.timed("register", lambda: client.post(f"{API}/auth/register", json={"email": email, "password": "load-test-pass-1"}), ok(201))
    if reply is None or reply.status_code != 201:
        return flow
    headers = {"Authorization": "Bearer " + reply.json()["access_token"]}
    flow.timed("enroll", lambda: client.post(f"{API}/courses/{course}/enroll", headers=headers), ok(204))

    started = flow.timed("placement start", lambda: client.post(f"{API}/diagnostic/start", headers=headers, json={"course_id": course}), ok())
    if started is None or started.status_code != 200:
        return flow
    session, item, answered = started.json()["session_id"], started.json()["item"], 0
    while item is not None and answered < 12:
        body = (
            {"option_id": item["options"][0]["id"]} if item["kind"] == "mcq" else {"code": "print(1)\n"}
        )
        step = flow.timed(
            f"placement answer ({item['kind']})",
            lambda b=body, i=item: client.post(f"{API}/diagnostic/answer", headers=headers, json={"session_id": session, "problem_id": i["problem_id"], **b}),
            ok(),
        )
        answered += 1
        if step is None or step.status_code != 200 or step.json()["done"]:
            break
        item = step.json()["next_item"]
    flow.timed("dashboard", lambda: client.get(f"{API}/students/me/mastery", headers=headers, params={"course_id": course}), ok())

    code = DEMO_CODE if cached else DEMO_CODE + f"# run {uuid.uuid4().hex}\n"
    submitted = flow.timed("submit wrong code", lambda: client.post(f"{API}/submissions", headers=headers, json={"problem_id": problem, "code": code}), lambda r: r.status_code == 200 and r.json()["status"] == "failed")
    if submitted is None or submitted.status_code != 200:
        return flow
    sid = submitted.json()["submission_id"]
    explained = flow.timed(
        "explanation (cached demo)" if cached else "explanation (live, uncached)",
        lambda: client.post(f"{API}/submissions/{sid}/explain", headers=headers),
        lambda r: r.status_code == 200 and (r.json()["cached"] if cached else r.json()["status"] in ("verified", "fallback")),
    )
    flow.timed("hint", lambda: client.post(f"{API}/submissions/{sid}/hint", headers=headers), ok())
    probe = explained.json().get("probe") if explained is not None and explained.status_code == 200 else None
    if probe:
        answer = {"option_id": probe["options"][0]["id"]} if probe["kind"] == "mcq" else {"code": CORRECT_SUM}
        flow.timed("probe answer", lambda: client.post(f"{API}/probes/{probe['problem_id']}/answer", headers=headers, json={"submission_id": sid, **answer}), ok())
    flow.timed("chat: hint", lambda: client.post(f"{API}/chat", headers=headers, json={"message": "I am stuck, can I have a hint?", "problem_id": problem}), lambda r: r.status_code == 200 and r.json()["route"] == "hint")
    flow.timed("chat: progress", lambda: client.post(f"{API}/chat", headers=headers, json={"message": "How am I doing?"}), lambda r: r.status_code == 200 and r.json()["route"] == "progress")
    flow.timed("instructor heatmap", lambda: client.get(f"{API}/courses/{course}/class-mastery", headers=admin), lambda r: r.status_code == 200 and len(r.json()["students"]) >= 20)
    return flow


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(p * (len(ordered) - 1))))]


def summarise(flows: list[Flow], title: str) -> int:
    print(f"# {title}\n\nRun {datetime.now(UTC):%Y-%m-%d %H:%M UTC}\n")
    by_step: dict[str, list[float]] = {}
    for flow in flows:
        for name, seconds, _ok, _note in flow.steps:
            by_step.setdefault(name.split(" (")[0] if name.startswith("placement answer") else name, []).append(seconds)
    total_steps = sum(len(f.steps) for f in flows)
    failed = [(i + 1, s) for i, f in enumerate(flows) for s in f.failed]
    print(f"Flows: {len(flows)}, steps: {total_steps}, failed steps: {len(failed)}, flows with no failed step: "
          f"{sum(not f.failed for f in flows)} of {len(flows)}\n")
    print("| Step | Count | Median s | 95th percentile s | Max s |\n| --- | --- | --- | --- | --- |")
    for name, values in by_step.items():
        print(f"| {name} | {len(values)} | {statistics.median(values):.2f} | {percentile(values, 0.95):.2f} | {max(values):.2f} |")
    for number, (name, seconds, _, note) in failed:
        print(f"\nFAILED flow {number}: {name} after {seconds:.1f}s: {note}")
    return 1 if failed else 0


def concurrent(count: int) -> int:
    admin = admin_headers()
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=count) as pool:
        flows = list(pool.map(lambda n: demo_flow(f"c{n}", cached=False, admin=admin), range(count)))
    code = summarise(flows, f"{count} concurrent students, each doing the whole demo flow (explanation uncached, live model)")
    print(f"\nWall time for all {count} students together: {time.perf_counter() - started:.1f}s")
    return code


def runs(count: int) -> int:
    admin = admin_headers()
    flows = []
    for n in range(count):
        flows.append(demo_flow(f"r{n}", cached=True, admin=admin))
        print(f"run {n + 1}: {'ok' if not flows[-1].failed else 'FAILED'} in {sum(s[1] for s in flows[-1].steps):.1f}s", file=sys.stderr)
    return summarise(flows, f"{count} consecutive demo runs (one student after another, explanation from the demo cache)")


def timings() -> int:
    from app.diagnostic import selection

    print(f"# Timings\n\nRun {datetime.now(UTC):%Y-%m-%d %H:%M UTC}\n")
    course, problem = course_ids()
    client = httpx.Client(timeout=120)

    def student():
        token = client.post(f"{API}/auth/register", json={"email": f"time-{uuid.uuid4().hex[:8]}@eval.local", "password": "timing-pass-1"}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        client.post(f"{API}/courses/{course}/enroll", headers=headers)
        return headers

    headers = student()
    runs = []
    for _ in range(20):
        started = time.perf_counter()
        client.post(f"{API}/submissions/run", headers=headers, json={"problem_id": problem, "code": CORRECT_SUM})
        runs.append(time.perf_counter() - started)
    print("| Measure | n | Median s | 95th percentile s | Max s | Target |\n| --- | --- | --- | --- | --- | --- |")
    print(f"| Sandbox run, typical problem (TR-P-01), through the API | {len(runs)} | {statistics.median(runs):.2f} | {percentile(runs, 0.95):.2f} | {max(runs):.2f} | within 5 s, hard stop 10 s |")

    with get_engine().connect() as conn:
        rows = conn.execute(text("SELECT p.id, p.kind, p.discrimination_a, p.difficulty_b, pc.concept_id, pc.weight FROM problems p JOIN problem_concepts pc ON pc.problem_id = p.id WHERE p.course_id = :c"), {"c": course}).all()
    items: dict[int, dict] = {}
    for pid, kind, a, b, cid, w in rows:
        e = items.setdefault(pid, {"kind": kind, "a": a, "b": b, "concepts": {}})
        e["concepts"][cid] = w
    pool = [selection.Item(pid, e["kind"], e["a"], e["b"], e["concepts"]) for pid, e in sorted(items.items())]
    concepts = sorted({c for i in pool for c in i.concepts})
    selection_times = []
    for step in range(200):
        mastery = {c: 0.2 + 0.6 * ((c * 7 + step) % 10) / 10 for c in concepts}
        asked = {i.id for i in pool[: step % 8]}
        started = time.perf_counter()
        selection.select_next(pool, asked, mastery, theta=0.0)
        selection_times.append(time.perf_counter() - started)
    print(f"| Next diagnostic item, selection function alone (TR-P-02) | {len(selection_times)} | {statistics.median(selection_times) * 1000:.1f} ms | {percentile(selection_times, 0.95) * 1000:.1f} ms | {max(selection_times) * 1000:.1f} ms | under 1 s |")

    answers = []
    started_session = client.post(f"{API}/diagnostic/start", headers=headers, json={"course_id": course}).json()
    session, item = started_session["session_id"], started_session["item"]
    while item is not None:
        body = {"option_id": item["options"][0]["id"]} if item["kind"] == "mcq" else {"code": "print(1)\n"}
        started = time.perf_counter()
        reply = client.post(f"{API}/diagnostic/answer", headers=headers, json={"session_id": session, "problem_id": item["problem_id"], **body}).json()
        if item["kind"] == "mcq":
            answers.append(time.perf_counter() - started)  # answer + mastery update + choosing the next item
        item = reply.get("next_item")
    print(f"| Placement answer end to end for a tracing item (answer, mastery update, next item) | {len(answers)} | {statistics.median(answers):.2f} | {percentile(answers, 0.95):.2f} | {max(answers):.2f} | (reference) |")

    live = []
    for _ in range(8):
        sub = client.post(f"{API}/submissions", headers=headers, json={"problem_id": problem, "code": DEMO_CODE + f"# timing {uuid.uuid4().hex}\n"}).json()
        started = time.perf_counter()
        reply = client.post(f"{API}/submissions/{sub['submission_id']}/explain", headers=headers).json()
        live.append((time.perf_counter() - started, reply["status"], reply["attempts"]))
        time.sleep(3)
    seconds = [t for t, _, _ in live]
    print(f"| Verified explanation, new failure, live model (TR-P-03) | {len(live)} | {statistics.median(seconds):.2f} | {percentile(seconds, 0.95):.2f} | {max(seconds):.2f} | within 15 s |")
    cached = []
    for _ in range(5):
        sub = client.post(f"{API}/submissions", headers=headers, json={"problem_id": problem, "code": DEMO_CODE}).json()
        started = time.perf_counter()
        client.post(f"{API}/submissions/{sub['submission_id']}/explain", headers=headers)
        cached.append(time.perf_counter() - started)
    print(f"| Explanation from the demo cache (TR-P-03) | {len(cached)} | {statistics.median(cached):.2f} | {percentile(cached, 0.95):.2f} | {max(cached):.2f} | within 1 s |")
    print(f"\nLive explanations: {Counter_text([f'{s} after {a} attempt(s)' for _, s, a in live])}")
    return 0


def Counter_text(values: list[str]) -> str:  # noqa: N802
    counts: dict[str, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return ", ".join(f"{n} x {v}" for v, n in counts.items())


def prepare() -> int:
    """Restart test, part 1: register a student and leave a placement test half done."""
    course, _ = course_ids()
    client = httpx.Client(timeout=60)
    token = client.post(f"{API}/auth/register", json={"email": f"restart-{uuid.uuid4().hex[:8]}@eval.local", "password": "restart-pass-1"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.post(f"{API}/courses/{course}/enroll", headers=headers)
    started = client.post(f"{API}/diagnostic/start", headers=headers, json={"course_id": course}).json()
    session, item = started["session_id"], started["item"]
    for _ in range(4):
        reply = client.post(f"{API}/diagnostic/answer", headers=headers, json={"session_id": session, "problem_id": item["problem_id"], "option_id": item["options"][0]["id"]}).json()
        item = reply["next_item"]
    print(json.dumps({"token": token, "session_id": session, "current": item["problem_id"], "course": course, "answered": 4}))
    return 0


def verify(handle: str) -> int:
    """Restart test, part 2: the same session continues and completes."""
    state = json.loads(handle)
    client = httpx.Client(timeout=60)
    headers = {"Authorization": "Bearer " + state["token"]}
    answered, item_id, failed = state["answered"], state["current"], False
    me = client.get(f"{API}/students/me/mastery", headers=headers, params={"course_id": state["course"]})
    print(f"signed in with the token from before the restart: {me.status_code == 200}")
    while True:
        with get_engine().connect() as conn:
            options = conn.execute(text("SELECT id, option_text FROM item_options WHERE problem_id = :p ORDER BY id"), {"p": item_id}).all()
            kind = conn.execute(text("SELECT kind FROM problems WHERE id = :p"), {"p": item_id}).scalar_one()
        body = {"option_id": options[0].id} if kind == "mcq" else {"code": "print(1)\n"}
        reply = client.post(f"{API}/diagnostic/answer", headers=headers, json={"session_id": state["session_id"], "problem_id": item_id, **body})
        if reply.status_code != 200:
            print(f"FAILED: session answer returned {reply.status_code}: {reply.text[:100]}")
            failed = True
            break
        answered += 1
        data = reply.json()
        if data["done"]:
            print(f"the placement test continued after the restart and finished after {answered} items; "
                  f"mastery for {len(data['result']['mastery'])} concepts")
            break
        item_id = data["next_item"]["problem_id"]
    return 1 if failed else 0


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "concurrent":
        return concurrent(int(sys.argv[2]))
    if command == "runs":
        return runs(int(sys.argv[2]))
    if command == "timings":
        return timings()
    if command == "prepare":
        return prepare()
    if command == "verify":
        return verify(sys.argv[2])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
