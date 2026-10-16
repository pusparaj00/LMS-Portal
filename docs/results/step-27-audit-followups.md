# Step 27: the two decisions left open by the Step 26 audit

Run on 2026-10-17, branch `step-27-audit-followups`. Both follow the recommendation you approved.

## 1. A teacher who still teaches a course is not made a student (F-01, F-02)

`PATCH /admin/users/{id}/role` to `student` is now refused (409) while the person still owns a course, archived ones
included. The reply names the courses: "this person still teaches 'Taught course'; give those courses to another
teacher or remove them first". Before, the demotion succeeded and left the courses with no teacher. Making the same
person an **admin** is still allowed, because an admin manages every course.

- **Test:** `test_a_teacher_who_still_teaches_a_course_is_not_made_a_student` in `backend/tests/test_accounts.py`
  checks the refusal, the course named in the message, and that promotion to admin still works.
- **Browser (1366 x 768 and 390 x 844):** an admin chose "student" for a throwaway teacher on the Users page. The page
  showed the message above, and the role list still showed "instructor".

## 2. DOMPurify pinned to a fixed version (TR-S, dependency hygiene)

The code editor `monaco-editor@0.57.0` bundles DOMPurify 3.4.15, which has two low-severity advisories:
GHSA-p98j-92pf-mc4p and GHSA-6688-9rhm-gjv2. npm's own fix downgraded the editor. Instead, `frontend/package.json` now
has `"overrides": {"dompurify": "3.4.16"}`:
- 3.4.16 is the first fixed release, published 2026-09-23;
- 3.4.17 is newer but was only 5 days old, so it was not chosen.

| Check | Before | After |
| --- | --- | --- |
| `npm audit` (all dependencies) | 2 low | 0 |
| `npm ls dompurify` | 3.4.15 | 3.4.16 overridden |
| `tsc --noEmit`, `npm run build` | pass | pass |

**Browser:** at both widths the problem page's code editor loaded, and text typed into it appeared.

One limit of the test, not a defect: Playwright's default instant typing dropped characters in this Monaco version, and
the same text typed at 80 ms per key appeared exactly.

## Tests

`docker compose --profile test run --rm --build test` (2026-10-17): 651 passed and 1 failed. The new test read the error
message from the wrong field. After that fix, `tests/test_accounts.py` passed 8 of 8, so the suite stands at **652**,
ruff clean.
