# Step 47: Handed-in work and manual grading (F-73, F-74, F-75, F-76, F-77)

Date: 2026-10-19. Branch `step-47-submissions-grading` (from `step-46-audit`). Migration 0026.

## What was built

- **Assignment work (F-73).** An assignment can ask for handed-in work: instructions, points, and which of a file, a
  link or text it accepts. It can stand alone or sit beside problems and quizzes. Tables `assignment_work`,
  `work_submissions` (one row per student per assignment: draft or turned in, text, link, one file, score, feedback,
  graded and returned times) and `work_comments` (migration 0026).
- **Student side.** Save a draft, turn in, unsubmit until the instructor has graded it, replace or remove the file,
  download their own file. States shown: Assigned, Missing (past due, nothing turned in), Turned in, Returned. Work
  turned in after the due time is marked late.
- **Files.** PDF, text, Python or zip, at most 4.5 MB, checked by content (`%PDF-` header, zip header, readable UTF-8
  without NUL bytes), file name reduced to a safe last segment. Stored in the database and only ever served as an
  attachment with `application/octet-stream` and `nosniff`. Nothing is opened, unpacked or run.
- **Instructor side (F-74).** One review page: students with their state on the left, the chosen student's work, a score
  box (at most the assignment's points), feedback, Save score, Return, and Return all. A score and its feedback are
  hidden from the student until the return; a regrade after the return shows at once.
- **Gradebook (F-75).** `assignment_scores` counts a returned score (points times score over points) by the same late
  rule as problems and quizzes: on time counts, late shows only in `with_late`. A saved score that is not yet returned
  counts as zero for the student and in the gradebook.
- **To-review queue (F-76).** `GET /instructor/to-review` and a To review page with To review and Reviewed tabs, for the
  instructor's own live courses only.
- **Private comments (F-77).** A thread per piece of work between the student and the course's instructor.
- **Audit.** `work.viewed`, `work.file_downloaded`, `work.graded`, `work.returned` and `work.returned_all` are written
  with numbers only (no work text or feedback).
- **Guards.** An assignment that students have worked on cannot be deleted; work they handed in cannot be removed; the
  work's points cannot drop below a score already given.
- **Erasure.** A student's work and comments are removed with their account (TR-S-07).
- **Privacy notice.** Version `2026-10-v5` names the work, quiz answers and private comments and says the instructor, and
  no other student, can see them. Every student is asked to agree again.

## Evidence

- Existing scores unchanged: `assignment_scores` for every course in the dev database (15 rows) dumped before and after
  migration 0026 and compared: identical, 2026-10-19. Backup first: `backup/lms-2026-10-19-before-step47.dump`.
- Tests (`docker compose --profile test run --rm test`, 2026-10-19): 818 passed with the OpenAPI file frozen, ruff clean,
  `tsc --noEmit` clean. 22 new tests in `tests/test_work.py` cover the draft, turn-in and unsubmit rules, missing and
  late states, the kinds an assignment accepts, 7 rejected files and a bad base64 body, file name cleaning and
  download headers, score hiding until return, grading rules, a gradebook with a returned, an unreturned and a late
  hand-in, role and course isolation, the audit trail without text, private comments, the queue counts and Return all,
  and the delete and shrink guards. The access matrix, the table count and the erasure seed were extended.
- Browser (Playwright, 1280x1000, throwaway `@eval.local` accounts): a teacher created an assignment with handed-in
  work; a student saved text and a `.py` file and turned in; the queue showed "1 turned in"; the teacher scored 7 of 10
  with feedback and returned it; the student then saw "Your score: 7 of 10" with the feedback and the grades page showed
  the score. No console or API errors.

## Not checked, not built

- The new pages were not checked at phone width in a browser (a narrow-screen rule is in the stylesheet).
- A teacher is not told when work arrives and a student is not told when work is returned: in-app notifications are
  Step 48. Muting a student's comments is Step 49.
- Rubrics and score overrides are Steps 51. A returned score cannot be changed back to hidden.

## Open issues

- Every student, including the demo student, is asked to accept the new privacy notice on their next login.
- The dev database keeps throwaway `quizt-*`, `worksw-*` and similar `@eval.local` accounts and their courses.
