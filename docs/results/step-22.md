# Step 22 results: the teacher's view of a student's work (F-61, F-34, TR-S-02, TR-S-05, TR-S-08)

All runs on 2026-10-16, branch `step-22-student-work`.

## Why this step, checked against the plan

Before building, the request was checked against the documents:
- The PRD's value table promises "Transparent mastery: student **and instructor** can see why a mastery value changed".
  Until now only the student could, so F-34 was half-built although the gap report counted it as done. That is
  corrected below.
- The PRD's privacy row says "student code and chat history visible only to the student and their instructors", so a
  teacher seeing submitted code is in scope.
- Showing the chat is allowed but not required, so it is left out, which is the more private reading.
- The PRD limits the instructor dashboard to a "basic class view", so this is a drill-down, not analytics.

## What was built

- **`GET /courses/{id}/students/{sid}`:** the student's mastery per concept, suspected misconceptions and the newest 100
  submissions in the course.
- **`GET /courses/{id}/students/{sid}/mastery/{concept}/history`:** the same ledger the student sees. The query now lives
  in one function used by both views.
- **`GET /courses/{id}/students/{sid}/submissions/{subid}`:**
  - the code as submitted, the status, counts, error type and failing categories;
  - each visible test's pass or fail, and how many hidden tests failed (their inputs are never sent);
  - whether an explanation was requested, the number of model attempts, verified or template, and served from the
    stored explanations or not;
  - the explanation text while it is still in the 24-hour cache.

  If the problem's tests were changed after the submission, per-test results are left out instead of being guessed.
  Each call writes `student_work.viewed` (teacher, student, submission) to the audit trail.
- **Access:** only the course's own teacher, and only for a student enrolled in that course. Other teachers, admins and
  students get 403; an unknown or removed student, or a submission that is not theirs, gets 404.
- **Privacy notice v3:** "Your instructor can see your mastery and why it changed, the code you submit with its test
  results, and whether you asked for an explanation. Your messages to the assistant are not shown to them." Every
  student is asked to agree again.
- **Screens:** student names in the class view link to a student page (mastery bars linking to the history,
  misconceptions, submissions), and each submission opens a read-only view with line numbers.

## Tests

`docker compose --profile test run --rm --build test`: **631 passed**, ruff clean. That is 10 new: 7 in
`backend/tests/test_student_work.py`, plus 3 access-matrix cases.
- **Overview:** submissions newest first with status and counts, and mastery.
- **Access:** another teacher, an admin, a classmate and anonymous are each refused; a student outside the course gives
  404; another student's submission cannot be read through this student's address.
- **Submission:** the code and per-test results; 2 hidden failures counted; the hidden input and expected outputs
  appear nowhere in the response; the audit row is written.
- **Explanation:** after the student asked (stub model), the record says requested, template, and the text matches what
  the student was shown.
- **Ledger:** the teacher's history equals the student's own; another course's concept gives 404.
- **Notice:** it says code is seen and messages are not.
- **Changed tests:** after the tests were changed, per-test results are absent and the stored counts remain.

## Browser run (Chromium, Playwright)

At 1366 x 768 and 390 x 844. A throwaway student agreed to notice v3, set the name "Ravi Kumar", submitted code passing
2 of 3 tests, and asked for an explanation; the dev stack's live model verified it in 1 attempt. The teacher then:
1. Clicked "Ravi Kumar" in the class view, and saw the submission "failed · 2/3".
2. Opened it: 5 numbered code lines, both visible tests passed, the note that a hidden test failed, and "A checked
   explanation was shown after 1 model attempt". The hidden input `987654` appeared nowhere on the page.
3. Opened "loops": "50% to 27%, Submission #4073 to 'Add one' failed tests in: large_input".

No page errors, no 5xx responses, no horizontal overflow.

## Not done

- The student's chat is not shown, by decision.
- The explanation text is only available while cached (24 hours); the verdict and attempts are kept permanently.
