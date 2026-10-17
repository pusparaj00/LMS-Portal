# Step 36: model-drafted practice problems, checked before an instructor sees them (TR-L-10)

Date: 2026-10-17. Branch `step-36-problem-drafts`.

## What changed

- `POST /problems/draft` (course instructor only, 10 per hour). A model writes a problem for one concept: a title,
  a statement, 4 to 8 tests (at least two hidden), a reference solution, and a solution with one planted mistake plus
  the test category it should fail. The draft is returned only if all of these hold in the sandbox:
  - the reference solution passes every test;
  - the planted mistake fails, and fails in the named category;
  - the title is new to the course.
  Otherwise the model gets the reasons once and tries again. If the second try also fails, the instructor gets a 422
  that lists the reasons.
- Nothing is stored. The draft fills the "Add a coding problem" form, and the instructor reads and changes it, then
  saves it through `POST /problems`. That path runs the reference against every test again (TR-D-04). Only then is the
  problem in the bank, where probes can use it. The planted wrong solution is never sent to the browser.
- The model gets the concept's name and the titles of the course's existing problems. It gets no student data.
- Audit events: `problem.drafted` (with the number of attempts) and `problem.draft_rejected`.

## Checks

- Full suite (`docker compose --profile test run --rm test`): ruff clean, **672 passed**.
- `tests/test_problem_draft.py`, 5 tests:
  - a checked draft is offered and nothing is saved until the instructor saves it;
  - a wrong solution that is not caught is retried once with the reasons, then refused;
  - a reply that cannot be read is refused;
  - a second attempt succeeds after the first is rejected;
  - access is checked (another instructor 403, a student 403, an unknown concept 404), and a model failure gives 503.
  The access matrix has the new route.
- Live model on the throwaway stack (`-p lmsui`, provider order gemini first), 2026-10-17 06:27 UTC, through
  `POST /problems/draft` as the demo instructor:

| Concept | Result | Time | Attempts | Tests | Planted mistake caught in |
| --- | --- | --- | --- | --- | --- |
| loops | offered | 5.5 s | 1 | 5 | basic |
| strings | offered | 3.9 s | 1 | 4 | basic |
| dictionaries | offered | 4.8 s | 1 | 4 | duplicates |

- Browser (Playwright): as the instructor, choosing "recursion" and pressing "Draft a problem" filled the form
  ("recursive countdown", 4 test rows) and showed both check results. The first try of this script waited 90 s and
  timed out before the reply arrived. The second try finished within the 40 s it waited. That model call was not
  timed separately.

## Not covered

- Generated *probes* chosen automatically for students without an instructor's review are not built. The project rule
  is that probes come from the vetted bank, so a person stays between the model and the students.
- The model's titles come back in lower case and its statements are sometimes long. The instructor edits them in the form.
