# Step 48: To-do, calendar and in-app notifications (F-78, F-79, F-80)

Date: 2026-10-19. Branch `step-48-todo-calendar-notifications` (from `step-47-submissions-grading`). Migration 0027.

## What was built

- **To-do (F-78).** `GET /students/me/todo` and a To-do page for students with Assigned, Missing and Done tabs, grouped by
  Earlier, This week, Next week and Later (weeks start on Monday, in the viewer's own time). An assignment is done when its
  score is complete, or when it asks only for handed-in work and the work is turned in; otherwise it is missing once the
  due time has passed and assigned before. Every assignment has a due date, so the "no due date" group from the
  Classroom file never appears; the PRD row now says so. Archived courses are left out.
- **Calendar (F-79).** `GET /calendar?start&end[&course_id]` and a Calendar page with month and week views, a course
  filter and a Today button. A student sees the due dates of their live courses with a state (missing items in red);
  an instructor sees the due dates of the courses they teach. A range must carry a time zone and span at most 100 days.
- **Notifications (F-80).** Table `notifications` (migration 0027), a bell with an unread count in the top bar (checked
  again every minute) and a Notifications page. Created for: a new announcement (every enrolled student), work turned in
  (the instructor), work returned, single or all at once (the student), a new private comment (the other person), and a
  due-soon notice (students, for unfinished work due within 48 hours, once per assignment). A notification holds a short
  title and an in-app link only, never a score, a comment or feedback. Read one, read all; only the owner can mark a
  notification read. No email is sent.
- **Erasure.** A student's notifications are removed with their account (TR-S-07).

## Evidence

- Tests (`docker compose --profile test run --rm test`, 2026-10-19): 835 passed, ruff clean, `tsc --noEmit` clean.
  17 new tests in `tests/test_planner_notifications.py` cover the to-do states and order, the done rule, isolation and
  archived courses, calendar range, roles and bad ranges, who is notified for each event (and who is not), no private
  text in any notification, Return all, read and read-all with ownership, the once-only due-soon notice (and none for far
  or finished work or for teachers), a removed student, and in-app links. The access matrix and table count were extended.
- Browser (Playwright, 1280x1000, throwaway `@eval.local` accounts): a student with three assignments and one
  announcement saw the bell show 2, the To-do tab counts (Assigned 2, Missing 1, Done 0) with the right groups, the
  calendar month (3 items) and week (1 item) views, both notifications; opening one went to the course and the bell
  dropped to 1. No console or API errors.
- Backup before migrating: `backup/lms-2026-10-19-before-step48.dump` (git-ignored). The score function did not change.

## Not checked, not built

- Phone-width layout of the calendar and the new pages was not checked in a browser (a narrow-screen rule exists).
- Notifications are not sent by email (an SMTP service would need your approval); nobody is notified of a new assignment.
- A student who only handed in work still sees the assignment as done before it is graded, by design (see the to-do rule).
