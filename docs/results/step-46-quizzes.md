# Step 46: Quizzes (F-71, F-72, part of F-75)

Date: 2026-10-19. Branch `step-46-quizzes` (from `step-45-open-chat`). Migration 0025.

## What was built

- Tables `quizzes`, `quiz_questions`, `quiz_attempts`, `assignment_quizzes` (migration 0025). A quiz belongs to a course;
  an assignment can hold quizzes next to coding problems, each with points.
- `assignment_scores` (the one SQL function behind the gradebook, grades page, dashboards, assistant and LTI send) now
  also scores quizzes: points times the fraction of the best attempt, on time or late, by the same late rule as coding
  problems. Its signature and result columns are unchanged.
- `routers/quizzes.py`: instructor create, edit, delete; students list published quizzes, read questions, submit an
  attempt and read their own attempts. Grading is on the server and per question all-or-nothing: a choice question is
  right when the chosen set equals the right set; a short answer matches an accepted answer after trimming, collapsing
  spaces and ignoring case.
- Right answers reach a student only in the review of an attempt, when the instructor turned `show_answers` on and
  every assignment holding the quiz is past due. The questions of a quiz that has attempts are locked (409); title,
  attempt limit, review and publishing can still change. A quiz in an assignment or with attempts cannot be deleted.
- Screens: Quizzes (instructor authoring), quiz picker with points on the Assignments form, quiz list on the student
  course page, and the take-a-quiz page. Quiz attempts are removed by erasure (TR-S-07).

## Not built (by design, later steps)

File-upload assignments and manual grading (F-73, F-74) are Step 47; F-75 is complete only after that.
Time limits, partial credit and email notices are not part of this step.

## Evidence

- Existing scores unchanged: `assignment_scores` for every course in the dev database was dumped before and after
  migration 0025 (13 rows) and compared with `diff`: identical (md5 b8772f14… both times), 2026-10-19.
- Tests (`docker compose --profile test run --rm test`, 2026-10-19): 779 passed, ruff clean. 20 new quiz tests cover
  answer secrecy (student view has no `correct_choices` or `accepted`), all-or-nothing grading and weights, the
  attempt limit, review timing, question locking, delete rules, the role matrix, 10 malformed questions refused, and a
  hand-calculated gradebook (8 points x 1/4 = 2.0, x 4/4 = 8.0, late attempts show only in `with_late`). The access
  matrix, the table-count test and the erasure test were extended for the new routes and tables.
- Browser (Playwright, 1280x1000, throwaway `@eval.local` accounts): an instructor built a quiz with a single-choice
  and a short-answer question, put it in an assignment, and a student took it; the student page did not contain the
  accepted answer, the attempt scored 2 of 2 (answer `"  LEN "` matched `len`), and the assignment showed Complete 1 / 1.
- Backup before migrating: `backup/lms-2026-10-19-before-step46.dump` (git-ignored).

## Open issues and risks

- Dev database keeps throwaway accounts and courses from the browser checks (`quiz*-*@eval.local`, `Quiz UI *`).
- A student can retake until attempts run out; per-question right/wrong is hidden until review opens, so retakes cannot
  be used to read off answers question by question.
- Review is not available for a quiz that is not in an assignment until `show_answers` is on (then it is immediate).
