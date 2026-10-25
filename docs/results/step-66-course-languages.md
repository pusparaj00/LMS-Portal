# Step 66: Java and C as course languages (F-94, TR-X-10, TR-L-13, TR-V-13)

All numbers below were measured on 2026-10-25 on this machine (Docker Desktop, one sandbox container limited to 1 CPU
and 512 MB). Commands run from `LMS-Portal`; the throwaway compose project `lmssb` was used so the live stack was not
touched until the end.

## What was built

- A course teaches one language (python, java or c), fixed at creation (`courses.language`, migration 0034). Problems,
  placement items, runs, grading, hints, explanations, the leak guard and the template fallback follow the problem's
  language. Hand-ins accept `.java`, `.c` and `.h` files. The editor highlights each language and the course list shows
  a language badge.
- Sandbox: Java (OpenJDK, `javac` once per job) and C (`cc` once per job) run in the same container under the same rules
  as Python (no network, read-only root, unprivileged uid, wall clock). Java has its own address-space, thread and file
  limits and a capped heap, because a JVM cannot start under the Python limits. C programs run from a separate tmpfs
  (`/cwork`) that allows exec; `/work` stays `noexec`. A C source that includes a file by absolute or parent path, or
  uses `incbin`, is refused before compiling, so a compiler error cannot print a container file back to the student.
- Question banks: `data/bank/java` (10 concepts, 18 coding problems, 12 tracing items) and `data/bank/c` (10 concepts,
  16 coding problems, 10 tracing items). Every concept has at least one problem. Imported into the live database as
  "Java Fundamentals" (course 1869) and "C Fundamentals" (course 1870).

## Bugs found and fixed on the way

- The uncommitted first version crashed every Java and C run (`SubprocessError`: a float CPU limit in `setrlimit`).
- C binaries could not start (`PermissionError`): Docker mounts a tmpfs `noexec` unless told otherwise.
- The problem-creation route validated a Java or C reference solution as Python.
- The test for "Divisible by four" never separated `% 4` from `% 2` (no even non-multiple of 4); a hidden test was added
  to both banks.
- One Java tracing item did not compile (two variables named `a`).

## Measurements

| Check | Command | Result |
| --- | --- | --- |
| Sandbox attack suite (Python, Java, C, compile-step attacks) | `pytest tests/test_sandbox_adversarial.py` | 41 passed in 53 s |
| Whole backend suite | `pytest -q` | 1130 passed, 0 failed (7 min 15 s) |
| Java and C end-to-end tests | `pytest tests/test_course_languages.py` | 17 passed (course language, correct run and mastery event, wrong run and template, compile error and its template, placement language, gradebook score, problem creation, difficulty rule, hand-in files) |
| Java bank | `python -m app.bank_import /data/bank/java --dry-run` | validated 30 of 30 |
| C bank | `python -m app.bank_import /data/bank/c --dry-run` | validated 26 of 26 |
| Wrong solutions (TR-V-13) | `python -m evaluation.wrong_solutions_compiled /data/bank` | 34 of 34 caught, each in the category its mistake is about |
| Front end | `npx tsc --noEmit` | no errors |
| Lint | `ruff check .` | all checks passed |
| Browser check, live app, Chromium 1366x900 | `node langcheck.cjs` (throwaway student) | course badge shown; editor shows the language's starter comment and highlighting; a wrong Java and a wrong C submission fail with the explain panel offered; the correct ones are Accepted; 0 console errors |

Sandbox latency (median of 5, includes compile; `run_batch` from the test container):

| Language | 1 test | 5 tests |
| --- | --- | --- |
| Python | 0.05 s | 0.15 s |
| Java | 0.60 s | 0.90 s |
| C | 0.05 s | 0.05 s |

## What is not measured or not done

- The verifier and leak guard for Java and C are covered by tests and the wrong-solution check, but not measured on real
  model explanations (no LLM run for these languages yet). TR-L-13 needs that before any quality claim.
- Placement, mastery and misconception parameters are the Python defaults. Nothing says they suit Java or C; they need
  the pilot (TR-M-05).
- Difficulty estimates (F-23) exist only for Python: a Java or C problem needs a difficulty chosen by the teacher.
- The two new banks are smaller than the Python bank (35 problems, 26 tracing items), and the difficulty values are the
  author's judgement, not calibrated.
- The attack suite has no case for every possible compiler trick; the include filter is a deliberate narrow rule.
- A throwaway account `langcheck-1792943982481@eval.local` (id 10387) remains on the live database; it can only be
  removed through the app's erasure request.
