# Step 26: audit after Steps 24 and 25

Run on 2026-10-16 and 2026-10-17, branch `step-26-audit`. Each suspected bug was first reproduced against the running
stack with throwaway `audit-a3*@eval.local` accounts, then fixed, then covered by a test that fails without the fix.

## Bugs found and fixed

| # | Requirement | What was wrong | Fix | Test |
| --- | --- | --- | --- | --- |
| 1 | F-02, F-03 | A student could still list, open and submit to the problems of an **archived course** by direct link, and a submission still updated mastery. Archived problems were closed, archived courses only dropped out of the course list. | `can_access_course` counts a student's enrolment only while the course is not archived. Restoring the course reopens everything; nothing the student did is removed. | `test_an_archived_course_is_closed_to_its_students_until_it_is_restored`: list 403, page 404, submission 404, mastery 403; after restore, 200 |
| 2 | F-52 | "What should I do next?" suggested a problem from an **archived course** when that was the student's first enrolment (live: "Try "Old course problem" next"). | The chat's course choice skips archived courses, for the open problem and for the fallback. | `test_recommend_skips_a_course_that_was_archived` |
| 3 | F-23 | The difficulty estimate (Step 25) used the **concept names sent by the browser**, not the course's own (live: the same concept gave −0.28 or −0.80 depending on the name sent). | The estimate uses the names looked up from the course, which the sandbox check already reads. | `test_the_estimate_uses_the_courses_concept_names_not_the_ones_the_client_sends` |

After the fixes the live reproduction gives "Try "New course problem" next" and −0.28 for both names.

## Checked, no change

- **The other enrolment queries.** Teacher views, erasure, breach reports and the course list rightly include archived
  courses. The chat's grades, deadlines and announcements already excluded them.
- **Frontend:** `tsc --noEmit` is clean and `npm run build` passes. **Backend:** `pip check` reports no broken
  requirements; `pip-audit` is not installed, so Python packages were not scanned for advisories.

## Found, not changed: your decision

- **Demoting a teacher who owns courses** (`PATCH /admin/users/{id}/role`) succeeds and leaves their courses with no
  teacher; only admins can manage them afterwards (live: the former owner gets 403 on the gradebook). Whether a demotion
  should be refused while the person owns courses, or allowed with a warning, is a product decision.
- **`npm audit`: 2 low-severity advisories in DOMPurify 3.4.15**, which the code editor `monaco-editor@0.57.0` bundles.
  The advisories are GHSA-p98j-92pf-mc4p and GHSA-6688-9rhm-gjv2, both in DOMPurify's `IN_PLACE` mode. npm's fix
  downgrades Monaco (breaking). An `overrides` pin to a fixed DOMPurify would change a dependency, so it waits for your
  approval.

## Tests

`docker compose --profile test run --rm --build test` (2026-10-17): **651 passed**, ruff clean. That is 3 new, one per
bug.
