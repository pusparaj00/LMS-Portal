# Step 70: small fixes (G-3, G-14, G-15)

Measured on 2026-10-25 in the test container (`docker compose -p lmssb --profile test run --rm ... test python -m
evaluation.thread_share --students 48 --delay 6`), against the test database.

## G-3: cheap requests waiting behind model-backed ones

The experiment starts the real app under uvicorn with a model that thinks for 6 seconds and then fails (so each
explanation holds a worker thread and database connections exactly as a slow provider does). 48 students ask for an
explanation at the same moment, and the course list (a cheap request) is timed every 250 ms throughout. Model calls at
once: 16 (unchanged).

| Setting | Explanations | Slowest explanation | Cheap request: median / 95th percentile / slowest |
| --- | --- | --- | --- |
| 40 threads, pools 30+10 (before) | 40 answered, 8 refused with 503 | 26.4 s | 9 ms / 85 ms / 13.9 s |
| 70 threads, pools 45+25 (after) | 48 answered | 14.4 s | 8 ms / 278 ms / 1.4 s |

An earlier run of the "before" setting gave a slowest cheap request of 26.1 s (status counts were not printed that time); the single
"after" run is the one shown. Cheap requests alone take 5 to 8 ms in both.

Changed: `server_threads` is now a setting (default 70, applied at start-up) and the two database pools are 45+25, so
each covers the threads. Postgres allows 200 connections: 70 + 70 here and about 15 for the mastery service and the
worker. Not changed: the cap of 16 model calls at once and the 3-second queue.

Limits: one experiment on one PC, one run per setting, a fake model, 48 students. Above about 70 simultaneous
model-backed requests the same starvation returns; a class that size needs a pool of its own for those routes.

## G-14: a coding problem without a hidden test

Saving a problem (form, import and draft) is now refused with "has no hidden test; add at least one so a student cannot
hard-code the visible examples". All 35 problems of the bank already had one (the bank still validates: 75 of 75). The
second half of G-14, reference solutions under 6 tokens that the leak guard does not compare, is accepted as a limit.

## G-15: past-due assignments

Saving an assignment whose due date has already passed is refused with a message naming `confirm_past_due`; the page
asks the teacher "every student will count as late at once. Save it anyway?" and sends the request again with
`confirm_past_due: true`. Editing an assignment without changing its stored date does not ask again.

## Tests

`pytest -q`: see the step report. New: `tests/test_small_fixes.py` (7), a worker-thread test and a pool-covers-threads
test in `tests/test_overload.py`. Existing tests that created past-due assignments or problems with no hidden test now
say so explicitly.
