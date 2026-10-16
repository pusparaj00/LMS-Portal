# Step 18: third bug audit

Run on 2026-10-16 on branch `step-18-audit`. It covered the code added since the second audit (Step 15): grade
passback (Step 16) and announcements (Step 17). It also covered parts no audit had reached: the hint ladder, the
feedback panel and the problem page.

| # | Bug | How it was found | Fix | Proof |
| --- | --- | --- | --- | --- |
| H1 | The third hint (a worked example on a different problem) could show the full reference solution of a problem that is set in an assignment. A student could fail any practice problem on purpose and be handed the answer to graded work. This was safe before Step 14 added assignments. | Live: hint 3 on "Practice" returned the full solution of "Graded: factorial", which was in an assignment | Worked examples skip every problem that belongs to an assignment | Test in `test_gradebook.py`: no example while graded; the same problem is offered again once the assignment is deleted |
| H2 | A run or submission still in flight when the student moved to another problem showed its result, and its help panel, on the new problem's page | Code review in the first audit (Step 11), confirmed by reading `ProblemPage.tsx` | A finished request is shown only if its problem is still the one on screen | Browser: a 4-second run started on one problem, then a switch to another; the new page showed no result |

Suite: `docker compose --profile test run --rm --build test`, **585 passed**, ruff clean.

## Seen but not changed

- A worked example can still show the solution of a non-graded problem that is later offered as a probe or a placement
  item, which would let a student raise their own mastery estimate. Mastery does not count toward grades, so this is
  smaller than H1. Closing it needs a record of which examples each student has seen.
- When an LMS student's data is erased here, the last score already sent stays in the LMS gradebook. Removing it there is
  the LMS's job.
