# Step 46 audit: bugs found and fixed (steps 40 to 46)

Date: 2026-10-19. Branch `step-46-audit` (from `step-46-quizzes`).

## Method

Code reading of the unaudited areas (run with input, course content, dashboards, quizzes, open chat, LLM chain), plus
checks that run against the code:

- Every endpoint of the OpenAPI file called as student, instructor, admin and anonymous, in-range and out-of-range ids,
  8 kinds of garbage body: **0 server errors** (temporary test, removed afterwards).
- Every route called with the id 99999999999 as an instructor, on the live API: **0 server errors**.
- 20 pages loaded in a browser as a student and as an instructor (Playwright, 1280x900): **no console errors, page
  errors, overflow or empty pages**; the only 404s were a deliberate request for a quiz that does not exist.
- 8 simultaneous submits of a 1-attempt quiz: **one accepted, seven refused, one attempt stored**.
- `npm audit --omit=dev`: 0 vulnerabilities. Secret scan: passed (212 commits, 362 files).
- Live service logs: no ERROR or 5xx lines (covers only the containers' last 20 minutes).

## Bugs fixed

1. **Open chat could hand out a graded solution (my step 45).** With no problem open, an open answer was compared with
   no reference, so a student could close the problem page, paste an assignment's statement and receive code. Code in
   an open answer is now also compared with the reference solution of every problem in the student's live courses and
   withheld when it matches (`chat/handlers.py`). Test: `test_closing_the_problem_page_does_not_let_a_course_solution_through`.
2. **A dead LLM provider cost time on every request.** A provider that could not be reached (for example a local model
   that is not running) set no cooldown, so each request waited out its retries and backoff first (log showed
   `cooldown_s: 0.0`, about 4.5 s per call on this PC). A connection failure now stops retrying that provider and cools
   it for 60 s (`llm/adapter.py`). Test: `test_an_unreachable_provider_is_not_retried_and_is_skipped_for_the_next_requests`.
3. **Students were offered a quiz that was not published (my step 46).** An assignment holding a draft quiz showed
   "Take quiz", which led to "not found". The assignment list now carries `published` and the page says "not open yet".
   Test: `test_an_assignment_tells_students_when_its_quiz_is_not_open_yet`.

## Results

782 tests passed (`docker compose --profile test run --rm test`), ruff clean, `tsc` clean.

## Not fixed, for your decision

- A quiz that is not in an assignment shows its right answers right after each attempt when `show_answers` is on (the
  teacher's choice), so retakes of such a quiz can be answered from the review.
- Placement and probe gaming through worked examples (from the step 18 audit) is still open.
- The first provider in `.env` on this PC is the `local` model, which is not running; with fix 2 it now costs one
  failed connection per minute, not one per request. Removing it from `.env` would remove even that.
