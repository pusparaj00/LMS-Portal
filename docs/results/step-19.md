# Step 19 results: content management (F-02, F-03, TR-D-03, TR-D-04)

All runs on 2026-10-16 on the dev stack, branch `step-19-content-management`.

## What was built

Submissions, the mastery ledger, assignments and stored explanations all point at problems and concepts, so nothing
students have used is ever deleted. It is archived instead, or the delete is refused with the reason.

| Thing | Action | Rule |
| --- | --- | --- |
| Course | rename; archive and restore | Archived: gone from other users' course lists and closed to new enrolment. Its teacher still sees it and can restore it. |
| Coding problem | edit everything (`GET /problems/{id}/source`, `PUT /problems/{id}`); archive and restore; mark reviewed | An edit goes through the same sandbox check as a new problem, refuses a title already used in the course, and resets "needs review". Past run results are unchanged. Multiple-choice items are still edited through the bank. |
| Concept | rename; delete only if unused | Renaming keeps every tag and all history. Delete is refused (409, naming the uses) while any of the 7 tables with a foreign key to concepts refers to it. A test checks that list against the live schema. |
| Course notes | delete | The document and its search chunks are removed. |
| Enrolment | student leaves (`DELETE /courses/{id}/enroll`); teacher removes (`DELETE /courses/{id}/students/{sid}`) | Work and history stay; the student drops out of the gradebook and the class view. |

**An archived problem is hidden from students** (the list, the page, and new submissions get 404). It is also never
chosen for placement, probes, worked examples or recommendations, and cannot be added to a new assignment. An
assignment that already had it keeps it, so grades do not change.

**Screens:**
- Course page (teacher): a Course settings panel (rename, archive, concepts) and Edit, Mark reviewed, Archive or
  Restore on each problem.
- Problem form: an edit mode, with a note on what an edit does.
- Notes: Delete. Class view: Remove. Students: Leave course.
- Every repeated button has a name that says what it acts on (for example "Archive Double"), so screen-reader users
  and tests can tell them apart.

This deviates from the plan in one place: the new endpoints went into the existing course, problem and notes routers
instead of a new `content.py`, because each belongs with the code it changes.

## Tests

`docker compose --profile test run --rm --build test`: **605 passed**, ruff clean. That is 20 new: 7 in
`backend/tests/test_content.py`, plus 13 access-matrix cases, one per new route.
- **Courses:** rename, archive (hidden, enrolment refused, still listed for its teacher), restore; others refused.
- **Problem edits:**
  - the source carries hidden tests;
  - a wrong reference solution is refused with the sandbox's reason;
  - a title clash gives 409;
  - after an edit, the hidden test stays hidden and an earlier passed submission still reads passed with 2 tests;
  - mark reviewed works, and another teacher gets 404.
- **Archived problems:**
  - hidden from students and refused for submission;
  - absent from placement items, probes, worked examples and the recommendation;
  - kept by the existing assignment and its edit, refused for a new one;
  - restored.
- **Concepts:** rename follows the tags; a name clash and an in-use delete are refused; an unused one is deleted. The
  guard list equals the schema's foreign keys.
- **Notes:** delete removes the chunks and is refused for another teacher.
- **Enrolment:** remove and leave keep the submission and drop the student from the gradebook.

## Browser run (Chromium, Playwright)

At 1366 x 768 and 390 x 844, as a throwaway teacher with two throwaway students:
1. Renamed the course. Deleted the unused concept. Deleting the used one showed "this concept is still used by
   problems; rename it instead". Renamed it to "for loops".
2. Edited the problem's statement, which was saved after the sandbox check. Marked it reviewed, and archived the other
   problem.
3. Deleted the notes. A student saw only the live problem, then left the course (the course offered "Enrol" again).
4. In the class view the teacher removed the other student.
5. Archived the course: the notice appeared and the course was not in the student's list. Then restored it.

No page errors, no 5xx responses, no horizontal overflow.
