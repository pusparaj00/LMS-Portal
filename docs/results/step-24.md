# Step 24 results: a per-problem leak policy (F-62, TR-L-06)

All runs on 2026-10-16, branch `step-24-leak-policy`.

## Why, and one conflict settled

F-62 was partly built: per-problem hint limits and approval of stored explanations worked, but the leak guard's
threshold was global, not per problem. The DRD lists `PUT /problems/{id}/policy` to set "the maximum hint level and
leak policy".

The PRD says the system "never gives a full solution unless the instructor allows it". The project's non-negotiable rule
in CLAUDE.md says replies never contain a full solution. Those disagree, and the project rule wins: a problem's policy can
only make the guard **stricter** than the threshold tuned on the question bank (0.7, TR-L-06), never looser. No way to
allow full solutions was built.

## What was built

- `problems.leak_threshold` (migration 0018), empty for the tuned default. A database check limits it to 0.3–0.7.
- The guard takes the problem's threshold everywhere it compares a reply with the solution:
  - the verifier, for new explanations, the stored-explanation cache and the demo cache;
  - the worked-example hint, which must not resemble this problem's solution more than the threshold allows.

  `leak.check` caps any threshold at 0.7, so even a wrong caller cannot loosen it. The absolute rules (no fenced code,
  at most 3 code lines, short inline snippets) are unchanged at every level.
- `GET` and `PUT /problems/{id}/policy` (the course's teacher) read and set the hint limit and the leak level. The `PUT`
  used to return the problem as it was before the change and without the hint limit; it now returns the saved policy.
- **"Help for this problem"** panel on the problem page for teachers: hints (1 to 3) and three levels, Standard (0.7),
  Strict (0.5) and Very strict (0.3), with the note that a full solution is never shown at any level.

## What the levels cost, measured

`python -m evaluation.leak_threshold` (question bank, 2026-10-16):

| Threshold | Solution code let through | Ordinary text blocked | Other problems' code blocked |
| --- | --- | --- | --- |
| 0.3 (Very strict) | 0 of 120 | 0 of 137 | 661 of 2890 |
| 0.5 (Strict) | 0 of 120 | 0 of 137 | 216 of 2890 |
| 0.7 (Standard) | 0 of 120 | 0 of 137 | 61 of 2890 |

Stricter levels never block ordinary explanations in this set. They block more short code that merely resembles the
solution, which is what worked examples and quoted expressions consist of.

## Tests

`docker compose --profile test run --rm --build test`: **645 passed**, ruff clean. That is 6 new: 5 in
`backend/tests/test_leak_policy.py`, plus 1 access-matrix case.
- **Stricter blocks more:** a fragment measured at 0.636 similar passes at 0.7 and is blocked at 0.5 and 0.3.
- **Never looser:** a fragment at 0.727 stays blocked when 0.9 is asked for, and fenced code stays blocked.
- **The endpoint:**
  - the default reads as 0.7 effective;
  - Strict and 2 hints are saved and returned;
  - 0.8 and 0.2 are refused;
  - another teacher gets 404 and a student 403;
  - a reset returns to 0.7.
- **End to end:** an explanation quoting about 53% of the solution is verified on a Standard problem and falls back to
  a template on a Strict one.

## Browser run (Chromium, Playwright)

At 1366 x 768 and 390 x 844, a throwaway teacher set "2 hints" and "Strict" on a problem; after a reload both were kept.
A student opening the same problem saw no help panel, and the policy endpoint answered 403 for them. No page errors,
no 5xx responses, no horizontal overflow.
