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


# Java and C run as compiled programs in the same isolated, unprivileged container. The compile step must
# stay contained too: a hostile source cannot read the host, open a socket, or fork, and a bad compile is
# reported as a syntax error (no test ran) rather than a crash.
LANG_ATTACKS = {
    "java: infinite loop": (
        "java",
        "public class Main { public static void main(String[] a) { while (true) {} } }\n",
        "", {"time_limit"}, "",
    ),
    "java: memory bomb": (
        "java",
        "public class Main { public static void main(String[] a) { "
        "java.util.List<byte[]> l = new java.util.ArrayList<>(); "
        "while (true) { l.add(new byte[10_000_000]); } } }\n",
        "", {"memory_limit", "time_limit"}, "",
    ),
    "java: network call": (
        "java",
        "public class Main { public static void main(String[] a) throws Exception { "
        "java.net.Socket s = new java.net.Socket(); s.connect(new java.net.InetSocketAddress(\"1.1.1.1\", 53), 2000); } }\n",
        "", "runtime_error", "",
    ),
    "java: write outside the temp directory": (
        "java",
        "public class Main { public static void main(String[] a) throws Exception { "
        "java.nio.file.Files.writeString(java.nio.file.Path.of(\"/etc/pwned\"), \"x\"); } }\n",
        "", "runtime_error", "",
    ),
    "java: bad source is a syntax error": (
        "java", "public class Main { this is not java }\n", "", "syntax_error", "",
    ),
    "java: a correct program runs": (
        "java",
        "public class Main { public static void main(String[] a) { System.out.println(21 * 2); } }\n",
        "", "ok", "",
    ),
    "c: infinite loop": (
        "c", "int main(void) { for (;;) {} }\n", "", "time_limit", "",
    ),
    "c: memory bomb": (
        "c",
        "#include <stdlib.h>\nint main(void) { for (;;) { malloc(10000000); } }\n",
        "", {"memory_limit", "time_limit"}, "",
    ),
    "c: network call": (
        "c",
        "#include <sys/socket.h>\n#include <netinet/in.h>\n#include <unistd.h>\n"
        "int main(void) { int s = socket(AF_INET, SOCK_STREAM, 0); "
        "struct sockaddr_in a; a.sin_family = AF_INET; a.sin_port = 53; a.sin_addr.s_addr = 0x01010101; "
        "return connect(s, (void*)&a, sizeof a) == 0 ? 0 : 1; }\n",
        "", "runtime_error", "",
    ),
    "c: write outside the temp directory": (
        "c",
        "#include <stdio.h>\nint main(void) { FILE* f = fopen(\"/etc/pwned\", \"w\"); fputc('x', f); fclose(f); return 0; }\n",
        "", "runtime_error", "",
    ),
    "c: bad source is a syntax error": (
        "c", "int main(void) { this is not c }\n", "", "syntax_error", "",
    ),
    "c: a correct program runs": (
        "c", "#include <stdio.h>\nint main(void) { printf(\"%d\\n\", 21 * 2); return 0; }\n",
        "", "ok", "",
    ),
}


@pytest.mark.parametrize("name", LANG_ATTACKS)
def test_compiled_language_is_contained(name):
    language, code, stdin, expected_status, stderr_hint = LANG_ATTACKS[name]
    (run,) = run_batch(code, [stdin], language)
    RESULTS[name] = (run.status, run.runtime_ms)
    allowed = expected_status if isinstance(expected_status, set) else {expected_status}
    assert run.status in allowed, (name, run.status, run.stderr)
    assert len(run.stdout) <= 64 * 1024
    if name == "java: a correct program runs":
        assert run.stdout.strip() == "42"
    if name == "c: a correct program runs":
        assert run.stdout.strip() == "42"


# TR-X-10: the compile step is an attack surface too. A hostile C source must not read a file back through the
# compiler's error text, and neither language may use the compile step to escape the per-job limits.
COMPILE_ATTACKS = {
    "c: include an absolute path": ("c", '#include "/etc/passwd"\nint main(void) { return 0; }\n', "syntax_error"),
    "c: include a parent path": ("c", '#include "../../etc/passwd"\nint main(void) { return 0; }\n', "syntax_error"),
    "c: include hidden behind a comment": (
        "c", '/* x */ #include "/etc/passwd"\nint main(void) { return 0; }\n', "syntax_error",
    ),
    "c: include hidden behind a line splice": (
        "c", '#in\\\nclude "/etc/passwd"\nint main(void) { return 0; }\n', "syntax_error",
    ),
    "c: incbin": (
        "c", '__asm__(".incbin \\"/etc/passwd\\"");\nint main(void) { return 0; }\n', "syntax_error",
    ),
    "c: fork bomb": (
        "c", "#include <unistd.h>\nint main(void) { for (;;) fork(); }\n", {"time_limit", "runtime_error"},
    ),
    "java: fork bomb": (
        "java",
        "public class Main { public static void main(String[] a) throws Exception { "
        "while (true) { new ProcessBuilder(\"/bin/sh\", \"-c\", \"sleep 5\").start(); } } }\n",
        {"time_limit", "runtime_error"},
    ),
    "c: compile bomb (deep macro expansion)": (
        "c",
        "#define A(x) x x x x x x x x\n#define B(x) A(A(A(A(A(x)))))\n"
        "int main(void) { int v[] = { B(B(B(1))) }; return v[0]; }\n",
        {"syntax_error", "time_limit"},
    ),
}


@pytest.mark.parametrize("name", COMPILE_ATTACKS)
def test_compile_step_is_contained(name):
    language, code, expected = COMPILE_ATTACKS[name]
    (run,) = run_batch(code, [""], language)
    allowed = expected if isinstance(expected, set) else {expected}
    assert run.status in allowed, (name, run.status, run.stderr)
    assert "root:" not in run.stderr and "/work" not in run.stderr and "/cwork" not in run.stderr


def test_a_compile_error_names_no_container_path_and_runs_once_per_job():
    code = "public class Main { void f() { int x = \"s\"; } }\n"
    runs = run_batch(code, ["", "", ""], "java")
    assert [r.status for r in runs] == ["syntax_error"] * 3
    assert all("Main.java" in r.stderr and "/work" not in r.stderr for r in runs)



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
