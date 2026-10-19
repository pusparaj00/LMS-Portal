# Step 50: Course page structure and scheduling (F-84, F-85, F-86)

Date: 2026-10-19. Branch `step-50-course-page-scheduling` (from `step-49-class-access-people`). Migration 0029.

## What was built

- **Stream, Classwork and People tabs (F-84).** Every course page now shows the three tabs. Stream holds the class
  settings (teachers), an Upcoming box (students: the next three things due and how many are missing), announcements,
  the student's progress panel and the course rating. Classwork holds assignments grouped by topic, quizzes, lessons and
  the problem list, with shortcuts to the lesson, assignment, quiz and notes editors for teachers. People is the page
  from step 49. A topic is a course module: an assignment is filed under one (`assignments.module_id`), and a student
  sees the topic's name only while that module is published, otherwise the work appears under "Other work".
- **Draft and scheduled announcements (F-85).** A teacher posts now, saves a draft (teachers only) or schedules a post
  for a later time. A student sees an announcement only once it is visible; posts are ordered by the time they became
  visible. Students are notified once, when the post becomes visible: whoever asks first after that moment (the bell, the
  announcement list, the teacher) triggers it, and the update hands each post to exactly one caller, so there is no
  duplicate and no background job. Editing a draft into a post publishes it.
- **Given to chosen students (F-86).** An assignment is given to the whole class or to chosen students
  (`assignment_students`). `assignment_scores` skips an assignment for a student it was not given to; the to-do list,
  calendar, due-soon notices, assignment list, hand-in page and the teacher's work list follow. A student is never told
  who else was chosen. In the gradebook a student without the assignment has no cell ("not given") and their total is
  shown "of" only the points they were given; the CSV export and the LTI grade send skip them.
- **Teacher dashboard.** The count of students who could finish an upcoming assignment counts only those it was given to.

## Evidence

- Scores unchanged: `assignment_scores` for every live course (20 rows) dumped before and after migration 0029 and compared:
  identical, 2026-10-19. Backup first: `backup/lms-2026-10-19-before-step50.dump`.
- Tests (`docker compose --profile test run --rm test`, 2026-10-19): 884 passed, ruff clean, `tsc --noEmit` clean. 18 new tests in `tests/test_course_page.py` cover drafts hidden from students and notifying
  nobody, publishing a draft once however often anyone looks, a scheduled post hidden until its time and then announced
  once to every student, ordering by visible time, six bad publishing choices refused, students unable to post or see other
  states, an assignment invisible to the students it was not given to (list, to-do, calendar, hand-in page, teacher's
  work list), no leak of who was chosen, gradebook cells and per-student totals, the score function returning no row for
  an unchosen student, the CSV export not crashing, changing who an assignment is given to, only students of the course
  being choosable, topics (own course only, cleared when the module is deleted) and the instructor dashboard count.
- Browser (Playwright, 1280x1000, throwaway `@eval.local` accounts): a teacher posted one announcement, saved a draft and
  scheduled one (shown with "draft" and "scheduled" labels), then created an assignment under the topic "Loops" for one
  chosen student; both students saw only "Visible now" on the Stream and the tabs Stream, Classwork, People; the chosen
  student saw the assignment on Classwork and the other student saw none. No console or API errors.

## Not checked, not built

- Phone-width layout of the tabs and the new forms was not checked in a browser.
- Lessons and assignments share a topic name but are listed in two lists on Classwork (lessons first by module, then
  assignments by topic), not interleaved in one list.
- "Reuse a post" from the Classroom file is not built; a scheduled post that nobody opens is announced the next time
  anyone in the course looks.
- Quizzes are not given to chosen students on their own: a quiz inside an assignment is scored only for the students
  the assignment was given to, but the quiz itself stays open to the whole class.
