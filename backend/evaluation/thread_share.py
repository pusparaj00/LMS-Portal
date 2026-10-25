"""G-3: how long does a cheap request wait while a crowd of model-backed requests is running?

Starts the real app under uvicorn in this process, with a model that is slow and then fails (so each explanation holds a
worker thread and database connections exactly as a slow provider does), makes N students ask for an explanation at the
same moment, and times a cheap request (the course list) throughout. Runs only against the test database and Redis
database 1, in the test container:
    python -m evaluation.thread_share --students 48 --delay 6
Set SERVER_THREADS, DB_POOL_SIZE and DB_MAX_OVERFLOW in the environment to compare settings.
"""
import argparse
import os
import statistics
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import httpx
import uvicorn
from sqlalchemy import create_engine, text

from app.auth import create_token, hash_password
from app.config import get_settings
from app.consent import CONSENT_VERSION
from app.llm.adapter import FallbackChain, LLMConfig, LLMError
from app.main import app
from app.routers.feedback import llm_adapter

PORT = 8765
BASE = f"http://127.0.0.1:{PORT}/api/v1"


class SlowThenDown:
    """A model that thinks for `delay` seconds and then fails: the request falls back to the template."""

    def __init__(self, delay: float) -> None:
        self.config = LLMConfig("fake", "fake-model", 0.0, 0, 30.0)
        self.delay = delay

    def complete(self, system, user, json_schema=None):
        time.sleep(self.delay)
        raise LLMError("the model is down")


def setup(students: int, engine) -> tuple[dict, list[dict], int]:
    password = hash_password("pw-12345678")
    with engine.begin() as conn:
        def user(role: str) -> tuple[int, dict]:
            uid = conn.execute(
                text("INSERT INTO users (email, password_hash, role) VALUES (:e, :h, :r) RETURNING id"),
                {"e": f"{role}-{uuid.uuid4().hex[:8]}@test.local", "h": password, "r": role},
            ).scalar_one()
            if role == "student":
                conn.execute(
                    text("INSERT INTO consents (user_id, version, adult_confirmed) VALUES (:u, :v, true)"),
                    {"u": uid, "v": CONSENT_VERSION},
                )
            return uid, {"Authorization": f"Bearer {create_token(uid, role)}"}

        teacher_id, teacher = user("instructor")
        course = conn.execute(
            text("INSERT INTO courses (title, instructor_id) VALUES ('Thread share', :i) RETURNING id"), {"i": teacher_id}
        ).scalar_one()
        concept = conn.execute(
            text("INSERT INTO concepts (course_id, name) VALUES (:c, 'loops') RETURNING id"), {"c": course}
        ).scalar_one()
        problem = conn.execute(
            text(
                "INSERT INTO problems (course_id, title, statement, kind, difficulty_b, discrimination_a,"
                " reference_solution) VALUES (:c, 'Add one', 's', 'code', 0, 1, :r) RETURNING id"
            ),
            {"c": course, "r": "print(int(input()) + 1)\n"},
        ).scalar_one()
        conn.execute(text("INSERT INTO problem_concepts VALUES (:p, :c, 1.0)"), {"p": problem, "c": concept})
        for given, expected, hidden in (("1\n", "2\n", False), ("9\n", "10\n", True)):
            conn.execute(
                text("INSERT INTO test_cases (problem_id, input, expected, hidden, category) VALUES (:p, :i, :e, :h, 'basic')"),
                {"p": problem, "i": given, "e": expected, "h": hidden},
            )
        people = []
        for _ in range(students):
            uid, headers = user("student")
            conn.execute(text("INSERT INTO enrollments (user_id, course_id) VALUES (:u, :c)"), {"u": uid, "c": course})
            people.append(headers)
    return teacher, people, problem


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--students", type=int, default=48)
    parser.add_argument("--delay", type=float, default=6.0)
    args = parser.parse_args()
    settings = get_settings()
    engine = create_engine(os.environ["OWNER_DATABASE_URL"])
    chain = FallbackChain(
        [SlowThenDown(args.delay)], budget_s=settings.llm_budget_s, max_concurrent=settings.llm_max_concurrent,
        queue_wait_s=settings.llm_queue_wait_s,
    )
    app.dependency_overrides[llm_adapter] = lambda: chain
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.1)

    teacher, students, problem = setup(args.students, engine)
    with httpx.Client(timeout=60) as client:
        ids = [
            client.post(f"{BASE}/submissions", headers=h, json={"problem_id": problem, "code": "print('x')\n"}).json()["submission_id"]
            for h in students
        ]
    stop = threading.Event()
    cheap: list[float] = []

    def probe() -> None:
        with httpx.Client(timeout=60) as client:
            while not stop.is_set():
                started = time.monotonic()
                client.get(f"{BASE}/courses", headers=teacher)
                cheap.append(time.monotonic() - started)
                time.sleep(0.25)

    def explain(item: tuple[dict, int]) -> tuple[int, float]:
        headers, submission = item
        with httpx.Client(timeout=90) as client:
            started = time.monotonic()
            status = client.post(f"{BASE}/submissions/{submission}/explain", headers=headers).status_code
            return status, time.monotonic() - started

    quiet = []
    with httpx.Client(timeout=60) as client:
        for _ in range(10):
            started = time.monotonic()
            client.get(f"{BASE}/courses", headers=teacher)
            quiet.append(time.monotonic() - started)
    prober = threading.Thread(target=probe)
    prober.start()
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.students) as pool:
        results = list(pool.map(explain, zip(students, ids, strict=True)))
    wall = time.monotonic() - started
    stop.set()
    prober.join()

    codes = dict(sorted(Counter(s for s, _ in results).items()))
    cheap.sort()
    print(f"settings: server_threads={settings.server_threads}, db pool {settings.db_pool_size}+{settings.db_max_overflow}, "
          f"model calls at once {settings.llm_max_concurrent}, model delay {args.delay:g} s, {args.students} students")
    print(f"explain: statuses {codes}, slowest {max(t for _, t in results):.1f} s, whole crowd done in {wall:.1f} s")
    print(f"cheap request alone: median {statistics.median(quiet) * 1000:.0f} ms")
    print(f"cheap request during the crowd ({len(cheap)} samples): median {statistics.median(cheap) * 1000:.0f} ms, "
          f"95th percentile {cheap[int(len(cheap) * 0.95) - 1] * 1000:.0f} ms, slowest {cheap[-1] * 1000:.0f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
