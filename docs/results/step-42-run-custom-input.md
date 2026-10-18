# Step 42: Run code on your own input (F-14)

Date: 2026-10-19. Branch `step-42-run-custom-input`, from `step-41-edu-dashboards`.

## Finding

A **Run examples** button already existed, but it is disabled unless the signed-in user is a student (an instructor sees
"Only students can run code"), and there was no way to type an input. F-14 adds a Run button with an input box.

## What changed

| ID | Change |
| --- | --- |
| F-14 | `POST /submissions/run-custom` (problem id, code, optional stdin up to 10,000 characters): one sandbox run, nothing stored, no grading, no test case or hidden data in the reply; rate limit `run_custom` 60 per minute per user, separate from example runs |
| F-14 | Problem page: input box, **Run**, **Run examples**, **Submit**; the output panel shows stdout, stderr, runtime and a plain-language error. Instructors and admins can use Run on problems of their courses |
| F-14 | The runner's scratch path (`/work/<id>/`) is removed from tracebacks |

Access follows the problem's course (`can_access_course`); a student must have agreed to the notice. Student code runs only in the sandbox.

## Measured (2026-10-19)

| Check | Command | Result |
| --- | --- | --- |
| Lint | `ruff check .` | clean |
| Full backend suite | `docker compose --profile test run --rm test` | 704 passed in 267.28 s (693 before this step, 11 new in `tests/test_run_custom.py`) |
| Browser | Playwright, Chromium 1366 px, live stack at `localhost:8080`, throwaway student | buttons Run / Run examples / Submit; input `14` to `print(n * 3)` printed `42`; empty input gave `EOFError` with `File "main.py"` and no runner path; no console errors |

The throwaway account (`ui-check@eval.local`) was deleted after the check.
