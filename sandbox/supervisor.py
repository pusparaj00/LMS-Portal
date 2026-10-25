"""Sandbox runner (TR-X-08, TR-X-10): runs untrusted Python, Java or C from job files on a shared volume.

The container has no network interface besides loopback, a read-only root filesystem and no
listening port, so the only way in is a job file written by the submission service.
Every limit below is explicit (TR-X-05). Student code runs as an unprivileged uid in a
per-run directory on a tmpfs and is killed, with every process of that uid, when the run ends.
Java and C are compiled once per job, by the same unprivileged uid, and each test then runs its own copy
of the compiled program.
"""
import json
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
CWORK = Path("/cwork")  # the only tmpfs that allows exec: a compiled C program cannot start from /work
PYTHON = "/usr/local/bin/python3"
SUPPORTED = ("python", "java", "c")
COMPILED = ("java", "c")
SOURCE_FILE = {"python": "main.py", "java": "Main.java", "c": "main.c"}
ENV = {"PATH": "/usr/local/bin:/usr/bin", "PYTHONDONTWRITEBYTECODE": "1"}

API_UID = API_GID = 10001
RUN_UID = RUN_GID = 10002

LIMITS = {
    "cpu_seconds": 2,
    "wall_seconds": 10,  # TR-P-01 hard stop; generous so a loaded host does not fail honest code
    "compile_wall_seconds": 20,
    "memory_bytes": 256 * 1024 * 1024,
    "max_processes": 16,
    "max_open_files": 32,
    "output_file_bytes": 1024 * 1024,
    "result_text_bytes": 64 * 1024,
    "max_code_bytes": 256 * 1024,
    "max_stdin_bytes": 64 * 1024,
    "max_runs_per_job": 60,
}
# A JVM reserves far more address space than it uses and starts a dozen threads, so Java gets its own address-space,
# thread and file limits; its heap is capped with -Xmx and the container's own memory limit is the outer bound.
_PYTHON_PROFILE = {
    "cpu": LIMITS["cpu_seconds"], "memory": LIMITS["memory_bytes"],
    "processes": LIMITS["max_processes"], "files": LIMITS["max_open_files"],
}
PROFILES = {
    "python": _PYTHON_PROFILE,
    "c": _PYTHON_PROFILE,
    "java": {"cpu": 6, "memory": 3 * 1024**3, "processes": 64, "files": 256},
}
COMPILE_PROFILES = {
    "c": {"cpu": 10, "memory": 512 * 1024**2, "processes": 16, "files": 64},
    "java": {"cpu": 15, "memory": 3 * 1024**3, "processes": 64, "files": 256},
}
_JVM_FLAGS = ["-XX:+UseSerialGC", "-XX:TieredStopAtLevel=1", "-XX:CICompilerCount=1", "-XX:-UsePerfData", "-Xss1m"]
COMMANDS = {
    "python": [PYTHON, "-I", "main.py"],
    "java": ["java", "-Xmx128m", "-XX:MaxMetaspaceSize=64m", "-XX:ReservedCodeCacheSize=32m", *_JVM_FLAGS,
             "-Djava.io.tmpdir=.", "-cp", ".", "Main"],
    "c": ["./a.out"],
}
COMPILE_COMMANDS = {
    "java": ["javac", "-proc:none", "-J-Xmx192m", *(f"-J{f}" for f in _JVM_FLAGS), "-d", ".", "Main.java"],
    "c": ["cc", "-std=gnu11", "-O0", "-o", "a.out", "main.c", "-lm"],
}
ARTIFACTS = {"java": "*.class", "c": "a.out"}
ORPHAN_RESULT_SECONDS = 120
REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")  # the API's own rule; anything else is logged as "-"

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_LINE_SPLICE = re.compile(r"\\\r?\n")
_INCLUDE = re.compile(r"^[ \t]*#[ \t]*(?:include|include_next|import|embed)\b(.*)$", re.M)
_PLAIN_HEADER = re.compile(r'\s*(?:<[A-Za-z0-9_+][A-Za-z0-9_./+-]*>|"[A-Za-z0-9_+][A-Za-z0-9_./+-]*")\s*(?://.*)?$')
_FILE_READERS = re.compile(r"\bincbin\b|__has_include|__has_embed")


