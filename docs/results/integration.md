# Step 6 results (gate G5)

Run on 2026-10-15 against the local Docker Compose stack (Docker Desktop, WSL2) after `python -m app.seed`. Primary model
`gemini-3.5-flash-lite`, fallback chain `groq,openrouter,mistral,deepseek,openai`. Every table is pasted from command
output. Commands are run from the repository root as `docker compose exec -T api python -m <module> ...`.

## Ten consecutive demo runs (TR-V-10, TR-P-06)

`evaluation.load runs 10`. Each run is the PRD demo script as API calls with a new student: register, enrol, placement
test, dashboard, wrong submission, explanation (the scripted demo submission, so the prepared explanation is used and
re-verified), hint, probe answer, chat hint, chat progress, instructor heatmap (which must show this student and the
synthetic class).

Run 2026-10-15 15:46 UTC

Flows: 10, steps: 210, failed steps: 0, flows with no failed step: 10 of 10

| Step | Count | Median s | 95th percentile s | Max s |
| --- | --- | --- | --- | --- |
| register | 10 | 0.29 | 0.57 | 0.57 |
| enroll | 10 | 0.01 | 0.13 | 0.13 |
| placement start | 10 | 0.02 | 0.40 | 0.40 |
| placement answer | 100 | 0.05 | 0.35 | 1.56 |
| dashboard | 10 | 0.01 | 0.04 | 0.04 |
| submit wrong code | 10 | 0.26 | 0.34 | 0.34 |
| explanation (cached demo) | 10 | 0.03 | 0.31 | 0.31 |
| hint | 10 | 0.03 | 6.53 | 6.53 |
| probe answer | 10 | 0.19 | 2.72 | 2.72 |
| chat: hint | 10 | 2.08 | 7.23 | 7.23 |
| chat: progress | 10 | 2.19 | 11.00 | 11.00 |
| instructor heatmap | 10 | 0.03 | 0.08 | 0.08 |

An earlier attempt the same day failed 6 of 138 steps ("unknown user" or "no access" right after register or enrol).
Cause: the database commit ran after the response was sent, so a fast client could act before its row existed (and a
failed commit would have followed a success reply). Fixed by committing before the response (commit `TR-A-01`,
regression test `tests/test_commit_order.py`, which fails without the fix); the table above is the run after the fix.

## Ten concurrent students (TR-V-10, TR-P-04)

`evaluation.load concurrent 10`: ten students run the whole flow at the same time; each explanation is for a new
failure, so all ten go to the live model.

Run 2026-10-15 15:47 UTC

Flows: 10, steps: 210, failed steps: 0, flows with no failed step: 10 of 10

| Step | Count | Median s | 95th percentile s | Max s |
| --- | --- | --- | --- | --- |
| register | 10 | 1.12 | 1.22 | 1.22 |
| enroll | 10 | 0.04 | 0.14 | 0.14 |
| placement start | 10 | 0.12 | 0.20 | 0.20 |
| placement answer | 100 | 0.43 | 1.46 | 1.61 |
| dashboard | 10 | 0.01 | 0.03 | 0.03 |
| submit wrong code | 10 | 2.28 | 2.77 | 2.77 |
| explanation (live, uncached) | 10 | 4.90 | 7.36 | 7.36 |
| hint | 10 | 0.03 | 0.06 | 0.06 |
| probe answer | 10 | 0.29 | 0.55 | 0.55 |
| chat: hint | 10 | 1.13 | 2.68 | 2.68 |
| chat: progress | 10 | 1.12 | 4.42 | 4.42 |
| instructor heatmap | 10 | 0.03 | 0.06 | 0.06 |

Wall time for all 10 students together: 19.9s

## Restart test (TR-V-10, TR-P-07)

`evaluation.load prepare` leaves a placement test half done (4 of the items answered); then the services are restarted;
then `evaluation.load verify` continues the same session with the token issued before the restart.

