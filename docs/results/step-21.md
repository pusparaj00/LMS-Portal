# Step 21 results: a separate test database (TR-A-01, TR-V-10)

All runs on 2026-10-16 on the dev stack, branch `step-21-test-database`.

## The problem

The 621 tests ran against the app's own database. Each run wiped the synthetic demo class, and every run left accounts
and courses behind: before this step the app database held 431 users, among them 260 `@order.test` students created by
test runs and 53 groups of audit accounts.

## What was built

- **`lms_test`**, a second database on the same Postgres server (no new container). `tests/prepare_db.py` creates it if
  it is missing and brings it up to date; `--reset` drops it and starts again. It refuses to touch any database not
  named `lms_test`.
- **Test-only services** (compose profile `test`, started by `run test`, never by `up`): `testdb` (runs the script),
  `mastery-test` and `worker-test`. Without them a test's mastery updates and note embedding would still land in the app's
  database, because tests reach those services over the network. The test service no longer depends on the running
  API, and uses the stub model as before. The sandbox stays shared; it keeps no data.
- **Redis database 1** for tests; the app uses database 0.
- **A guard in `tests/conftest.py`:** the whole run stops before any test if any database URL names something other
  than `lms_test`, or Redis is not database 1.
- **Roles:** the database roles belong to the server, not to one database, so migrations 0001 and 0005 now create a
  role only if it does not exist. Databases that already ran them are unaffected.
- A test helper that leaked a fake LTI platform per student now cleans up (66 had piled up in the app database).

## Proof

Measured with row counts of all 33 tables in the app database and the list of Redis database 0 keys, taken before the
first test run:
- After a full run (621 passed): **every table's row count is identical**, no new key in Redis database 0, and the 20
  synthetic students are still there. The test database held its own 10 users and Redis database 1 its own 200 keys.
- After a second and a third full run, the third straight after rebuilding the test database from nothing (33 tables, all
  migrations): **identical again**. The first and third runs passed all 621.

## A defect found on the way

The second run, straight after `--reset`, failed 35 tests, where the first from-scratch run had passed all 621. A new
database restarts its ids at 1, but Redis database 1 still held the old database's cached explanations and probe offers,
keyed by the reused submission ids, and a probe for a different problem was returned. `prepare_db` now clears the tests'
Redis database whenever it creates the database, and the run straight after a reset passes. The same effect would affect
the app if its database were restored from a backup while Redis kept old keys, so the README's restore steps now flush
Redis database 0 after loading the dump (not run, since no restore was needed).

## Not done: removing the old test data from the app database

A one-off cleanup of the app database was prepared and then blocked: Claude Code's permission check refused the mass
delete, and I did not work around it. What exists:
- a full backup, `backup/lms-2026-10-16-before-cleanup.dump` (33 tables, restore-listed, git-ignored);
- `backup/cleanup-2026-10-16.sql`, which removes only my 16 Oct `audit-*@eval.local` accounts, the test suite's old
  accounts (`@order.test`, `@test.local`, `@t.*`), the Moodle test (`@lti.local`, its course and platform) and 66 leaked
  platforms, with their courses and data. It stops itself if any protected data would change. A first dry run
  rolled back and listed 332 users, 21 courses, 19 problems, 16 submissions and 1 document, and it halted on the
  `@gmail.com` student's enrolment in three test courses. The check was then relaxed to allow losing only that
  enrolment, but that corrected version has not been run.
- It keeps the demo accounts, the dev instructor, the `@gmail.com` student, the 20 synthetic students, the four earlier
  `@synthetic.local` evaluation accounts, courses 19 and 409, and everything from the 15 Oct evaluation runs
  (`load-`, `g3-`, `cache-`, `ui-`, `restart-` and similar accounts), because the measured results depend on it.

Until it is run, the app database still holds those leftovers, and a student's course list still shows the test courses.
