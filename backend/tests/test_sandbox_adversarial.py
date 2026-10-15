"""TR-V-01: every attack runs inside the sandbox container and must be contained.

Run with `pytest -s tests/test_sandbox_adversarial.py` to print the result table.
"""
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
    "memory bomb (growing list)": (
        "a = []\nwhile True:\n    a.append(' ' * 10**6)\n", "", "memory_limit", "",
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
    assert run.status == expected_status, (name, run.status, run.stderr)
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
    assert first.startswith("10002 10002")
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
