# Step 51: Grading structure (F-87, F-88, F-89)

Date: 2026-10-19. Branch `step-51-grading-structure` (from `step-50-course-page-scheduling`). Migration 0030.

## What was built

- **Grade categories and a weighted grade (F-87).** A course can define categories with weights (Homework 30, Exams 70);
  an assignment is filed in one. Each student's overall grade is the weighted mean of their category percentages
  (on-time score over the points of the assignments in the category that were given to them). A category with nothing
  given to the student yet is left out and the other weights are scaled up, so an empty category never pulls the grade
  down. Assignments with no category are not in the overall grade and the count is shown beside it. A course with no
  categories has no weighted grade; its points total stays the course score. The gradebook has an Overall column and a
  categories panel; a student's Grades page shows the overall grade with each category's score and weight.
- **Score overrides (F-89).** A teacher adjusts one student's score for one assignment from the gradebook with a reason.
  The override replaces the computed score (on time and with late alike) everywhere, because it lives in the one
  `assignment_scores` function; the score may not exceed the assignment's points and the assignment must have been given
  to the student. The reason is shown to the student on their Grades page and marked in the gradebook. Setting and
  removing an override are audited with numbers only (the score and what it was before, never the reason text).
- **Rubrics (F-88).** A course has reusable rubrics (criteria, each with levels worth points). A rubric is attached to
  an assignment's handed-in work and must have the same top score as the work (the form takes the points from it). The
  teacher grades by choosing one level per criterion; the score is their sum, and a plain score is refused for rubric
  work and levels for work without one. The student sees the rubric from the start and the chosen levels only once the
  work is returned. A rubric that has graded work is locked, one attached to an assignment cannot be deleted or have its
  top score changed.

## Evidence

- Scores unchanged: `assignment_scores` for every live course (21 rows) dumped before and after migration 0030 and
  compared: identical, 2026-10-19. Backup first: `backup/lms-2026-10-19-before-step51.dump`.
- Tests (`docker compose --profile test run --rm test`, 2026-10-19): 912 passed, ruff clean, `tsc --noEmit` clean. 18 new tests in `tests/test_grading_structure.py`
  cover category management and its refusals, a hand-calculated weighted grade (homework 8 of 10 = 80%, exam 30 of 50 =
  60%, weights 30 and 70, an empty category and an uncategorised assignment present: 66.0), no weighted grade without
  categories, deleting a category, late work staying out, overrides (replace, reason shown to the student, audit without
  the reason text, removal, every bound refused, role and not-given checks), rubric storage and refusals, grading by
  levels (sum, hidden until returned, plain score and incomplete or foreign levels refused), the points match and own-course
  checks, and rubric locking and deletion rules. The access matrix, table count, erasure seed and cleanup were extended.
- Browser (Playwright, 1280x1100, throwaway `@eval.local` accounts): a teacher graded an essay with the rubric (Strong 6 +
  Polished 4 shown live as 10 of 10) and returned it; the exam was scored 20, then adjusted to 30 in the gradebook with a
  reason; the gradebook showed the Overall column (72%) and the categories panel; the student's Grades page showed
  "Overall grade: 72%" with Homework 10 of 10 (100%) and Exams 30 of 50 (60%), (30 x 100 + 70 x 60) / 100 = 72, and
  "Adjusted by your instructor: Re-marked after appeal". No console or API errors.

## Not checked, not built

- Phone-width layout of the new panels and the rubric grading form was not checked in a browser.
- The CSV export and the LTI grade send use the points score and do not include the weighted grade or mark overrides
  (an override changes the exported score because it changes the stored one).
- The rubric page is a form per rubric; there is no drag-to-reorder, and levels are stored best first.
- Quizzes and coding problems cannot use a rubric; only handed-in work can.
