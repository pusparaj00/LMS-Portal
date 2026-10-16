# Step 12 results: breach detection and procedure (TR-S-08)

All runs on 2026-10-16 on the dev stack, branch `step-12-breach-procedure`.

## What was built

- **Audit trail** (`audit_events`, migration 0010). Events: `auth.login`, `auth.login_failed`, `auth.register`,
  `access.denied` (401, 403), `rate_limited` (429), `access.not_found` (404 on submission, history and probe ids),
  `export.download`, `staff.created`, `consent.accepted`, `consent.withdrawn`, `erasure.scheduled`, `erasure.cancelled`,
  `erasure.completed`. Each has the time, user number, IP address, request id, status and a few labels (path, course,
  format). A failed login stores a keyed hash of the email (HMAC with the server secret), not the email. The API role has
  SELECT and INSERT only; `purge_audit_events(days)` is the one way to remove rows, used by the worker when
  `AUDIT_RETENTION_DAYS` is above 0 (default 0, keep). The trail outlives an erased account with only its number.
- **Request log** lines now carry the user number and IP, joined to the trail by request id.
- **`python -m app.breach_report --since ... [--until ...]`** lists password guessing by address and by account, logins
  from guessing addresses, accounts with many refused or not-found reads, exports, new staff accounts, erasures, and the
  student numbers possibly affected (owners of probed submissions, students in exported courses).
- **`docs/breach-procedure.md`**: roles (blank, to be filled), hour-by-hour timeline to 72 hours, evidence commands,
  containment steps tied to this system's secrets, notice contents for the regulator and for students. Marked as a draft
  awaiting the data protection contact.

## Tests

`docker compose --profile test run --rm --build test`: **520 passed**, ruff clean. `backend/tests/test_audit.py` (7 tests):
logins recorded without the password, email or its local part; refused requests carry user, address and request id; the
report flags a staged 12-attempt password burst and a student reading 12 of another student's submissions, and names the
victim as possibly affected (not the prober); an export is recorded and its course's students reported; consent, erasure
and staff events are recorded; the API role cannot UPDATE or DELETE events, and purge removes only rows past the limit;
a request still succeeds when the trail cannot be written.

## Live checks

- 391 audit rows before `docker compose up -d --force-recreate api worker`, 391 after.
- 11 failed logins through nginx (port 8080) were recorded with the client address; `app.breach_report` listed that
  address with 11 failures. On Docker Desktop every client on the host appears as the bridge address `172.18.0.1`; on a
  real host nginx passes the real address.
- The evidence commands in the procedure (container logs and `pg_dump`) were run into a temporary folder: the dump
  listed 26 tables of data with `pg_restore --list`. The copies were then deleted.

## Limits

- The test suite shares the app database (known), so test events (address `testclient`) appear in the dev trail.
- Container logs are still lost on a rebuild; the procedure copies them first, and the audit trail does not depend on them.
- The trail keeps IP addresses until `AUDIT_RETENTION_DAYS` is set; erasure does not remove them (TR-S-07 names
  submissions, chat and mastery). The data protection contact should set the period.
