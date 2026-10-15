"""Client for the sandbox runner (TR-X-07, TR-A-03).

The runner has no network interface, so jobs travel through files on a shared volume. Results
come from an untrusted container and are parsed defensively.
"""
import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

POLL_SECONDS = 0.05
SECONDS_PER_RUN = 12  # the runner stops a run after 10 s wall time, plus startup
SLACK_SECONDS = 15
MAX_QUEUED_JOBS = 20  # the runner takes one job at a time; this many waiting means a wait of many seconds (TR-P-05)
QUEUE_WAIT_SECONDS = 3  # a short queue is waited out before the caller is told to retry
RETRY_AFTER_SECONDS = 2


class SandboxUnavailable(Exception):
    pass


class SandboxBusy(SandboxUnavailable):
    """The runner is up but its queue is full: the request was not lost, it was not started. Retry shortly."""


@dataclass(frozen=True)
class RunOutcome:
    status: str
    stdout: str
    stderr: str
    runtime_ms: int


def _jobs_dir() -> Path:
    return Path(os.environ.get("JOBS_DIR", "/jobs"))


def _parse(payload: object, expected: int) -> list[RunOutcome]:
    if not isinstance(payload, dict) or not isinstance(payload.get("runs"), list):
        raise SandboxUnavailable(f"sandbox error: {str(payload)[:100]}")
    if len(payload["runs"]) != expected:
        raise SandboxUnavailable("sandbox returned the wrong number of runs")
    try:
        return [
            RunOutcome(
                status=str(r["status"]),
                stdout=str(r["stdout"]),
                stderr=str(r["stderr"]),
                runtime_ms=int(r["runtime_ms"]),
            )
            for r in payload["runs"]
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise SandboxUnavailable("sandbox returned a malformed result") from exc


def _wait_for_room(jobs: Path) -> None:
    """Return when the queue has room; raise SandboxBusy if it stays full for QUEUE_WAIT_SECONDS."""
    queue = jobs / "in"
    deadline = time.monotonic() + QUEUE_WAIT_SECONDS
    while sum(1 for p in queue.glob("*.json")) >= MAX_QUEUED_JOBS:
        if time.monotonic() >= deadline:
            raise SandboxBusy("the sandbox queue is full")
        time.sleep(POLL_SECONDS)


def run_batch(code: str, stdins: list[str]) -> list[RunOutcome]:
    jobs = _jobs_dir()
    _wait_for_room(jobs)
    job_id = uuid.uuid4().hex
    tmp = jobs / "in" / f"{job_id}.json.tmp"
    try:
        tmp.write_text(json.dumps({"code": code, "runs": [{"stdin": s} for s in stdins]}))
        os.replace(tmp, jobs / "in" / f"{job_id}.json")
    except OSError as exc:
        raise SandboxUnavailable("cannot submit job to the sandbox") from exc

    result_path = jobs / "out" / f"{job_id}.json"
    deadline = time.monotonic() + SECONDS_PER_RUN * len(stdins) + SLACK_SECONDS
    try:
        while time.monotonic() < deadline:
            if result_path.exists():
                return _parse(json.loads(result_path.read_text()), len(stdins))
            time.sleep(POLL_SECONDS)
        raise SandboxUnavailable("sandbox did not answer in time")
    except json.JSONDecodeError as exc:
        raise SandboxUnavailable("sandbox returned invalid JSON") from exc
    finally:
        result_path.unlink(missing_ok=True)
        (jobs / "in" / f"{job_id}.json").unlink(missing_ok=True)
