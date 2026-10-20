# Step 65: audit after step 64 (2026-10-20)

Branch `step-65-audit` (from `step-64-student-notes`). Every check below was run; nothing is claimed that was not.

## What was checked and what it found

| Check | How | Result |
| --- | --- | --- |
| 5xx under bad input | Every API operation (147), as student, instructor, admin and anonymous, 8 id values and 16 kinds of junk in bodies and queries, 4,800 calls against a throwaway stack | **5 server errors** (admin on five course routes) and **lost audit events**; both fixed below. After the fixes: 4,800 calls, 0 server errors, 0 slow answers, 0 "audit event not written" and 0 "unhandled error" lines in the API log |
| Browser sweep | Every route as student (17), instructor (21) and admin (4), at 1280 and 390 px, with page errors, console errors, 5xx answers, horizontal overflow and "undefined", "NaN" or "[object" in the text | No page error, no console error, no 5xx, no overflow, no bad text, including the new notes pages |
| Static checks | `ruff check`, `tsc --noEmit` (through the front end build) | Clean |
| Full test suite | `docker compose --profile test run --rm test`, 2026-10-20 | 1,091 passed, ruff clean |

## Bugs found and fixed

1. **An id past the 32-bit range gave a 500 for admins** (`GET /courses/99999999999/gradebook`, `/at-risk`, `/content-report`, `/export/gradebook`, `/quizzes/{id}`). Admins skip the course-membership lookup, so the id reached the database, which raised "function assignment_scores(bigint, integer) does not exist". The middleware now answers 404 "not found" for any path segment that is a number above 2,147,483,647 (every id in the API is a 32-bit integer), and a handler turns a database "value out of range" or "cannot be stored" error into 404 or 422 instead of 500 (`main.py`, `errors.py`). Test: `test_an_id_past_the_integer_range_is_not_found_not_a_server_error`.
2. **A refused request whose path held a NUL character was not audited.** The access-denied event failed to insert ("\u0000 cannot be converted to text") and the log showed "audit event not written", so probing with such paths left no trace (`audit.py`). NULs are now removed from the event detail. Test: `test_a_refused_request_with_a_nul_in_its_path_is_still_audited`.
3. **An unknown address showed the course list** (for a signed-in user, `#/no-such-page`, or a student opening an instructor-only address such as `#/course/1/notes`). It now shows "Page not found" with a link to the courses (`App.tsx`). Found in step 62 and left open; checked in the sweep above.
4. **The top bar took two rows on a phone and stayed fixed to the top**, covering about 106 px of 800 px. On phones it now scrolls away with the page (`styles.css`). Found in step 62 and left open. The bar still takes two rows; only the fixed position changed.

## Found and not changed

- A past due date is still accepted without a warning (G-15), and a problem can still be saved with no hidden test (G-14). Both need a decision from the owner.
- A fuzz run on a stack changes demo passwords (the admin reset-password route is called with junk ids), so the throwaway stack has to be reset after it.
- Not covered: the model-backed routes with a real provider, a screen reader, Firefox and Safari.
