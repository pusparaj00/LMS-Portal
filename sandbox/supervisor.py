"""Sandbox runner (TR-X-08): runs untrusted Python from job files on a shared volume.

The container has no network interface besides loopback, a read-only root filesystem and no
listening port, so the only way in is a job file written by the submission service.
Every limit below is explicit (TR-X-05). Student code runs as an unprivileged uid in a
per-run directory on a tmpfs and is killed, with every process of that uid, when the run ends.
"""
import json
import os
import resource
import shutil
import signal
import subprocess
import time
import uuid
from pathlib import Path

JOBS = Path(os.environ.get("JOBS_DIR", "/jobs"))
WORK = Path("/work")
PYTHON = "/usr/local/bin/python3"

API_UID = API_GID = 10001
RUN_UID = RUN_GID = 10002

LIMITS = {
    "cpu_seconds": 2,
    "wall_seconds": 4,
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


def _demote() -> None:
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
    os.setuid(RUN_UID)


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


def run_once(code: str, stdin: str) -> dict:
    run_dir = WORK / uuid.uuid4().hex
    run_dir.mkdir(mode=0o700)
    os.chown(run_dir, RUN_UID, RUN_GID)
    try:
        main = run_dir / "main.py"
        main.write_text(code)
        os.chown(main, RUN_UID, RUN_GID)
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
                preexec_fn=_demote,
                close_fds=True,
            )
            timed_out = False
            try:
                proc.wait(timeout=LIMITS["wall_seconds"])
            except subprocess.TimeoutExpired:
                timed_out = True
            _kill_user_processes(RUN_UID)
            proc.wait()
            runtime_ms = int((time.monotonic() - started) * 1000)
        stdout_size = (run_dir / "stdout").stat().st_size
        stderr = _read_capped(run_dir / "stderr")
        return {
            "status": _classify(proc.returncode, timed_out, stdout_size, stderr),
            "exit_code": proc.returncode,
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


def handle(job_path: Path) -> None:
    job_id = job_path.stem
    try:
        job = json.loads(job_path.read_text())
        if _valid(job):
            payload = {"runs": [run_once(job["code"], r["stdin"]) for r in job["runs"]]}
        else:
            payload = {"error": "invalid_job"}
    except Exception as exc:
        payload = {"error": f"supervisor_error: {type(exc).__name__}"}
    finally:
        job_path.unlink(missing_ok=True)
    _write_result(job_id, payload)


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
    _ensure(JOBS, 0, 0, 0o711)
    _ensure(JOBS / "in", API_UID, API_GID, 0o711)
    _ensure(JOBS / "out", 0, API_GID, 0o770)
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
        "run_uid": RUN_UID,
        "network_interfaces": sorted(os.listdir("/sys/class/net")),
        "root_filesystem_writable": rootfs_writable,
        "supervisor_effective_capabilities": cap_eff,
        "python": subprocess.run([PYTHON, "--version"], capture_output=True, text=True).stdout.strip(),
    }
    (JOBS / "config.json").write_text(json.dumps(report, indent=2))
    os.chmod(JOBS / "config.json", 0o644)


def main() -> None:
    setup()
    last_beat = 0.0
    while True:
        now = time.time()
        if now - last_beat >= 1:
            (JOBS / "heartbeat").write_text(str(now))
            last_beat = now
        for orphan in (JOBS / "out").glob("*.json"):
            if now - orphan.stat().st_mtime > ORPHAN_RESULT_SECONDS:
                orphan.unlink(missing_ok=True)
        pending = sorted((JOBS / "in").glob("*.json"), key=lambda p: p.stat().st_mtime)
        if pending:
            handle(pending[0])
        else:
            time.sleep(0.05)


if __name__ == "__main__":
    main()
