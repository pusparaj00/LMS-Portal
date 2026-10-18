# Step 41: Role dashboards, grades page, course analytics and ratings (F-63, F-64, F-65)

Date: 2026-10-19. Branch `step-41-edu-dashboards`, started from `step-40-profiles-dashboard`. The feature list comes from the
Edu-Hub portal in the workspace (`Edu-Hub-Portal/`); only what traces to a requirement ID was built.

## What was built

| ID | Change |
| --- | --- |
| F-63 | `GET /students/me/stats` and `/students/me/grades`; student dashboard with stat cards, course cards with progress and weakest concepts, upcoming assignments, latest announcements; `#/grades` page |
| F-64 | `GET /instructor/stats` and `/courses/{id}/analytics`; instructor dashboard with stat cards, course cards and upcoming assignments; `#/course/{id}/analytics` with a score-distribution chart and a per-assignment status chart (Recharts) |
| F-65 | Migration 0023 `ratings` (one per student per course, 1 to 5, optional review); `GET` and `PUT /courses/{id}/ratings`; rating form on the course page; anonymous reviews on the analytics page; erasure deletes a student's rating |

Not built (no requirement ID): video-recording submissions, lesson video upload, the Edu-Hub landing page and quiz.
New dependency: `recharts` 2.15.4, for the two charts; nothing already installed draws charts.

## Rules kept

Every figure is a query over the caller's rows: a student sees only their own scores, an instructor only courses they
teach (`can_access_course`). Ratings need an enrolment. Reviews carry no author and are stored and shown as text.
Mastery is only read, never written.

## Measured (2026-10-19)

| Check | Command | Result |
| --- | --- | --- |
| Lint | `ruff check .` (first step of the test service) | clean |
| Full backend suite | `docker compose --profile test run --rm test` | 692 passed, 1 failed in 251.63 s; the failure was a table count (33 vs 34) caused by the new table, fixed in `test_roles.py` and re-run (`tests/test_roles.py`: 7 passed) |
| New and related tests | `pytest -q tests/test_dashboards.py tests/test_access_matrix.py tests/test_contract.py tests/test_erasure.py` | 117 passed |
| Frontend | `npm run build` (runs `tsc --noEmit`) | built, no type errors |
| Migration | `select version_num from alembic_version` on the app database | `0023` |
| Health | `curl http://127.0.0.1:8000/api/v1/health` | `{"status":"ok","database":"ok","redis":"ok"}` |
| Browser, both roles | Playwright (Chromium, 1366 px) against `http://localhost:8080` | instructor and student dashboards, analytics, grades and rating save all rendered; no console errors |

The browser check used labelled preview accounts (`preview-*@demo.local`) and a "Preview course (sample data)" with
hand-inserted run results. Figures matched the database (1 of 6 student-assignment pairs complete = 17%; 2.67 of 6 points = 44%).
The suite was not re-run in full after the one-line `test_roles.py` change.
