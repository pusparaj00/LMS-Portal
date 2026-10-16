# Step 16 results: grade passback to the LMS (LTI Assignment and Grade Services)

All runs on 2026-10-16, branch `step-16-grade-passback`. This extends TR-A-09 and F-70 with F-04's scores. The TRD has
no line for grade passback.

## What was built

- **Tool key:** `python -m app.manage lti-tool-key` prints a new RSA key as one `.env` line (`LTI_TOOL_PRIVATE_KEY`,
  base64 PEM). Only the api service receives it. `GET /api/v1/lti/jwks` publishes the public half only.
- **At launch,** the grade-service endpoint the LMS offers (line items URL and scopes) is stored per LMS course
  (migration 0013). It is refreshed at each teacher launch, so turning grade sync off in the LMS shows here too.
- **`POST /api/v1/courses/{id}/gradebook/send`** (the course's teacher), behind a "Send grades to the LMS" button that
  appears only when the course can send:
  1. Get an access token with a signed client assertion.
  2. Create one LMS grade column per assignment, then reuse it. If the points change, its maximum is updated.
  3. Post each LMS student's on-time score with an activity progress.
  - Students without an LMS account are counted and skipped.
  - Each failed score is listed, and every send or refusal is audited (`lti.grades_sent`, `lti.grades_refused`).
- **Safety:** every service URL must be on the token URL's own address, so a launch cannot point the server anywhere
  else (the test uses `169.254.169.254`). The token and LMS timeouts use `LTI_KEYS_TIMEOUT_S`.
- **Registration:** `lti-add-platform --token-url` adds the LMS's token endpoint.

## Tests

`docker compose --profile test run --rm --build test`: **569 passed**, ruff clean. `backend/tests/test_lti_grades.py`
has 6 tests against a fake LMS that verifies the tool's signed token request and records columns and scores:
- **Publication:** only the public key is published.
- **Scores:** the right scores are sent (1.5 of 2 for 3 of 4 tests, 0 for no attempt), with the right progress, to the
  column's `/scores` path with its query kept. A second send reuses the column, and a points change updates its maximum.
- **Failures:** a failed score is listed and the audit row counts it.
- **Local accounts:** students without an LMS account are counted, not sent.
- **Refusals:** each has a reason and an audit row: no tool key (503), no grade service offered (409), a service on
  another address (409, never called), a course not from an LMS (409).
- **Access:** only the course's teacher can send.

## Live run on Moodle 5.3

The same local Moodle as Step 13. `backend/evaluation/lti_moodle_grades.php` turned on accept grades, grade sync with
column management, and the tool's key set URL. Then, with Playwright:
1. The teacher launched from Moodle and created "Add one" and a 2-point "Week LTI" assignment.
2. The student launched and submitted a correct program (2 of 2 tests).
3. The teacher clicked **Send grades to the LMS**: "Sent 1 score for 1 assignment".
4. Moodle's grader report for the course showed a **Week LTI** column with **Student1: 2.00** and a course total of
   2.00. The audit row was `lti.grades_sent {"assignments": 1, "scores_sent": 1, "failures": 0}`.

The first send failed with "the LMS refused the token request (HTTP 404)", refused cleanly and audited. Moodle's page
showed why: its outbound-request protection blocks `localhost` and private addresses, so it could not fetch the tool's
key set. Only for this test Moodle, its `config.php` sets an empty `curlsecurityblockedhosts`. On a real deployment the
tool has a public address and nothing needs changing.

Test-only plumbing, removed afterwards:
- Two `alpine/socat:1.8.0.3` port forwarders let each container reach the other as `localhost`, because the Windows
  hosts file does not resolve `host.docker.internal`.
- `LTI_KEYS_TIMEOUT_S=30` was set for this slow Moodle.

Free memory was 0.42 to 0.44 GB during the run. Moodle is stopped again.

## Not done

- Grades are sent when the teacher clicks, not automatically.
- LMS columns are never deleted; deleting an assignment here leaves its column in the LMS.
- Canvas is not tested.
