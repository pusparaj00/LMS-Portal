# Step 33: audit after the interface change

Date: 2026-10-17. Branch `step-33-audit`.

## Fixed

| # | Problem | Evidence | Fix | Proof |
| --- | --- | --- | --- | --- |
| A1 | A student could get the full solution of a practice problem as a worked example (hint level 3), and that same problem could then be offered to them as a probe or a placement item. That raised their mastery with extra weight. Left open in Step 18. | Code: `hints.worked_example` recorded nothing; `probe.select_probe` and the placement selection did not know what had been shown | New table `worked_examples_seen` (migration 0020, API role SELECT/INSERT/DELETE, cascades with the user or problem). Hint level 3 records the problem shown. Probes and placement items skip it. Erasure deletes the rows. | `test_a_problem_whose_worked_solution_was_shown_is_never_used_as_a_probe`, `test_a_problem_whose_worked_solution_was_shown_is_not_a_placement_item`; the erasure test now covers the table |
| A2 | Step 32 moved Account and Privacy into the side menu. The privacy notice (version 2026-10-v3), the consent message, the forced-password message and the README all say "in the top bar". Rewording the notice would make every student agree again. | `grep -rn "top bar"` | Account and Privacy are back in the top bar, and the side menu keeps only course links | Browser run below |
| A3 | Code typed in the editor was lost when the student opened another page and came back, which the new menu makes easy to do | Code: `ProblemPage` reset the editor on every visit | The unsent draft is kept per problem for the browser session, and logging out removes every draft | Browser: typed, left, came back; text still there; storage empty after logout |
| A4 | Concept tags on the problem page showed raw names (`variables_io`) | Screenshot | Shown as "variables io" | Screenshot |
| A5 | On a phone the header wrapped "Adaptive LMS" and "Log out" onto two lines | Screenshot at 390 px | Header items no longer wrap, and the header is smaller on phones | Screenshot |

## Checked, no change needed

- Chat uses the client's `problem_id` only when the student is enrolled in that problem's live course (`handlers._course_id`), and reads submissions only by the caller's id.
- Login and registration are rate-limited by IP and by email. nginx overwrites `X-Forwarded-For`, so it cannot be forged through the web front end.
- Due dates are stored with a time zone, and the browser converts its local time to UTC.
- `npm audit`: 0 vulnerabilities.

## Tests

- `docker compose --profile test run --rm test` (ruff and pytest) on a freshly reset `lms_test`: **665 passed**.
  The run before the reset failed on rows left behind by a run that lacked the new table; `tests.prepare_db --reset`
  is the documented remedy.
- Browser check (Playwright, Chromium) on a throwaway stack `-p lmsui` (fresh seed, removed afterwards). 18 pages
  across the three roles at 1366 and 390 px, 36 screenshots. Result: no console errors and no page wider than the window.
  The draft survived navigation, and session storage was empty after logout.

## Open (not fixed)

- The API port 8000 is published on 127.0.0.1, and a caller there can set `X-Forwarded-For` and get a fresh login
  rate-limit bucket. It is local only. When the system moves to a production host, do not publish this port.
- Backend dependencies were not scanned: `pip-audit` is not installed, and installing it needs approval.
