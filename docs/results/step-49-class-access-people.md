# Step 49: Class access and people (F-81, F-82, F-83)

Date: 2026-10-19. Branch `step-49-class-access-people` (from `step-48-todo-calendar-notifications`). Migration 0028.

## What was built

- **Class code (F-81).** Every course has a 10-character code (migration 0028 backfilled all 63 live courses; a database
  trigger gives a code to any course created later, whichever way it is created). `POST /courses/join` joins a student by
  code, however it is typed (case, spaces and dashes ignored). An unknown, closed or archived code all get the same 404,
  and tries are limited to 10 a minute per student. The teacher sees the code and an invite link (`#/join/CODE`), can copy
  them, close or reopen the class, and reset the code (the old code and link stop working; students already in stay).
  Joins, refusals and resets are audited without the code itself.
- **Open enrolment is gone.** `POST /courses/{id}/enroll` is removed. A student's course list holds only the courses they
  joined, a teacher's only the courses they teach, so nobody can browse courses they have no part in. The Courses page
  became a "Join a class" box.
- **People (F-82).** `GET /courses/{id}/people`: a teacher sees every teacher and student; a student sees the teachers and
  the number of classmates, never a classmate's name. The owner can add a co-teacher by the email of an existing active
  instructor account and remove them; a co-teacher teaches like the owner (grading, content, gradebook, code, queue,
  notifications) except for archiving the course and changing who teaches it. A teacher can mute a student's private
  comments (the student can still read them; the teacher can still write). Co-teachers are recorded in `course_teachers`,
  which also holds the owner (kept in sync by a trigger); the access check, dashboards, calendar and the to-review queue
  read it.
- **Course details (F-83).** Optional section, subject and colour, set from the course settings, shown on the course
  list rows and the course page header; sending null clears one.
- **Privacy.** A student never receives a classmate's name or email; the count only.

## Evidence

- Existing data: the live database went to migration 0028 with 63 of 63 courses having a code and their owner as a teacher
  (`select` after migrating), 2026-10-19. Backup first: `backup/lms-2026-10-19-before-step49.dump`.
- Tests (`docker compose --profile test run --rm test`, 2026-10-19): 866 passed, ruff clean, `tsc --noEmit` clean. 24 new tests in
  `tests/test_class_access.py` cover the code shape and trigger, joining by code in any typing, identical answers for wrong,
  closed and archived codes, closing and reopening, reset, who may see or change the code, the rate limit, the removed open
  route, per-role course lists, details set and cleared with 7 bad inputs refused, people for teacher and student without a
  classmate's name, adding and removing a co-teacher (existing instructors only, no student or unknown email, owner
  cannot be removed, co-teacher cannot archive or add teachers), co-teacher notification and grading, muting, audit
  without the code. 41 existing call sites that enrolled students were moved to a shared `enroll` helper that joins with
  the real code; the demo, load and evaluation scripts join the same way (`evaluation/join.py`).
- A bug found by the access-matrix test and fixed: an admin asking for the code or people of a course that does not
  exist got a 500; it is now a 404 (regression test added).
- Browser (Playwright, 1280x1000, throwaway `@eval.local` accounts): a teacher saved details and saw the code and the
  coloured header; a student with no class saw only the join box and was refused at a guessed course address; the invite
  link joined them and the course appeared with its section and subject; the student's People page showed the teacher
  and "1 students are in this class"; after a reset the old link said the code does not match; the teacher's People
  page listed the student with Mute and Remove.

## Not checked, not built

- Phone-width layout of the new pages was not checked in a browser.
- Students are not told by email; an invite link or code is shared by the teacher. The colour is shown on the courses
  list and the course page only, not on the dashboard cards.
- A student's course code cannot be reset per student; muting is per course.
- Course cards on the dashboards do not show the colour yet.
