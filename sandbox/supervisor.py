"""Sandbox runner (TR-X-08): runs untrusted Python from job files on a shared volume.

The container has no network interface besides loopback, a read-only root filesystem and no
listening port, so the only way in is a job file written by the submission service.
Every limit below is explicit (TR-X-05). Student code runs as an unprivileged uid in a
per-run directory on a tmpfs and is killed, with every process of that uid, when the run ends.

Several jobs run at once (TR-P-04, TR-P-05), one in each of WORKERS worker processes, and each worker has a uid of its
own. A worker's run directory is private to its uid, its process limit counts only its own processes, and ending a run
kills only that uid's processes, so one student's code cannot read, signal or starve another's.
"""
import json
import multiprocessing
import os
import re
import resource
import shutil
import signal
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

JOBS = Path(os.environ.get("JOBS_DIR", "/jobs"))
WORK = Path("/work")
CLAIMED = JOBS / "claimed"
PYTHON = "/usr/local/bin/python3"

API_UID = API_GID = 10001
RUN_UID_BASE = RUN_GID = 10002
WORKERS = int(os.environ.get("SANDBOX_WORKERS", "4"))
RUN_UIDS = [RUN_UID_BASE + slot for slot in range(WORKERS)]

LIMITS = {
    "cpu_seconds": 2,
    "wall_seconds": 10,  # TR-P-01 hard stop; generous so a loaded host does not fail honest code
    "memory_bytes": 256 * 1024 * 1024,
    "max_processes": 16,
    "max_open_files": 32,
    "output_file_bytes": 1024 * 1024,
    "result_text_bytes": 64 * 1024,
    "max_code_bytes": 256 * 1024,
    "max_stdin_bytes": 64 * 1024,
    "max_runs_per_job": 60,
}
ORPHAN_RESULT_SECONDS = 120
REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")  # the API's own rule; anything else is logged as "-"


