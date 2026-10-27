# Step 79: the step-75 gate, measured (TR-L-04, TR-L-05, TR-L-12)

Date: 2026-10-27. Throwaway stack `lmssim` (compose project, ports 18000/18080), built from the step-79 code, seeded, with
`explanation_cache` truncated before generating. Provider chain as configured: `gemini-3.5-flash-lite`, then groq, mistral,
openai, local. Gemini answered in 0.8-1.4 s on a probe before the run, so the outage that blocked step 75 was over.

## Verify rate

    docker exec lmssim-api-1 python -m evaluation.explain_rate

28 varied failures, stored explanations bypassed: **26 of 28 verified (93%)**, all on the first attempt, 0 fallbacks from
provider failure, median 2.0 s, max 8.2 s. The two fallbacks were `Palindrome check` (hidden-data leak check, then
`claimed_input` on the retry) and `Leap year` (hidden-data leak check twice). Step 71 measured 26 of 28 (93%) before the
truth checks existed, so the stricter verifier costs no verified rate on a healthy provider.

## Re-rated sheet

    docker exec lmssim-api-1 python -m evaluation.rating_sheet generate S.csv K.csv
    docker exec lmssim-api-1 python -m evaluation.rating_sheet llm-rate S.csv O.csv groq:openai/gpt-oss-20b,groq:openai/gpt-oss-120b   # re-run on O.csv until no 429 gaps
    docker exec lmssim-api-1 python -m evaluation.rating_sheet compute O.csv K.csv

21 submissions, each shown as the verified flow's explanation and a plain model call, order shuffled per row.

| Flow | Reviewer 1 | Reviewer 2 | Where both reviewers agree |
| --- | --- | --- | --- |
| verified | 20 of 21 = 95% | 19 of 21 = 90% | 19 of 20 = 95% |
| plain | 20 of 21 = 95% | 20 of 21 = 95% | 20 of 21 = 95% |

Reviewer agreement 98% (kappa 0.79) over 42 explanations. Step 74 had the verified flow below the plain call (12 of 20
against 17 of 20); that gap is gone.

## Gate

**Met on the measurement, with one limit.** The verified flow is now rated as correct as the plain call (95% each where both
reviewers agree). The two raters are language models (`gpt-oss-20b` and `gpt-oss-120b`), not people, and one verified row
is still rated incorrect. At 21 rows one explanation is 5 points, so the verified and plain flows are not distinguishable
here. The human re-rating (G-5) is still open and is the only evidence that settles it.
