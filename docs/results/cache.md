# Step 7 results: failure-signature cache and instructor review

Command: `docker compose exec -T api python -m evaluation.load cache 5` (after `python -m app.seed`), primary model
`gemini-3.5-flash-lite` on the original key (the Gemini Pro key was rejected by Google, see the provider notes in
`integration.md`). Six new students submit the same wrong code; the models are read back from `explanation_checks`.

## TR-V-11

Run 2026-10-15 17:12 UTC, problem `Factorial`, the same wrong code from each new student.

| Student | Seconds | Result | Stored explanation | Models in explanation_checks |
| --- | --- | --- | --- | --- |
| 1 | 10.80 | verified | no | gemini-3.5-flash-lite |
| 2 | 0.03 | verified | yes | cache |
| 3 | 0.02 | verified | yes | cache |
| 4 | 0.02 | verified | yes | cache |
| 5 | 0.04 | verified | yes | cache |
| 6 | 0.02 | verified | yes | cache |

Later students served from the cache in under 1 s with no model call: 5 of 5

The first student's explanation came from the model; the cache stored it. The next five got it back in 0.02 to
0.04 s and their `explanation_checks` rows name only `cache` (prompt `cache-v1`), so no model was called for them.
Six students on one problem is a small sample.

## What stops a wrong reuse (tests in `backend/tests/test_explanation_cache.py`)

- A stored explanation is shown only if the line it cites reads the same in the new code and the verifier passes it
  against the new submission's failed tests; otherwise the live flow runs (tested with the same failure moved to line 2).
- A rejected entry is never reused; a template fallback is never stored.
- An instructor edit is saved only if it passes the verifier against the submission the entry came from: edits with
  the reference solution, hidden test data or more than 400 characters are refused (422) and nothing changes.
- Only the course's instructor can approve or reject; admins and the instructor can list.

## Browser check (F-62)

Headless Chromium (Playwright 1.55) logged in as the demo instructor, opened the class page, edited the stored
Factorial explanation and saved it: the entry changed to "approved" with the new text. The same page was rendered at a
390 px width. Run 2026-10-15.