def _forbidden_c_source(code: str) -> str | None:
    """The reason a C source is refused before compiling, or None. A compiler error quotes the line of a file it
    cannot parse, so `#include "/etc/passwd"` would otherwise print that file back to the student (TR-X-10)."""
    text = _BLOCK_COMMENT.sub(" ", _LINE_SPLICE.sub("", code))
    if _FILE_READERS.search(text):
        return "reading files at compile time is not allowed"
    for match in _INCLUDE.finditer(text):
        target = match.group(1)
        if not _PLAIN_HEADER.match(target) or ".." in target:
            return "only standard headers and plain file names can be included"
    return None


def _demote_for(profile: dict):
    """A preexec_fn that drops privileges and sets every limit of the profile."""
    def _demote() -> None:
        os.setsid()
        resource.setrlimit(resource.RLIMIT_CPU, (profile["cpu"], profile["cpu"] + 1))
        resource.setrlimit(resource.RLIMIT_AS, (profile["memory"],) * 2)
        resource.setrlimit(resource.RLIMIT_NPROC, (profile["processes"],) * 2)
        resource.setrlimit(resource.RLIMIT_FSIZE, (LIMITS["output_file_bytes"],) * 2)
        resource.setrlimit(resource.RLIMIT_NOFILE, (profile["files"],) * 2)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        os.setgroups([])
        os.setgid(RUN_GID)
        os.setuid(RUN_UID)
    return _demote


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


def _classify(language: str, returncode: int, timed_out: bool, stdout_size: int, stderr: str) -> str:
    if timed_out or returncode == -signal.SIGXCPU:
        return "time_limit"
    if stdout_size >= LIMITS["output_file_bytes"] or returncode == -signal.SIGXFSZ:
        return "output_limit"
    if returncode == 0:
        return "ok"
    if language == "python":
        if "MemoryError" in stderr:
            return "memory_limit"
        if "SyntaxError" in stderr or "IndentationError" in stderr:
            return "syntax_error"
        return "runtime_error"
    # java and c: a compile failure is reported before a program starts, so a crash here is a runtime error,
    # unless the out-of-memory signature shows in the error stream.
    if ("OutOfMemory" in stderr and "native thread" not in stderr) or "cannot allocate" in stderr:
        return "memory_limit"
    return "runtime_error"


def _read_capped(path: Path) -> str:
    with open(path, "rb") as handle:
        return handle.read(LIMITS["result_text_bytes"]).decode("utf-8", errors="replace")


