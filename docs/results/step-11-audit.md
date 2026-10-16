# Step 11: bug audit

Run on 2026-10-16 on the dev stack, branch `step-11-bug-audit`. The audit covered the backend routers, mastery service,
feedback and chat code, the erasure path and nginx. The frontend was walked in Chromium (Playwright 1.64.1) at
1366 x 768 and 390 x 844, as a student and as an instructor, using throwaway `@eval.local` accounts.

| # | Bug | How it was found | Fix | Proof |
| --- | --- | --- | --- | --- |
| B1 | `POST /problems` with a title already used in the course replaced that problem (statement, tests) and answered 201 with the old id | Live: two posts, same id, statement overwritten | 409; the bank import keeps its replace-on-reimport behaviour | Test in `test_concepts.py`; live: second post 409, first kept |
| B2 | Erasure (TR-S-07) left the student's Redis copies: chat history (24 h), stored explanations and probes per submission, hint counters, placement state | Code review | The erasure deletes those keys before the database rows | Test in `test_erasure.py` |
| B3 | A failure the sandbox labels `output_limit` or `memory_limit` had no slip and guess rates: the mastery service raised `KeyError`, reported it as 404 (`KeyError` is a `LookupError`), mastery did not change, and the 30-second backfill failed on it every time, which also blocked every later submission in its batch | Live: output-limit submission got 0 ledger rows; mastery log showed `KeyError: 'output_limit'` | Rates added (`output_limit` as `time_limit`, `memory_limit` as `runtime_error`); not-found uses its own exception; backfill applies each submission in a savepoint and skips one that fails | 4 parametrised tests, a backfill test; live: the stuck submission was backfilled (3 ledger rows), no backfill errors after the rebuild |
| B4 | The mastery service never configured logging, so its INFO lines (erasure counts, backfill) were dropped | Step 10 live run | `configure_logging()` at start-up | Service starts; suite passes |
| B5 | nginx gave up after its default 60 s while the API was still grading: a 7-test problem with a slow program returned an nginx 504 to the browser after 62 s, and the submission was stored at 71.5 s without the student seeing it | Live, through port 8080 | `proxy_read_timeout 660s` (50 tests x 12 s + 15 s) | Live: same request returned 200 after 73.6 s |
| F1 | A student who had withdrawn consent saw only the notice and could not reach "Delete my data", although the API allows it and the notice says deletion is available at any time | Browser walk | The delete section is shown on the notice screen too | Browser: after withdrawing, the button is shown and a request succeeds (both widths) |
| F2 | The "why did my mastery change" sentence ran together: "stopped with syntax error failed tests in: basic." | Browser walk | "stopped with a syntax error and failed tests in: basic." | Unit test |
| F3 | The chat progress reply named the same concept as both weakest and strongest when a course has few concepts | Browser walk | The two lists no longer overlap; "strongest" is left out when there is nothing to add | Assertion in `test_chat_api.py`; browser |
| F4 | Choosing another route for an earlier chat message sent the problem open now, not the one the question was asked on | Code review | The entry's own problem is sent | `tsc` |

Suite: `docker compose --profile test run --rm --build test`, **513 passed**, ruff clean.

## Seen but not changed

- An instructor's course list shows every course with an Open link; another instructor's course then answers 403. This
  matches the API (the list is public) and was left as it is.
- One live explanation named a test by its database id ("causing test 20937 to fail"). The id is not secret, but it means
  nothing to the student. Changing the prompt affects the verified flow, so it is left for a separate decision.
- The floating "Ask the assistant" button touches the Submit button's edge by about 1 px at 390 px width; both stay
  clickable.
- Playwright typing without a delay dropped characters in the code editor at 390 px; with a 60 ms delay the code was
  typed exactly, so this is a test artefact, not an app fault.
