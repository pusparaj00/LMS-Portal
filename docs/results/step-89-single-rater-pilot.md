# Step 89: single-rater pilot of the three explanation flows (TR-V-03, partial)

Dates: sheet generated 2026-10-28, rated 2026-10-28. Raw data: `docs/results/data/step-89-rated-sheet.csv` (as returned,
unchanged) and `docs/results/data/step-89-rating-key.csv` (which explanation came from which flow).

**This is not the TR-V-03 result.** TR-V-03 asks for two human raters marking each explanation correct or incorrect (0/1).
This pilot has one rater, a 1 to 5 scale, no agreement figure and no interval. G-5 stays open.

## Method

    docker exec lmssim-api-1 python -m evaluation.rating_sheet generate /tmp/sheet60.csv /tmp/key60.csv --size 60 --hint

The command asked for 60 submissions and produced 27: for the other 33 the plain or hint call failed after every provider
returned 429, "time budget used up" or `ConnectTimeout`, and the generator skips such items. For each of the 27 failing
submissions the sheet shows three explanations in random order: the verified flow (or its template fallback), a plain LLM
call, and a hint-only call. The rater saw the sheet without the key. One rater filled `r1_exp1` to `r1_exp3` with a 1 to 5
score and a free-text note per item; the `r2_` columns are empty. The score scale was not defined in the sheet's
instructions, so what a 3 or a 4 means was left to the rater. Who the rater is has not been recorded here.

## Result (one-off join of the scores with the key, 2026-10-28; `compute` cannot read 1 to 5 scores)

| Flow | Explanations | Mean score | Median | Count of 1 / 2 / 3 / 4 / 5 |
| --- | --- | --- | --- | --- |
| hint-only | 27 | 3.89 | 4 | 3 / 2 / 3 / 6 / 13 |
| plain LLM | 27 | 3.30 | 3 | 1 / 3 / 10 / 13 / 0 |
| verified flow (as shown to a student) | 27 | 3.00 | 3 | 3 / 2 / 14 / 8 / 0 |

Within the verified flow: the 14 items where the verifier passed scored a mean 2.71, and the 13 items where the template
fallback was shown scored a mean 3.31.

## What this does and does not show

- Ordering hint-only > plain > verified on this rater's scores. Like step 74 (LLM raters), it does not support "the verified
  flow explains better than a plain call". One rater, 27 items and no interval: directional only.
- Scores measure perceived quality on an undefined 1 to 5 scale, not the correctness criterion of TR-V-03. They cannot be
  turned into a correct share without choosing a cut-off, and none was chosen.
- The template fallback was shown for 13 of 27 submissions. Provider timeouts and 429s occurred during this run, so part of
  that share may come from provider failures and not from verifier rejections. It is not a clean fallback rate.
- The free-text notes flag specific wrong claims in some explanations. They were not mapped to flows or tallied.

## What is needed to close G-5

Two raters, working separately, marking each explanation 0 or 1 by the rubric in `backend/evaluation/rating_sheet.py`, on a
sheet generated when providers are not rate-limiting; then `python -m evaluation.rating_sheet compute SHEET.csv KEY.csv`.