def _demote(uid: int) -> None:
    os.setsid()
    cpu = LIMITS["cpu_seconds"]
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
    resource.setrlimit(resource.RLIMIT_AS, (LIMITS["memory_bytes"],) * 2)
    resource.setrlimit(resource.RLIMIT_NPROC, (LIMITS["max_processes"],) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (LIMITS["output_file_bytes"],) * 2)
    resource.setrlimit(resource.RLIMIT_NOFILE, (LIMITS["max_open_files"],) * 2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.setgroups([])
    os.setgid(RUN_GID)
    os.setuid(uid)


def _kill_user_processes(uid: int) -> None:
    for _ in range(10):
        found = False
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            try:
                with open(f"/proc/{entry}/status") as status:
                    real_uid = next(
                        int(line.split()[1]) for line in status if line.startswith("Uid:")
                    )
                if real_uid == uid:
                    os.kill(int(entry), signal.SIGKILL)
                    found = True
            except (OSError, StopIteration):
                continue
        if not found:
            return
        time.sleep(0.02)


def _classify(returncode: int, timed_out: bool, stdout_size: int, stderr: str) -> str:
    if timed_out or returncode == -signal.SIGXCPU:
        return "time_limit"
    if stdout_size >= LIMITS["output_file_bytes"] or returncode == -signal.SIGXFSZ:
        return "output_limit"
    if returncode == 0:
        return "ok"
    if "MemoryError" in stderr:
        return "memory_limit"
    if "SyntaxError" in stderr or "IndentationError" in stderr:
        return "syntax_error"
    return "runtime_error"


def _read_capped(path: Path) -> str:
    with open(path, "rb") as handle:
        return handle.read(LIMITS["result_text_bytes"]).decode("utf-8", errors="replace")


def run_once(code: str, stdin: str, uid: int) -> dict:
    run_dir = WORK / uuid.uuid4().hex
    run_dir.mkdir(mode=0o700)
    os.chown(run_dir, uid, RUN_GID)
    try:
        main = run_dir / "main.py"
        main.write_text(code)
        os.chown(main, uid, RUN_GID)
        (run_dir / "stdin").write_text(stdin)
        with (
            open(run_dir / "stdin", "rb") as in_f,
            open(run_dir / "stdout", "wb") as out_f,
            open(run_dir / "stderr", "wb") as err_f,
        ):
            started = time.monotonic()
            proc = subprocess.Popen(
                [PYTHON, "-I", "main.py"],
                cwd=run_dir,
                stdin=in_f,
                stdout=out_f,
                stderr=err_f,
                env={"PATH": "/usr/local/bin:/usr/bin", "PYTHONDONTWRITEBYTECODE": "1"},
                preexec_fn=lambda: _demote(uid),
                close_fds=True,
            )
            timed_out = False
            try:
                proc.wait(timeout=LIMITS["wall_seconds"])
            except subprocess.TimeoutExpired:
                timed_out = True
            _kill_user_processes(uid)
            proc.wait()
            runtime_ms = int((time.monotonic() - started) * 1000)
        stdout_size = (run_dir / "stdout").stat().st_size
        stderr = _read_capped(run_dir / "stderr")
        return {
            "status": _classify(proc.returncode, timed_out, stdout_size, stderr),
            "stdout": _read_capped(run_dir / "stdout"),
            "stderr": stderr,
            "runtime_ms": runtime_ms,
        }
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def _valid(job: dict) -> bool:
    runs = job.get("runs")
    return (
        isinstance(job.get("code"), str)
        and len(job["code"].encode()) <= LIMITS["max_code_bytes"]
        and isinstance(runs, list)
        and len(runs) <= LIMITS["max_runs_per_job"]
        and all(
            isinstance(r, dict)
            and isinstance(r.get("stdin"), str)
            and len(r["stdin"].encode()) <= LIMITS["max_stdin_bytes"]
            for r in runs
        )
    )


def _write_result(job_id: str, payload: dict) -> None:
    tmp = JOBS / "out" / f"{job_id}.json.tmp"
    tmp.write_text(json.dumps(payload))
    os.chown(tmp, 0, API_GID)
    os.chmod(tmp, 0o640)
    os.replace(tmp, JOBS / "out" / f"{job_id}.json")


def _log(job_id: str, request_id: object, payload: dict, started: float) -> None:
    """One JSON line per job in the API's log format (TR-A-08); never the code or its input and output."""
    runs = payload.get("runs", [])
    statuses: dict[str, int] = {}
    for run in runs:
        statuses[run["status"]] = statuses.get(run["status"], 0) + 1
    print(json.dumps({
        "ts": datetime.now(UTC).isoformat(), "level": "INFO", "logger": "sandbox",
        "request_id": request_id if isinstance(request_id, str) and REQUEST_ID.fullmatch(request_id) else "-",
        "message": "job finished", "job_id": job_id, "runs": len(runs), "statuses": statuses,
        "error": payload.get("error"), "duration_ms": int((time.monotonic() - started) * 1000),
    }), flush=True)


def handle(job_path: Path, uid: int) -> None:
    job_id = job_path.stem
    started = time.monotonic()
    job: object = None
    try:
        job = json.loads(job_path.read_text())
        if _valid(job):
            payload = {"runs": [run_once(job["code"], r["stdin"], uid) for r in job["runs"]]}
        else:
            payload = {"error": "invalid_job"}
    except Exception as exc:
        payload = {"error": f"supervisor_error: {type(exc).__name__}"}
    finally:
        job_path.unlink(missing_ok=True)
    _write_result(job_id, payload)
    _log(job_id, job.get("request_id") if isinstance(job, dict) else None, payload, started)


def _ensure(path: Path, uid: int, gid: int, mode: int) -> None:
    """Idempotent: after a restart the directory already belongs to the API uid."""
    info = path.stat()
    if (info.st_uid, info.st_gid, info.st_mode & 0o777) == (uid, gid, mode):
        return
    os.chmod(path, mode)
    os.chown(path, uid, gid)


def setup() -> None:
    (JOBS / "in").mkdir(exist_ok=True)
    (JOBS / "out").mkdir(exist_ok=True)
    CLAIMED.mkdir(exist_ok=True)
    _ensure(JOBS, 0, 0, 0o711)
    _ensure(JOBS / "in", API_UID, API_GID, 0o711)
    _ensure(JOBS / "out", 0, API_GID, 0o770)
    _ensure(CLAIMED, 0, 0, 0o700)
    for stale in CLAIMED.glob("*.json"):  # a job that was running when the container stopped has no one waiting for it
        stale.unlink(missing_ok=True)
    report_config()


def report_config() -> None:
    cap_eff = next(
        line.split()[1] for line in Path("/proc/self/status").read_text().splitlines()
        if line.startswith("CapEff:")
    )
    try:
        with open("/etc/sandbox-write-probe", "w"):
            rootfs_writable = True
    except OSError:
        rootfs_writable = False
    report = {
        "limits": LIMITS,
        "run_uids": RUN_UIDS,
        "workers": WORKERS,
        "network_interfaces": sorted(os.listdir("/sys/class/net")),
        "root_filesystem_writable": rootfs_writable,
        "supervisor_effective_capabilities": cap_eff,
        "python": subprocess.run([PYTHON, "--version"], capture_output=True, text=True).stdout.strip(),
    }
    (JOBS / "config.json").write_text(json.dumps(report, indent=2))
    os.chmod(JOBS / "config.json", 0o644)


def _mtime(path: Path) -> float | None:
    # The API deletes job and result files on its own schedule, so any file can vanish here.
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return None


def _claim() -> Path | None:
    """Take the oldest waiting job. The rename is atomic, so two workers never take the same job."""
    pending = sorted((m, p) for p in (JOBS / "in").glob("*.json") if (m := _mtime(p)) is not None)
    for _, path in pending:
        target = CLAIMED / path.name
        try:
            os.rename(path, target)
        except FileNotFoundError:
            continue
        return target
    return None


def _work(uid: int) -> None:
    while True:
        job = _claim()
        if job is None:
            time.sleep(0.05)
        else:
            handle(job, uid)


def _start(uid: int) -> multiprocessing.Process:
    worker = multiprocessing.get_context("fork").Process(target=_work, args=(uid,), daemon=True)
    worker.start()
    return worker


def main() -> None:
    setup()
    workers = {uid: _start(uid) for uid in RUN_UIDS}
    last_beat = 0.0
    while True:
        now = time.time()
        for uid, worker in workers.items():
            if not worker.is_alive():
                workers[uid] = _start(uid)
        if now - last_beat >= 1:
            (JOBS / "heartbeat").write_text(str(now))
            last_beat = now
        for orphan in (JOBS / "out").glob("*.json"):
            mtime = _mtime(orphan)
            if mtime is not None and now - mtime > ORPHAN_RESULT_SECONDS:
                orphan.unlink(missing_ok=True)
        time.sleep(0.2)


if __name__ == "__main__":
    main()
