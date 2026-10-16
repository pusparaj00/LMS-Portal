# Step 30: gate G5 evidence measured again on the current code

The G5 numbers in `integration.md` were measured on 15 Oct, before Steps 7 to 29. This is the same evidence on the
code as of `step-29-request-trace`, run 2026-10-17 (the script prints UTC, 2026-10-16 20:26 to 20:28) against the
local Docker stack. Commands run from the repository root as `docker compose exec -T api python -m <module>`.

| Check | Requirement | Result | Verdict |
| --- | --- | --- | --- |
| `evaluation.load runs 10`: 10 consecutive demo runs, each a new student through the whole demo script | TR-V-10, TR-P-06 | 210 steps, **0 failed**, 10 of 10 runs clean | Pass |
| `evaluation.load concurrent 10`: 10 students at once, live uncached explanations | TR-V-10, TR-P-04 | 210 steps, **0 failed**, 32.1 s for all 10 | Pass |
| `evaluation.load prepare`, restart of api, worker and mastery, then `verify` | TR-P-07 | The old token still signs in; the half-done placement test (4 items) continued and finished after 10 items, mastery for 12 concepts | Pass |
| `evaluation.load cache 5`: the same wrong code from new students | TR-V-11 | 5 of 5 later students got the stored explanation in 0.02 to 0.04 s, no model call | Pass |
| Database dump: `pg_dump -Fc` to `backup/lms-2026-10-17.dump`, read back with `pg_restore --list` | TR-P-07 | 643,340 bytes, data for 33 tables; ignored by git | Taken |

## Step times, 10 consecutive runs

| Step | Count | Median s | 95th percentile s | Max s |
| --- | --- | --- | --- | --- |
| register | 10 | 0.26 | 0.69 | 0.69 |
| enroll | 10 | 0.01 | 0.23 | 0.23 |
| placement start | 10 | 0.02 | 0.15 | 0.15 |
| placement answer | 100 | 0.04 | 0.23 | 0.73 |
| dashboard | 10 | 0.01 | 0.04 | 0.04 |
| submit wrong code | 10 | 0.23 | 0.29 | 0.29 |
| explanation (cached demo) | 10 | 0.03 | 0.13 | 0.13 |
| hint | 10 | 0.03 | 4.25 | 4.25 |
| probe answer | 10 | 0.20 | 0.29 | 0.29 |
| chat: hint | 10 | 3.80 | 14.91 | 14.91 |
| chat: progress | 10 | 11.55 | 17.19 | 17.19 |
| instructor heatmap | 10 | 0.03 | 4.83 | 4.83 |

## Step times, 10 concurrent students

| Step | Count | Median s | 95th percentile s | Max s |
| --- | --- | --- | --- | --- |
| register | 10 | 2.15 | 2.19 | 2.19 |
| enroll | 10 | 0.06 | 0.07 | 0.07 |
| placement start | 10 | 0.12 | 0.15 | 0.15 |
| placement answer | 100 | 0.21 | 1.66 | 1.76 |
| dashboard | 10 | 0.01 | 0.02 | 0.02 |
| submit wrong code | 10 | 1.40 | 1.46 | 1.46 |
| explanation (live, uncached) | 10 | 1.27 | 1.56 | 1.56 |
| hint | 10 | 0.46 | 0.80 | 0.80 |
| probe answer | 10 | 2.57 | 3.50 | 3.50 |
| chat: hint | 10 | 9.31 | 12.33 | 12.33 |
| chat: progress | 10 | 1.94 | 10.56 | 10.56 |
| instructor heatmap | 10 | 0.03 | 0.05 | 0.05 |

## What changed since 15 Oct, and why

**The chat steps are slower.** "chat: progress" had a median of 2.19 s on 15 Oct and 11.55 s now (max 17.19 s), and
"chat: hint" a 95th percentile of 7.23 s then and 14.91 s now. Both go through the model. Step 28 found that the
configured primary key (`gemini_pro`) is refused (HTTP 403 and 429), so each chat call first fails on it and then
answers through `gemini`, whose median that day was 8.57 s, against 2.32 s on 15 Oct. Nothing failed; it was slow. The
remedy is a working primary key or a faster primary provider. That is the key owner's choice, so it was not changed.

**Not re-run here:** the timings table (`evaluation.load timings`). The new-explanation time is covered by the
measured run in [step-28](step-28.md).

## What G5 still needs (people)

- A backup video.
- The updated report.
- Two rehearsals.
- The IPR conversation.

The explanation ratings (TR-V-03) move to after the review, because no reviewers are available before 21 Oct.