def _spawn(cmd: list[str], run_dir: Path, stdin_bytes: bytes | None, wall_seconds: int, profile: dict) -> tuple[int, bool, int]:
    """Run one command as the unprivileged uid with every limit set, then kill that uid. Returns
    (returncode, timed_out, runtime_ms); stdout and stderr land in run_dir as `stdout` and `stderr`."""
    if stdin_bytes is not None:
        (run_dir / "stdin").write_bytes(stdin_bytes)
    with (
        open(run_dir / "stdin", "rb") if stdin_bytes is not None else open(os.devnull, "rb") as in_f,
        open(run_dir / "stdout", "wb") as out_f,
        open(run_dir / "stderr", "wb") as err_f,
    ):
        started = time.monotonic()
        proc = subprocess.Popen(
            cmd,
            cwd=run_dir,
            stdin=in_f,
            stdout=out_f,
            stderr=err_f,
            env=ENV,
            preexec_fn=_demote_for(profile),
            close_fds=True,
        )
        timed_out = False
        try:
            proc.wait(timeout=wall_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
        _kill_user_processes(RUN_UID)
        proc.wait()
        runtime_ms = int((time.monotonic() - started) * 1000)
    return proc.returncode, timed_out, runtime_ms


def _new_dir(language: str) -> Path:
    run_dir = (CWORK if language == "c" else WORK) / uuid.uuid4().hex
    run_dir.mkdir(mode=0o700)
    os.chown(run_dir, RUN_UID, RUN_GID)
    return run_dir


def _write_source(run_dir: Path, language: str, code: str) -> None:
    source = run_dir / SOURCE_FILE[language]
    source.write_text(code)
    os.chown(source, RUN_UID, RUN_GID)


def _compile(language: str, code: str) -> tuple[Path | None, dict | None]:
    """Compile once for the whole job. Returns (build_dir, None) on success, or (None, outcome) where the outcome is
    what every run of the job reports: the compiler's message, with no path of this container in it."""
    if language == "c":
        reason = _forbidden_c_source(code)
        if reason is not None:
            return None, {"status": "syntax_error", "stdout": "", "stderr": f"main.c: error: {reason}", "runtime_ms": 0}
    build_dir = _new_dir(language)
    try:
        _write_source(build_dir, language, code)
        returncode, timed_out, runtime_ms = _spawn(
            COMPILE_COMMANDS[language], build_dir, None, LIMITS["compile_wall_seconds"], COMPILE_PROFILES[language])
        if returncode == 0 and not timed_out:
            return build_dir, None
        message = "" if timed_out else _read_capped(build_dir / "stderr").replace(str(build_dir) + "/", "")
        status = "time_limit" if timed_out else "syntax_error"
        shutil.rmtree(build_dir, ignore_errors=True)
        return None, {"status": status, "stdout": "", "stderr": message or "compilation took too long", "runtime_ms": runtime_ms}
    except BaseException:
        shutil.rmtree(build_dir, ignore_errors=True)
        raise


def run_once(code: str, stdin: str, language: str = "python", build_dir: Path | None = None) -> dict:
    run_dir = _new_dir(language)
    try:
        if build_dir is None:
            _write_source(run_dir, language, code)
        else:
            for artifact in build_dir.glob(ARTIFACTS[language]):
                target = shutil.copy2(artifact, run_dir)
                os.chown(target, RUN_UID, RUN_GID)
        returncode, timed_out, runtime_ms = _spawn(
            COMMANDS[language], run_dir, stdin.encode(), LIMITS["wall_seconds"], PROFILES[language])
        stdout_size = (run_dir / "stdout").stat().st_size
        stderr = _read_capped(run_dir / "stderr")
        return {
            "status": _classify(language, returncode, timed_out, stdout_size, stderr),
            "stdout": _read_capped(run_dir / "stdout"),
            "stderr": stderr,
            "runtime_ms": runtime_ms,
        }
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def run_job(job: dict) -> list[dict]:
    language = job.get("language", "python")
    if language not in COMPILED:
        return [run_once(job["code"], r["stdin"], language) for r in job["runs"]]
    build_dir, failure = _compile(language, job["code"])
    if build_dir is None:
        return [dict(failure) for _ in job["runs"]]
    try:
        return [run_once(job["code"], r["stdin"], language, build_dir) for r in job["runs"]]
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)


def _valid(job: dict) -> bool:
    runs = job.get("runs")
    language = job.get("language", "python")
    return (
        isinstance(job.get("code"), str)
        and len(job["code"].encode()) <= LIMITS["max_code_bytes"]
        and isinstance(language, str)
        and language in SUPPORTED
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


def handle(job_path: Path) -> None:
    job_id = job_path.stem
    started = time.monotonic()
    job: object = None
    try:
        job = json.loads(job_path.read_text())
        if _valid(job):
            payload = {"runs": run_job(job)}
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
        "profiles": {"run": PROFILES, "compile": COMPILE_PROFILES},
        "run_uid": RUN_UID,
        "network_interfaces": sorted(os.listdir("/sys/class/net")),
        "root_filesystem_writable": rootfs_writable,
        "supervisor_effective_capabilities": cap_eff,
        "python": subprocess.run([PYTHON, "--version"], capture_output=True, text=True).stdout.strip(),
        "java": subprocess.run(["java", "-version"], capture_output=True, text=True).stderr.strip(),
        "cc": subprocess.run(["cc", "--version"], capture_output=True, text=True).stdout.splitlines()[0],
    }
    (JOBS / "config.json").write_text(json.dumps(report, indent=2))
    os.chmod(JOBS / "config.json", 0o644)


def _mtime(path: Path) -> float | None:
    # The API deletes job and result files on its own schedule, so any file can vanish here.
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return None


def main() -> None:
    setup()
    last_beat = 0.0
    while True:
        now = time.time()
        if now - last_beat >= 1:
            (JOBS / "heartbeat").write_text(str(now))
            last_beat = now
        for orphan in (JOBS / "out").glob("*.json"):
            mtime = _mtime(orphan)
            if mtime is not None and now - mtime > ORPHAN_RESULT_SECONDS:
                orphan.unlink(missing_ok=True)
        pending = [(m, p) for p in (JOBS / "in").glob("*.json") if (m := _mtime(p)) is not None]
        if pending:
            handle(min(pending)[1])
        else:
            time.sleep(0.05)


if __name__ == "__main__":
    main()
