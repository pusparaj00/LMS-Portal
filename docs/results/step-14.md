# Step 14 results: assignments and gradebook (F-04)

All runs on 2026-10-16 on the dev stack, branch `step-14-gradebook`. The TRD has no requirement for F-04, so the tests
are named after the PRD feature.

## What was built

- **Assignments** (migration 0012): a title, a due date and time, and one or more of the course's coding problems, each
  worth 0.5 to 100 points. The course's instructor creates, edits and deletes them; deleting keeps the submissions.
- **Scores are computed, not stored.** A problem scores its points times the share of tests its best on-time
  submission passed, hidden tests included. A submission at the due time exactly is on time. Late work is never counted
  and no penalty is applied; `with_late` shows what the score would be with it. Changing an assignment's problems or
  due date changes every score at once, and an erased student's scores go with their submissions.
- **Statuses:** complete, in progress, late work (a late attempt would raise the score), missing (past due, never tried),
  not started.
- **Endpoints:** `GET/POST /courses/{id}/assignments`, `PUT/DELETE /courses/{id}/assignments/{aid}`,
  `GET /courses/{id}/gradebook`, `GET /courses/{id}/export/gradebook?format=csv|json` (formula-safe, written to the audit
  trail). A student's assignment list carries only their own score.
- **Identity:** the gradebook and its download show the same label as the class view (the part of the email before
  the @), unlike the mastery exports, which carry numbers only.
- **Screens:** Assignments (instructor: form with problem picker and points, list with edit and delete), Gradebook
  (students by assignment, totals, Download CSV), and an Assignments section on the student's course page.

## Tests

`docker compose --profile test run --rm --build test`: **558 passed**, ruff clean. `backend/tests/test_gradebook.py`
has 12 tests:
- **Scores and statuses:** attempts at due minus 1 hour (1 of 4 tests), at the due time (3 of 4) and at due plus
  1 hour (4 of 4) on a 2-point problem give score 1.5, with late 2.0, status late. A student with everything passed is
  complete, and one who never tried is missing. Moving the due date makes the late attempt count, and the missing
  student becomes not started.
- **Hidden tests count:** a real submission passing only the 2 visible of 4 tests scores 0.5.
- **Validation (7 cases):** a multiple-choice item, a problem from another course, a duplicate problem, no problems,
  a due time without a time zone, zero points, an empty title.
- **Access:** an enrolled student, another instructor, an outsider and an anonymous caller each get what they should.
- **Download:** a title starting with `=` is neutralised, JSON matches CSV, and both downloads are audited.
- **Erasure and delete:** an erased student leaves the gradebook; deleting an assignment keeps the submissions.

## Browser run (Chromium, Playwright)

At 1366 x 768 and 390 x 844, with a throwaway instructor and students on `@eval.local`:
1. The instructor created "Week N" through the form (due tomorrow, "Add one", 2 points).
2. The student enrolled and saw "Not started · 0 / 2".
3. The student submitted a correct program in the editor ("Accepted"), and the course page then showed
   "Complete · 2 / 2".
4. The gradebook showed 2, Complete, and the total. Download CSV saved `gradebook-course-1211.csv` with the expected
   header.

There were no page errors, no 5xx responses and no horizontal page overflow. At 390 px the table scrolls inside its
frame, like the class heatmap.

## Not done

- Grades are not sent back to Moodle (LTI Assignment and Grade Services); that would be its own step.
- There are no manual overrides, rubrics, weighting categories or late penalties.
- Computing on read is one query per view, sized for a class, not for thousands of students.
