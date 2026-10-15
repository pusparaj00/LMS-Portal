"""TR-P-05: a full sandbox queue is waited out briefly, then answered with a clear 503 and Retry-After, never dropped."""
import json
import threading
import time

import pytest

from app import sandbox
from tests.test_submissions import API, student, submit  # noqa: F401  (fixtures)


@pytest.fixture
def jobs(tmp_path, monkeypatch):
    (tmp_path / "in").mkdir()
    (tmp_path / "out").mkdir()
    monkeypatch.setenv("JOBS_DIR", str(tmp_path))
    monkeypatch.setattr(sandbox, "QUEUE_WAIT_SECONDS", 0.3)
    return tmp_path


def fill(jobs, count):
    for n in range(count):
        (jobs / "in" / f"waiting-{n}.json").write_text("{}")


def fake_runner(jobs, stop):
    """Takes jobs oldest first like the real runner and answers each with one successful run."""
    while not stop.is_set():
        for path in sorted((jobs / "in").glob("*.json"), key=lambda p: p.stat().st_mtime):
            try:
                job = json.loads(path.read_text())
                runs = [{"status": "ok", "stdout": "ok", "stderr": "", "runtime_ms": 1} for _ in job.get("runs", [{}])]
                path.unlink()
                (jobs / "out" / path.name).write_text(json.dumps({"runs": runs}))
            except (FileNotFoundError, json.JSONDecodeError):
                continue
        time.sleep(0.02)


def test_a_full_queue_raises_busy_after_a_short_wait_and_starts_nothing(jobs):
    fill(jobs, sandbox.MAX_QUEUED_JOBS)
    started = time.monotonic()
    with pytest.raises(sandbox.SandboxBusy):
        sandbox.run_batch("print(1)", ["1\n"])
    assert 0.25 <= time.monotonic() - started < 1.5
    assert len(list((jobs / "in").glob("*.json"))) == sandbox.MAX_QUEUED_JOBS  # no job of ours was queued


def test_a_queue_that_drains_during_the_wait_is_used_not_refused(jobs):
    fill(jobs, sandbox.MAX_QUEUED_JOBS)
    stop = threading.Event()
    threading.Timer(0.1, lambda: [p.unlink() for p in (jobs / "in").glob("waiting-*.json")]).start()
    runner = threading.Thread(target=fake_runner, args=(jobs, stop))
    runner.start()
    try:
        [outcome] = sandbox.run_batch("print(1)", ["1\n"])
    finally:
        stop.set()
        runner.join()
    assert outcome.status == "ok" and outcome.stdout == "ok"


def test_the_api_answers_a_busy_sandbox_with_503_and_retry_after(client, course, student, jobs):  # noqa: F811
    _, headers = student
    fill(jobs, sandbox.MAX_QUEUED_JOBS)
    response = submit(client, course, headers, "print(1)\n", path="/submissions/run")
    assert response.status_code == 503
    assert response.headers["retry-after"] == str(sandbox.RETRY_AFTER_SECONDS)
    assert "busy" in response.json()["error"]["message"].lower()
    assert submit(client, course, headers, "print(1)\n").status_code == 503  # a real submission too


def test_a_busy_submission_is_not_stored_so_nothing_is_dropped_or_half_saved(client, course, student, jobs, owner):  # noqa: F811
    from sqlalchemy import text

    user_id, headers = student
    count = text("SELECT count(*) FROM submissions WHERE user_id = :u")
    with owner.connect() as conn:
        before = conn.execute(count, {"u": user_id}).scalar_one()
    fill(jobs, sandbox.MAX_QUEUED_JOBS)
    assert submit(client, course, headers, "print(1)\n").status_code == 503
    with owner.connect() as conn:
        assert conn.execute(count, {"u": user_id}).scalar_one() == before


def test_a_retry_after_the_queue_drains_succeeds(client, course, student, jobs):  # noqa: F811
    _, headers = student
    fill(jobs, sandbox.MAX_QUEUED_JOBS)
    assert submit(client, course, headers, "print(int(input()) + 1)\n", path="/submissions/run").status_code == 503
    for path in (jobs / "in").glob("waiting-*.json"):
        path.unlink()
    stop = threading.Event()
    runner = threading.Thread(target=fake_runner, args=(jobs, stop))
    runner.start()
    try:
        assert submit(client, course, headers, "print(1)\n", path="/submissions/run").status_code == 200
    finally:
        stop.set()
        runner.join()


def test_a_runner_that_is_down_is_not_called_busy_and_gets_no_retry_after(client, course, student, jobs, monkeypatch):  # noqa: F811
    _, headers = student
    monkeypatch.setattr(sandbox, "SECONDS_PER_RUN", 0.05)
    monkeypatch.setattr(sandbox, "SLACK_SECONDS", 0.2)
    response = submit(client, course, headers, "print(1)\n", path="/submissions/run")
    assert response.status_code == 503 and "retry-after" not in response.headers
    assert "unavailable" in response.json()["error"]["message"]
