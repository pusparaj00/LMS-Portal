# Step 32: a clear interface for each role (TR-P-09, F-60, F-61, F-01)

Date: 2026-10-17. Branch `step-32-role-ui`.

## What changed

| Area | Change | Requirement |
| --- | --- | --- |
| Every page | Side menu per role, with the current page marked and the course's own links once a course is open; it becomes a scrolling strip under 52rem width. Name and role badge in the header, skip link, a new page opens at the top. | TR-P-09, F-01 |
| Student | The course page opens on a "Continue" panel: the placement test if it is not taken, otherwise the recommended next problem and its reason. A progress panel shows problems solved and the three weakest concepts. Problems are grouped by their main concept, each marked Solved, In progress or Not started. | F-60 |
| Instructor | Course page header with "Add a problem"; course links moved into the menu. The class heatmap keeps the concept headings and student names in view while scrolling, and has a colour legend. | F-61 |
| Admin | Signs in to Users. Counts per role, the new-account form folds away, the list is a table of 25 rows per page. "All courses" has a title search. | F-01 |
| API | `GET /problems?course_id=` adds `my_status` (`solved`, `tried`, `new`) for the student who asks, from their own submissions only; staff get `null`. | F-60 |

No page address, permission or API field changed apart from the added `my_status`. No new dependency.

## Checks

- `npx tsc --noEmit` and `npx vite build`: pass.
- `docker compose --profile test run --rm test` (ruff and pytest): 662 passed, 1 failed. The failure was the frozen API
  contract, because `my_status` was added. `backend/openapi.json` was regenerated (the only difference is that field), and
  `pytest tests/test_contract.py tests/test_submissions.py` then passed 15 of 15.
- New test `test_the_problem_list_shows_each_student_only_their_own_progress`: new, then tried, then solved; another student still sees new; an instructor sees null.
- Browser check on a throwaway stack (`docker compose -p lmsui`, fresh seed, removed afterwards with `down -v`). Chromium via Playwright signed in as the seeded student, the seeded instructor and a throwaway admin. It opened 17 pages at 1366 px and 390 px (34 screenshots). Result: no console errors, and no page wider than the window. Two problems found this way and fixed: the admin table pushed a 390 px page 111 px wide, and the phone menu strip left a blank gap.

## Not covered

- Screens not reworked: the problem page, placement test, notes, assignments, gradebook, account and privacy pages. They take the new colours, buttons and menu but keep their layout.
- No screen-reader run; keyboard focus and labels were checked only in the code.
