# Step 52: Instructor insight (F-90, F-91, F-92)

Date: 2026-10-19. Branch `step-52-instructor-insight` (from `step-51-grading-structure`). No migration: everything is read
from data the system already holds.

## What was built

- **At-risk alerts with reasons (F-90).** `GET /courses/{id}/at-risk` and an Insight page list the students with at least
  one warning sign, most signs first, each sign with the facts that raised it. The signs and their thresholds are plain
  constants returned with the report and shown on the page ("What counts as a sign"):
  - missing work: 2 or more assignments past due with nothing handed in (the assignments are listed);
  - low scores: under 50% of the points on at least 2 past-due assignments (each score is listed);
  - falling scores: the latest 2 assignments 20 or more points below the earlier ones, with at least 4 assignments;
  - low mastery: average under 40% over at least 3 concepts that have evidence (the weakest 3 are listed);
  - inactive: nothing run, answered, handed in or completed for 14 days, once a student has been in the class a week.
  Assignments not given to a student never count against them. An alert is a prompt to look, not a judgement.
- **Quiz question analysis (F-91).** `GET /courses/{id}/quizzes/{quiz_id}/report`: for each question, how many students
  answered, how many were right, the percentage, and for choice questions how many chose each option. Each student's latest
  attempt is used (the number of attempts is shown too). A question answered by at least 3 students and got right by under
  50% is marked "most of the class missed this".
- **Content report (F-92).** `GET /courses/{id}/content-report`: for each lesson item, how many students finished it, and the
  average score and average mastery of those who did and did not. A difference is shown only when both groups have at least
  3 students; otherwise the page says "not enough students". The page states that this is an association, not proof that the
  lesson caused the difference.
- All three are read-only and limited to a course's own teachers and admins.

## Evidence

- Tests (`docker compose --profile test run --rm test`, 2026-10-19): 924 passed, ruff clean, `tsc --noEmit` clean. 9 new tests in
  `tests/test_insight.py` cover each sign with exact numbers (3 missing assignments listed by name; 20.0% on three
  assignments; scores 100, 100, 30, 30 giving "70 points lower"; mastery needing three concepts before it counts; inactivity
  needing a week's enrolment and two weeks without activity, with a lesson completion counting as activity), ordering
  by number of signs, access for other teachers, students, admins and anonymous callers, a quiz report checked against a
  hand count (5 attempts, 4 students, average 41.7%, option counts 2/2/0 and 2/1/2, the latest attempt replacing an earlier
  one, a 25% question flagged and a 50% one not), a quiz nobody took, and a content comparison with 3 finishers (average
  80%) against 3 others (average 40%): +40, with the one-finisher lesson refused a difference.
- Browser (Playwright, 1280x1300, throwaway `@eval.local` accounts): in a class of four, where one student had full marks
  and three had handed in nothing, the page said "3 of 4 students have at least one warning sign", showed the three flagged
  rows with "Missing work" and "Low scores", and opening "Why" listed "Past one" and "Past two" and "0 of 10" each; the quiz
  section showed "4 students took it", "1 of 4 right (25%)" for both questions and "most of the class missed this".
  No console or API errors.

## Not checked, not built

- Phone-width layout was not checked in a browser.
- The thresholds are not editable by an instructor; they are constants in `app/insight.py`.
- The content report uses completion as recorded by students ticking items, and scores and mastery as they stand now; it
  does not control for how active a student is, which is why it is labelled as an association.
- No alert is sent to anyone: the list is read on the Insight page (in-app notifications of alerts are not built).
