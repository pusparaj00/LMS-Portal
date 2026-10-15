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
SECONDS_PER_RUN = 5
SLACK_SECONDS = 15


class SandboxUnavailable(Exception):
    pass


@dataclass(frozen=True)
class RunOutcome:
    status: str
    exit_code: int
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
                exit_code=int(r["exit_code"]),
                stdout=str(r["stdout"]),
                stderr=str(r["stderr"]),
                runtime_ms=int(r["runtime_ms"]),
            )
            for r in payload["runs"]
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise SandboxUnavailable("sandbox returned a malformed result") from exc


def run_batch(code: str, stdins: list[str]) -> list[RunOutcome]:
    jobs = _jobs_dir()
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