| Restart | Old token still valid | Session continued and finished | Run (UTC) |
| --- | --- | --- | --- |
| `docker compose restart api redis` (21 s until healthy) | yes | yes, after 10 items, mastery for 12 concepts | 2026-10-15 15:47 |
| `docker compose restart` (every service, database included) | yes | yes, after 10 items, mastery for 12 concepts | 2026-10-15 15:48 |

## Timings (TR-P-01 to TR-P-03)

`evaluation.load timings`

Run 2026-10-15 15:12 UTC

| Measure | n | Median s | 95th percentile s | Max s | Target |
| --- | --- | --- | --- | --- | --- |
| Sandbox run, typical problem (TR-P-01), through the API | 20 | 0.17 | 0.39 | 0.44 | within 5 s, hard stop 10 s |
| Next diagnostic item, selection function alone (TR-P-02) | 200 | 0.1 ms | 0.2 ms | 9.3 ms | under 1 s |
| Placement answer end to end for a tracing item (answer, mastery update, next item) | 8 | 0.06 | 0.48 | 0.48 | (reference) |
| Verified explanation, new failure, live model (TR-P-03) | 8 | 4.04 | 14.75 | 14.75 | within 15 s |
| Explanation from the demo cache (TR-P-03) | 5 | 0.04 | 0.07 | 0.07 | within 1 s |

Live explanations: 8 x verified after 1 attempt(s)

The live explanation's worst case (14.75 s) is just inside the 15 s target; Gemini latency varied between runs on
earlier days too (4 to 23 s), so the demo uses the prepared explanations and the target is not claimed as met in general.

## Which provider is primary (TR-P-03)

`evaluation.provider_compare gemini groq`: the ten Step 4 wrong submissions through the verified flow for each provider
in turn, no fallback, demo cache off.

Run 2026-10-15 15:53 UTC, 10 wrong submissions per provider (the Step 4 set), verified flow, no fallback, demo cache off.

| Provider and model | Verified | Verified on attempt 1 | Template | Median s | Max s | Within 15 s |
| --- | --- | --- | --- | --- | --- | --- |
| gemini `gemini-3.5-flash-lite` | 10 of 10 | 10 of 10 | 0 | 2.32 | 15.31 | 9 of 10 |
| groq `openai/gpt-oss-20b` | 8 of 10 | 8 of 10 | 2 | 1.74 | 27.22 | 9 of 10 |

Decision: Gemini stays primary (10 of 10 verified on the first attempt against 8 of 10); Groq stays first in the
fallback chain. Ten submissions per provider is a small sample.

## Backup and restore

`pg_dump -Fc` of the dev database restored into a fresh database (`createdb lms_restore_check`, `pg_restore --no-owner`,
exit 0) on 2026-10-15: users 114 = 114, mastery events 1600 = 1600, chunks 72 = 72, schema version 0006 in both. The
scratch database was then dropped. The in-place restore in the README (drop, create, restore) was not run on the dev
database.

## Seed (TR-D-06)

`python -m app.seed` on the dev database, twice: the first run created 47 problems, embedded 8 notes and applied 360
synthetic answers; the second run reported 0 created, 0 updated, 47 unchanged problems, 0 notes embedded and 0 answers
applied.

## Clean clone (G5)

`git clone --branch step-6-integration` at commit 17ae5dc into an empty folder, `.env` copied in, then
`docker compose -p lmsclean up -d --build --wait` (2 min 49 s from 15:59:08 to 16:01:57 UTC, images partly cached).
`python -m app.seed` twice: first run 47 problems created, 8 notes embedded, 360 synthetic answers, both demo accounts
created with one-time random passwords; second run 0 created, 0 updated, 47 unchanged, 0 notes, 0 answers.
`evaluation.load runs 2`: 0 of 42 steps failed. With the model switched off (`LLM_PROVIDER=stub`, no fallback):
`runs 2` again 0 of 42 failed, the explanation came from the prepared demo cache and chat used the keyword rules.
`secret_scan.py` in the clone: passed, 73 commits, 197 tracked files. The scratch project was then removed.
