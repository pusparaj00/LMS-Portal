# Step 15: second bug audit

Run on 2026-10-16 on branch `step-15-audit`. It covered the code added since the first audit (Step 11): the audit trail
(Step 12), the LTI launch (Step 13) and the gradebook (Step 14).

| # | Bug | How it was found | Fix | Proof |
| --- | --- | --- | --- | --- |
| G1 | In the gradebook, the columns were in due-date order but each row's cells were in assignment-id order, so an assignment created later with an earlier due date showed the other assignment's score under its heading | Live: columns B, A; cells A, B (1.0 under B) | Cells are sorted into the column order; the page also matches each cell to its column by id | Test in `test_gradebook.py`; live: cells B, A with 0.0, 1.0 |
| G2 | A student whose account was opened from the LMS could not ask for deletion (TR-S-07): the request needs the password, and such an account has a random one nobody knows | Code review | For an account linked to an LMS, an explicit confirmation replaces the password; the status says which is needed and the Privacy page shows a checkbox instead of a password field. A password account still needs its password | Test in `test_lti.py` |
| G3 | The LTI target check used a bare prefix, so `http://localhost:8080.evil.test/` passed as this tool | Code review | The target must be the tool's address itself or a path or query under it | 2 refusal cases added in `test_lti.py` |
| G4 | A refused LTI launch was recorded twice (`lti.launch_refused` and a generic `access.denied`), which would inflate a breach report | Code review | The middleware leaves 401 and 403 on `/auth/` and `/lti/` paths to those handlers' own events | Assertion in `test_lti.py` |
| G5 | `test_submissions_and_runs_are_limited...` failed at random in CI: limits use fixed one-minute windows and each graded request takes seconds, so a minute boundary between the requests reset the count | CI run 38868377376 (200 where 429 was expected); passed locally | The test pins the rate limiter's clock inside one window | 3 runs in a row pass; CI |

Suite: `docker compose --profile test run --rm --build test`, **561 passed**, ruff clean. The OpenAPI file was
regenerated for the new `confirm_with` and `confirm` fields.

## Seen but not changed

- Fixed windows let a client make up to twice the limit across a minute boundary. That is the documented design
  (TR-S-04, `app/ratelimit.py`), not changed here.
- Two first launches of the same new LMS user at the same moment would race, and one would fail with a 500. This is
  unlikely in practice; making it safe needs an upsert on the account and course together.
- Gradebook labels for LMS accounts are the placeholder (`lti-28-...`), because no name is taken from the LMS
  (TR-S-06). A teacher can't tell those students apart without the LMS's own list.
- The Privacy page's checkbox variant was checked by the type checker and through the API, not driven in a browser,
  because it needs an LMS session.
