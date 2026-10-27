"""TR-V-01: every attack runs inside the sandbox container and must be contained.

Run with `pytest -s tests/test_sandbox_adversarial.py` to print the result table.
"""
import threading
import time

import pytest

from app.sandbox import run_batch

COUNT_STUDENT_PROCESSES = """
import os
n = 0
for pid in filter(str.isdigit, os.listdir("/proc")):
    try:
        uid = int(next(l for l in open(f"/proc/{pid}/status") if l.startswith("Uid:")).split()[1])
    except (OSError, StopIteration):
        continue
    n += uid == os.getuid()
print(n)
"""

ATTACKS = {
    "infinite loop": ("while True:\n    pass\n", "", "time_limit", ""),
    "sleep past wall clock": ("import time\ntime.sleep(60)\n", "", "time_limit", ""),
    "memory bomb (one allocation)": ("x = bytearray(10**10)\n", "", "memory_limit", ""),
    # Allocation speed decides whether the memory or the CPU limit stops this one first.
    "memory bomb (growing list)": (
        "a = []\nwhile True:\n    a.append(' ' * 10**6)\n", "", {"memory_limit", "time_limit"}, "",
    ),
    "fork bomb": (
        "import os\nwhile True:\n    try:\n        os.fork()\n    except OSError:\n        pass\n",
        "", "time_limit", "",
    ),
    "network call": (
        "import socket\nsocket.create_connection(('1.1.1.1', 53), timeout=2)\n",
        "", "runtime_error", "unreachable",
    ),
    "network call to loopback service": (
        "import socket\nsocket.create_connection(('127.0.0.1', 8000), timeout=2)\n",
        "", "runtime_error", "refused",
    ),
    "symlink to a host path": (
        "import os\nos.symlink('/proc/1/environ', 'link')\nprint(open('link').read())\n",
        "", "runtime_error", "Permission",
    ),
    "list the job directories": (
        "import os\nprint(os.listdir('/jobs/in'))\n", "", "runtime_error", "Permission",
    ),
    "list the claimed jobs": (
        "import os\nprint(os.listdir('/jobs/claimed'))\n", "", "runtime_error", "Permission",
    ),
    "write outside the temp directory": (
        "open('/etc/pwned', 'w').write('x')\n", "", "runtime_error", "Read-only",
    ),
    "write into the results directory": (
        "open('/jobs/out/forged.json', 'w').write('{}')\n", "", "runtime_error", "Permission",
    ),
    "very large output": ("while True:\n    print('x' * 1000)\n", "", "output_limit", ""),
    "shell characters in input": (
        "print(input())\n", "$(touch /tmp/pwned); rm -rf / ; `id` | cat &\n", "ok", "",
    ),
}

RESULTS: dict[str, tuple[str, int]] = {}


@pytest.mark.parametrize("name", ATTACKS)
def test_attack_is_contained(name):
    code, stdin, expected_status, stderr_hint = ATTACKS[name]
    (run,) = run_batch(code, [stdin])
    RESULTS[name] = (run.status, run.runtime_ms)
    allowed = expected_status if isinstance(expected_status, set) else {expected_status}
    assert run.status in allowed, (name, run.status, run.stderr)
    assert stderr_hint.lower() in run.stderr.lower(), (name, run.stderr)
    assert len(run.stdout) <= 64 * 1024
    if name == "shell characters in input":
        assert run.stdout.strip() == stdin.strip()


def test_host_is_unchanged_and_no_processes_survive():
    code = (
        "import os\n"
        "print(os.path.exists('/etc/pwned'), os.path.exists('/tmp/pwned'),"
        " sorted(os.listdir('/jobs/out')) if False else '')\n"
    )
    (run,) = run_batch(code, [""])
    assert run.stdout.strip() == "False False"
    (count,) = run_batch(COUNT_STUDENT_PROCESSES, [""])
    assert count.stdout.strip() == "1"


def test_sandbox_has_no_network_interface_but_loopback():
    (run,) = run_batch("import os\nprint(sorted(os.listdir('/sys/class/net')))\n", [""])
    assert run.stdout.strip() == "['lo']"


