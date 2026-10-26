# Step 75: the verifier now tests a claim's truth, not only its shape (TR-L-04, TR-L-05, TR-L-12)

## Why

Step 74's rater panel found two verified explanations that were false (`Countdown`: "your range counts up"; `Sum and
maximum`: "only considers the first number") and a verified-flow score below the plain call's (12 of 20 against 17 of 20
rated correct by both raters). Reading the code showed the cause: `verifier.py` checks that a reply is well formed (the test
failed, the line exists, the concept and sources are real, quoted code is the student's, nothing leaks). The only check
that tests what the code does, the sandbox run of `example_input`, applied only when the model chose to give one.

## What changed

| Change | Where |
| --- | --- |
| A reply must name an `example_input` and a `predicted_output` (what the student's program prints on it), except for a syntax error. New check `claim_testable`. | `verifier.py`, `explain.py` |
| The sandbox runs the student's program on the example; the claim is rejected unless the real output equals the prediction (`predicted_output` check). The retry is told what the program really prints and what was predicted. Programs stopped for time, memory or output are not compared. | `claim_check.py`, `prompt.py` |
| The stored-explanation cache serves an entry only if it carries a tried example, so older entries without one are no longer served. | `signature_cache.py` |
| Before asking the model, the student's code runs on the visible failed tests and the prompt says what it printed. | `explain.py`, `prompt.py` |
| Values the student can already see (visible test inputs and outputs) are no longer treated as hidden: "leap", "even" and "common" were rejected as hidden test data because a hidden test expects the same word. Hidden inputs stay protected. | `verifier.py`, `context.py` |
| The template fallback names the failing category (boundary, zero, negative numbers, ...) instead of a fixed topic sentence ("check whether separate if statements should be elif" on code that already used elif). | `fallback.py` |
| Prompt `explain-v4` (rule 7 and the retry instructions). | `prompt.py` |

## Tests

New or changed tests: `test_verifier.py` (+7), `test_claimed_input.py` (a reply without an example is not shown; a wrong
prediction is rejected and the retry is told the real output; the prompt carries the real output), `test_fallback_text.py`
(3). Existing fixtures now give an example and prediction. Feedback-related files: 167 passed; ruff clean.
Full suite: see the end-of-step report.

## What was measured, and what was not

`python -m evaluation.explain_rate` (28 varied failures, real provider chain, stored explanations bypassed), 2026-10-26,
in the throwaway stack. Step 71 on 2026-10-25 had 26 of 28 verified (93%), 0 provider failures, Gemini median 1.6 s.

| Run (UTC) | Rules | Verified | Fallbacks from provider failure | Verified when a provider answered |
| --- | --- | --- | --- | --- |
| 14:11 | v4 as first written | 21 of 28 (75%) | 3 | 21 of 25 (84%) |
| 14:16 | + advice to avoid textbook example values | 20 of 28 (71%) | 1 | 20 of 27 (74%) |
| 14:24 | + visible values not hidden | 13 of 28 (46%) | 8 | 13 of 20 (65%) |
| 14:33 | + "printed output only, empty on a crash" | 6 of 28 (21%) | 15 | 6 of 13 (46%) |
| 14:44 | + the student's real output in the prompt | 11 of 28 (39%) | 12 | 11 of 16 (69%) |

These five runs cannot be ranked against each other. Gemini's latency rose from a 2.3 s median to 12 s during the session
and from 14:50 UTC it timed out or could not connect from the container (read timeouts of 20 s, a connect error after 285 s,
a connect timeout); GitHub also timed out from this machine. The fallbacks column shows the provider failures, and the
last three runs are dominated by them. I did not get a run with a healthy provider after the last change.

What the runs do show:
- The new check rejects false pictures of the code. In the 14:33 run the logged rejections (the detail records the real
  output and the prediction) include: real output empty (the program crashed), predicted '10', '55', 'olleh', 'division by
  zero'; real 'even', predicted 'odd'; real 'no', predicted 'yes'; real 'Liftoff!', predicted '3 2 1 Liftoff!'. In these the
  model described what the correct program prints, not what the student's does, so a claim built on that picture was false.
  Two of the earlier false sheet rows are the same kind of mistake.
- A rejected trace can be repaired by the retry (rows 15, 23 and 26 verified on attempt 2 after a `predicted_output` rejection
  in the 14:33 run).
- The cost is real: a model that traces badly now falls back more often than before. How much is not yet separable from the
  provider outage.

## Gate

**Not yet met, because it was not measured.** The gate is the step-74 sheet re-run with the new flow and re-rated by the
panel. That needs a working Gemini. The code and tests are done; the measurement is open (command below).

    python -m evaluation.explain_rate
    python -m evaluation.rating_sheet generate S.csv K.csv
    python -m evaluation.rating_sheet llm-rate S.csv O.csv groq:openai/gpt-oss-20b,groq:qwen/qwen3.8-27b   # rerun on O.csv to fill gaps
    python -m evaluation.rating_sheet compute O.csv K.csv

If the verified rate stays low with a healthy provider, the next lever is a stronger model for explanations
(`gemini-3.1-pro-preview` answered 429 on 2026-10-25), not a looser check.
