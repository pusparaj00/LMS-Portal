# Step 57: audit after steps 54 to 56 (2026-10-19 and 20)

Branch `step-57-audit` (from `step-55-prerequisites`). Every check below was run; nothing is claimed that was not.

## What was checked and what it found

| Check | How | Result |
| --- | --- | --- |
| Service logs | `docker compose logs api mastery worker`, errors and tracebacks, last 48 h and again after the runs below | None (16,521 api log lines after the fuzz run, all access lines) |
| Mastery ledger invariant (TR-M-09) | Replayed every user's ledger and compared with the stored vector | 187 users, 3,657 events, 1,739 concept vectors, **0 mismatches**; no mastery row without an event; all values in 0 to 1 |
| 5xx under bad input | Every API path and method from the OpenAPI file, as student, instructor and admin, with junk in each body field (wrong types, empty, NUL, 5,000 characters, SQL-like text, huge integers), bad path ids (0, -1, 2147483647, text) and real ids of a throwaway course; about 9,000 requests; auth, erasure, consent withdrawal, password and admin user routes skipped | **0 responses of 500 or more** (272 successes, 2,631 validation rejections, 6,053 refusals by role) |
| Browser sweep | Every route as student and instructor (and admin pages) at 1280 and 390 px, 96 page visits, on a fresh course | No page error, no console error, no 5xx, no horizontal overflow, no "undefined", "NaN" or "[object Object]" text |
| Static scan | `ruff` with the bugbear, pylint-error, security, simplify and performance rule sets | 10 style findings, none a defect (the PDF reader is already sandboxed with resource limits and an empty environment) |
| Stuck or inconsistent data | SQL on the live database | 0 submissions without a result, 0 graded submissions without mastery evidence, 0 notes not ready, 0 chunks without an embedding, 0 concepts depending on themselves or on another course, 0 problems without concepts, 0 tracing questions without a correct option |
| Names removed in steps 54 to 56 | Searched the whole repository | None left. One stale call was found and fixed earlier in step 56 (`evaluation/load.py`) |
| Latency | 25 calls each | Student dashboard median 12 ms, course list 6 ms |

## Bugs found and fixed

1. **A question archived or put into an assignment while a student was taking the placement test caused a 500 on their
   next answer, and left them unable to continue** (`routers/diagnostic.py`, `diagnostic/selection.py`). Reproduced with a
   test first (500), then fixed: the vanished question is skipped, nothing is graded or recorded for it, and the student
   gets the next question; answers already given stay in the ledger. Test:
   `test_a_question_archived_during_the_test_does_not_break_it`.
2. **Two teachers editing prerequisites at the same moment could create a circle** (`routers/courses.py`): the cycle check
   read the graph without a lock. The concept rows are now locked while the edit is checked and written. (`next_step` already
   copes with a circle, so nothing could loop forever.)
3. **A placement answer to a question whose concepts had all been removed would have divided by zero in the pooled
   estimate** (`mastery/service.py`): such answers are skipped.
4. **Two of my own new tests were order- or chance-dependent** (they counted a prerequisite-propagation ledger row, and
   required three different first questions out of six random starts). Both now count what they mean to.

## Found and not changed

- 31 coding problems in old audit test courses have no hidden test. The bank importer requires one; the teacher's
  "add a problem" screen does not. Hidden tests protect against hard-coded answers, so this is a product decision, not a bug.
- The audit created `fuzz-*@eval.local` accounts and courses in the development database (throwaway, like the earlier
  probe accounts).
- Not covered by this audit: LTI launch and grade passback (needs a Moodle), real model output quality, concurrency beyond
  the earlier 10-student run, and a dependency vulnerability scan (`pip-audit` and `npm audit` need approval).