def test_student_process_runs_unprivileged_with_no_capabilities():
    code = "import os\nprint(os.getuid(), os.getgid(), open('/proc/self/status').read())\n"
    (run,) = run_batch(code, [""])
    first, *_ = run.stdout.split("\n", 1)
    uid, gid = first.split()[:2]
    assert int(uid) in range(10002, 10006) and gid == "10002"
    assert "CapEff:\t0000000000000000" in run.stdout


def test_one_job_cannot_see_another_jobs_files():
    code = "import os\nprint(sorted(os.listdir('/work')))\n"
    (run,) = run_batch(code, [""])
    assert run.status == "runtime_error" and "Permission" in run.stderr


def test_sandbox_still_answers_after_all_attacks():
    (run,) = run_batch("print('alive')\n", [""])
    assert (run.status, run.stdout.strip()) == ("ok", "alive")


def test_print_result_table(capsys):
    lines = ["| Attack | Contained result | Runtime ms |", "| --- | --- | --- |"]
    lines += [f"| {name} | {status} | {ms} |" for name, (status, ms) in RESULTS.items()]
    table = "\n".join(lines)
    with capsys.disabled():
        print("\n" + table)


def test_sandbox_survives_jobs_withdrawn_while_queued():
    # The API deletes a job file when it gives up waiting; the runner must not crash on that.
    import os
    import uuid
    from pathlib import Path

    jobs_in = Path(os.environ["JOBS_DIR"]) / "in"
    for _ in range(400):
        path = jobs_in / f"{uuid.uuid4().hex}.json"
        path.write_text('{"code": "print(1)", "runs": []}')
        path.unlink(missing_ok=True)
    (run,) = run_batch("print('alive')\n", [""])
    assert (run.status, run.stdout.strip()) == ("ok", "alive")


def run_together(*jobs):
    """Starts each job at once from its own thread, as concurrent requests would, and returns their outcomes in order."""
    outcomes = [None] * len(jobs)

    def go(n, code):
        (outcomes[n],) = run_batch(code, [""])

    threads = [threading.Thread(target=go, args=(n, code)) for n, code in enumerate(jobs)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return outcomes


WAIT_THEN_SAY = "import time\ntime.sleep(4)\nprint('first finished')\n"

PROBE_OTHER_JOBS = """
import os, signal, time
time.sleep(1)
mine = os.getuid()
others = []
for pid in filter(str.isdigit, os.listdir("/proc")):
    try:
        uid = int(next(l for l in open(f"/proc/{pid}/status") if l.startswith("Uid:")).split()[1])
    except (OSError, StopIteration):
        continue
    if uid not in (0, mine):
        others.append(int(pid))
denied = 0
for pid in others:
    for attempt in (lambda: os.readlink(f"/proc/{pid}/cwd"), lambda: open(f"/proc/{pid}/environ").read(),
                    lambda: os.kill(pid, signal.SIGKILL)):
        try:
            attempt()
        except PermissionError:
            denied += 1
print(len(others), denied)
"""


def test_a_job_running_beside_it_cannot_be_read_or_signalled():
    first, probe = run_together(WAIT_THEN_SAY, PROBE_OTHER_JOBS)
    found, denied = map(int, probe.stdout.split())
    assert found >= 1 and denied == 3 * found, probe.stdout
    assert first.stdout.strip() == "first finished"  # the probe's SIGKILL attempts did not reach it


def test_ending_one_run_does_not_kill_a_run_beside_it():
    first, spinner = run_together(WAIT_THEN_SAY, "while True:\n    pass\n")
    assert spinner.status == "time_limit"
    assert (first.status, first.stdout.strip()) == ("ok", "first finished")


def test_four_jobs_run_at_the_same_time():
    started = time.monotonic()
    outcomes = run_together(*["import time\ntime.sleep(2)\nprint('done')\n"] * 4)
    elapsed = time.monotonic() - started
    assert [o.stdout.strip() for o in outcomes] == ["done"] * 4
    assert elapsed < 5, elapsed  # one after another would take at least 8 s
