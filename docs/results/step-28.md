# Step 28 results: one time budget for a new explanation (TR-P-03, TR-L-12)

All runs on 2026-10-17, branch `step-28-explain-budget`.

## The gap

TR-P-03 (P0) asks for a verified explanation within 15 s of a new failure. The earlier worst cases were 14.75 s and
15.31 s, and runs on earlier days reached 23 s.

The model adapter already had a 20 s budget per answer, but a new explanation makes up to two attempts. Each attempt
started a fresh 20 s, so nothing bounded the total.

## What was built

- **`EXPLAIN_BUDGET_S`, default 14 s:** the whole explanation must end within it, both attempts and their checks,
  leaving a margin under 15 s.
- **The model's share:** each model call gets what is left minus 1.5 s kept back for checking the answer. The sandbox
  example run measured under 0.5 s.
- **Stopping early:** when too little time is left, no second attempt is started. The student then gets the template
  hint, as TR-L-12 prescribes, and a `time_budget` row is logged.
- **No late answers are shown.** Nothing is shown before verification, as before.
- **`llm.deadline_within()`:** a caller-set deadline that the fallback chain respects; it no longer starts its own
  20 s past it. The chat and other model uses keep their 20 s budget.

## Measured with the real models

`python -m evaluation.provider_compare <provider>`: the 10 wrong submissions of the Step 4 set, each made unique so no
cache answers, verified flow, demo cache off, no provider fallback, 2026-10-17.

| Provider and model | Verified | Template | Median s | Max s | Within 15 s |
| --- | --- | --- | --- | --- | --- |
| gemini `gemini-3.5-flash-lite` | 6 of 10 | 4 | 8.57 | 12.69 | 10 of 10 |
| groq `openai/gpt-oss-20b` | 9 of 10 | 1 | 0.27 | 3.68 | 10 of 10 |
| gemini_pro `gemini-3.5-flash-lite` (the configured primary), two runs | 1 of 10, 1 of 10 | 9, 9 | 1.12, 1.30 | 8.41, 2.55 | 10 of 10, 10 of 10 |

**The bound holds.** All 40 replies came back within 15 s; the slowest was 12.69 s.

**What it costs on a slow model.** The check log shows why Gemini's 4 templates happened: in all 4, the first call
had not answered when its share of the budget ran out ("time budget used up"), so no second attempt was started
("14 s used up before attempt 2"). Before this step, those students would have waited longer than 15 s. Gemini's
median today was 8.57 s, against 2.32 s on 15 Oct.

**Found while measuring, not caused by this step.** The configured primary key, `gemini_pro`, is refused by the
provider:
- 403 for `gemini-3.5-flash-lite`;
- 429 for `gemini-3.1-pro-preview`.

The `gemini` and `groq` keys work: one probe each answered "OK". In the running app the fallback chain still reaches
them, after the refused key. This needs the key owner (see the report).

## Tests

`docker compose --profile test run --rm --build test`: **656 passed**, ruff clean. `backend/tests/test_explain_budget.py`
has 4 tests:
- **Deadlines:** a deadline caps calls inside it, and an inner one never extends an outer one.
- **The fallback chain:** it stops at its caller's deadline, not at its own 20 s.
- **A model slower than the budget:** the student gets the template within budget + 1 s, after only one call. The log
  shows `llm_call` failed, `time_budget` and a final fallback.
- **A model inside the budget:** the explanation is still verified.

The tests use a fake model that, like the real adapters, waits no longer than the deadline allows.
