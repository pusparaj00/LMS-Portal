# Step 25 results: difficulty estimates for new problems (F-23, TR-D-03)

All runs on 2026-10-16, branch `step-25-difficulty-estimates`.

## What the documents ask

The PRD (P2): "newly added or generated items get initial difficulty estimates from text and concept tags". TR-D-03
already stores each difficulty "with a source flag" (`param_source`: prior or estimated). No method or target is named.
Generated items are later work (TR-L-10), so this covers problems a teacher adds.

## What was built

- `app/difficulty.py` fits a small ridge regression on the question bank's 35 coding problems. It uses no model call,
  so the same input always gives the same estimate. The features are:
  - the reference solution's non-blank lines, deepest nesting and number of control structures and comprehensions;
  - the statement's word count;
  - the number of concept tags;
  - the bank's average difficulty for problems sharing those concepts (the overall mean when none does).

  Estimates are kept within the placement model's range, −2 to 2.
- In the problem form, Difficulty has a new first choice, **Estimate it for me**. It sends an empty difficulty; the
  server estimates it, stores `param_source = 'estimated'`, and the edit form then shows the current estimate. A chosen
  level stays `prior`, as before. The API refuses difficulties outside −2 to 2.
- `python -m evaluation.difficulty_model` reproduces the measurement below.

## Measured

Leave-one-out on the bank (2026-10-16): each problem is held out and the model, including the concept averages, is
fitted on the other 34. The table gives the mean absolute error against the bank's difficulty:

| Ridge | Model | Always the bank mean | Concept average alone |
| --- | --- | --- | --- |
| 0.1 | 0.376 | 0.607 | 0.557 |
| 1.0 | 0.372 | 0.607 | 0.557 |
| 3.0 (in use) | 0.370 | 0.607 | 0.557 |
| 10.0 | 0.372 | 0.607 | 0.557 |
| 30.0 | 0.389 | 0.607 | 0.557 |

The estimate's error is about 39% lower than always guessing the mean. **What this measures:** the bank's difficulties
are its authors' judgement, not calibrated on real answers, so the estimate agrees with that judgement. Whether either
matches how hard students find a problem is a question for the pilot (TR-M-05, Phase 6).

## Tests

`docker compose --profile test run --rm --build test`: **648 passed**, ruff clean. `backend/tests/test_difficulty.py`
has 3 tests:
- **Repeatable and ordered:** the same input gives the same estimate, inside the range, and a one-liner rates below a
  nested class.
- **Beats the baselines:** the model's leave-one-out error is below the concept average's, which is below the mean's.
- **Through the API:** an empty difficulty is estimated, equals the model's value and is marked `estimated`, also in
  the editor's source; a chosen value stays `prior`; switching an existing problem to "estimate" marks it `estimated`;
  3 is refused.

## Browser run (Chromium, Playwright)

At 1366 x 768 and 390 x 844, a throwaway teacher added "Sum of a list" with "Estimate it for me". The sandbox checked
it, it was saved with difficulty −0.51 (`estimated`), and the edit form showed "Estimate it for me" and "Current
estimate: −0.51". No page errors, no 5xx responses, no overflow.

One defect was found and fixed on the way: the help text sat inside the Difficulty label, so the field's accessible name
read the whole sentence. It is now outside the label and linked with `aria-describedby`.
