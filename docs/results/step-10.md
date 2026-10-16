# Step 10 results: deletion and retention (TR-S-07)

All runs on 2026-10-16 on the dev stack (`docker compose`), branch `step-10-deletion-retention`.

## What was built

- A student asks for deletion with `POST /me/erasure` and their password. A request is stored with `due_at` at least 48 hours
  after `notified_at` (a database CHECK enforces it). `GET` shows it and `DELETE` cancels it. Only students can use it, and a
  student who withdrew consent still can.
- The worker checks every 60 seconds. For each request whose time has come, the mastery service deletes the student's
  `mastery`, `mastery_events` and `misconception_state` rows through the database function `erase_user_mastery`; then the API
  role deletes the cached explanations made from their submissions, checks, run results, submissions, chat, placement sessions,
  consents, enrolments and the user row, in one transaction. A failure leaves the request pending and it is tried again.
- No role has DELETE on the three mastery tables. Only `lms_mastery` can run the function, so the mastery service is still the
  only writer of mastery. The completed request stays as an audit row with the user number and dates only.
- `RETENTION_DAYS` (default 0, off) makes the worker request erasure for students with no submission, chat message or consent
  change for that many days. They get the same 48 hours.
- The privacy notice (now version `2026-10-v2`) says how long data is kept, how to delete it, and that backups are not changed.
  Everyone is asked to agree again. The Privacy page has a "Delete my data" section and every page shows a banner while a
  deletion is pending.

## Tests

`docker compose --profile test run --rm --build test`: **505 passed** (ruff clean). `backend/tests/test_erasure.py` has 9 tests:
password and 48-hour wait; cancelled request never runs; erasure leaves zero rows in every table with a `user_id` column (found
from the schema) and leaves another student's rows identical; withdrawn student can request; roles; failure then retry; retention
schedules but does not delete; no role can DELETE mastery directly and the API role cannot call the function; service token needed.

## Live run

A throwaway student on the running stack (`erase-…@eval.local`): the notice showed version 2026-10-v2 and mentioned 48 hours;
a wrong password gave 403; a request gave 201 with `due_at` exactly 48 hours later; a second request gave 409; cancelling worked
and a new request was accepted. I then moved the due time into the past in the database, and the worker erased the account within
10 seconds (its log shows "erasure completed"). Afterwards the student's chat and consent rows were 0, login gave 401, the old token
gave 401, and the audit row read `done`.

## Not verified

- The new screens (Privacy section, banner) were not driven in a browser: no browser tool is installed and I did not install one
  without approval. `tsc` passes and the frontend image builds.
- The notice is shown in the app only. A student who is erased for inactivity and never signs in sees nothing. Email would need an
  SMTP service you approve.
- Backups are outside the code's reach; see the README.
- The mastery service's log line for erased rows is not emitted (its logging is not configured); the worker's line is.
