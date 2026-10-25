# Step 68: placement (TR-M-19, TR-M-20, TR-V-05, TR-V-06)

Measured on 2026-10-25 in the test container (`docker compose -p lmssb --profile test run --rm --no-deps ... test python -m ...`).
The students are synthetic: a simulator I wrote (`simulation.run`) and 50 LLM-persona students from step 40
(`simulation.noncircular`). No real learner is involved, so none of this says anything about real students.

## What changed

1. The bank grew from 61 to 75 items: 14 new tracing questions on the concepts that had almost none (tuples and sets,
   recursion, exceptions, comprehensions, classes, variables), with 15 new named misconceptions. All 75 validate in the
   sandbox (`python -m app.bank_import /data/bank --dry-run`: "validated 75 of 75").
2. The weight of concept coverage in the selector is a declared constant, `selection.COVER_WEIGHT = 0.25`, chosen on
   training seeds 1 to 3 only (below). It replaces the uncommitted `0.5 * cover` edit, which had no recorded basis.
3. A tracing question's guess rate is 1 divided by its number of options (3 for 33 of the 40 questions), not the single
   value 0.25 (TR-M-20). This applies in the selector, the pooled estimate and its replay in the mastery service. The
   "guessing" and "don't know" variants keep their own rates.

## Choosing the weight (training seeds 1 to 3, 300 students each, `--cover-weight W`)

Rule, as in step 56: the smallest worst-case relative regret in the final pooled error across the three seeds.

| Weight | Bank of 61: error at 20 (s1 / s2 / s3) | Worst regret | Bank of 75: error at 20 (s1 / s2 / s3) | Worst regret |
| --- | --- | --- | --- | --- |
| 0.25 | 0.221 / 0.224 / 0.217 | 1.8% | 0.227 / 0.218 / 0.219 | **1.34%** |
| 0.5 | 0.224 / 0.223 / 0.220 | 1.4% | 0.226 / 0.218 / 0.223 | 1.83% |
| 0.75 | 0.228 / 0.223 / 0.221 | 3.2% | 0.226 / 0.221 / 0.223 | 1.84% |
| 1.0 | 0.225 / 0.223 / 0.219 | 1.8% | 0.225 / 0.217 / 0.222 | 1.37% |
| 1.5 | 0.224 / 0.220 / 0.222 | 2.3% | 0.224 / 0.219 / 0.225 | 2.74% |

The winner changed from 0.5 (old bank) to 0.25 (final bank), and all weights end within 0.004 of each other: the weight
is not a sensitive setting. I followed the rule on the final bank and make no claim that 0.25 is better than 1.0.

Guess rate, training seeds, final error of the adaptive pooled estimate (truth old = simulator's 0.20 guess; truth
options = simulated students guess 1 / options): truth old, app old / new: 0.224, 0.222, 0.217 / 0.225, 0.223, 0.219;
truth options, app old / new: 0.230, 0.231, 0.224 / 0.230, 0.225, 0.223. A difference of about 0.002 either way; kept
because it states a fact about the questions, not because it is a large gain.

## Held-out results (seeds 2026 to 2029, 500 students each, final bank of 75)

`python -m simulation.run --students 500 --seed S --bank /data/bank` (new settings) and with
`--cover-weight 1.0 --no-option-chance` (the behaviour before this step). Pooled estimate, after 20 questions.

| Seed | Old: adaptive error / random error / questions saved | New: adaptive / random / saved |
| --- | --- | --- |
| 2026 | 0.217 / 0.228 / 30% | 0.212 / 0.228 / 40% |
| 2027 | 0.220 / 0.233 / 35% | 0.222 / 0.235 / 35% |
| 2028 | 0.216 / 0.231 / 40% | 0.216 / 0.232 / 45% |
| 2029 | 0.218 / 0.231 / 35% | 0.221 / 0.232 / 35% |
| **Mean** | **0.2178 / 0.2308 / 35.0%** | **0.2178 / 0.2318 / 38.75%** |

Same runs with the simulated students guessing 1 / options (`--true-guess-from-options`): old 0.2250, saved 32.5%;
new 0.2238, saved 38.75%.

Before the bank grew (61 items, old behaviour, seeds 2026 to 2029, run earlier today): questions saved 15%, 30%, 20%,
30%, mean 23.75%.

## What this means

- **TR-V-05, 30% fewer questions: met on the simulator on all four held-out seeds** (both settings), and not met before
  the bank grew (23.75%). The bank, not the weight, made the difference: the old and new settings have the same mean
  error (0.2178). "Questions saved" moves in steps of 5% and depends on random's own final error, so a 3.75-point gap
  between the settings is within what that measure can show.
- **TR-V-05, error under 0.15: still not reachable on the simulator.** Floor of an oracle that knows the simulator's true
  parameters (`python -m simulation.floor --students 300 --seed 2026`, 17:32 UTC): 0.282 with no answers, 0.217 with the
  20 questions the adaptive test chose, 0.173 even with the whole bank of 75. The app's pooled estimate after 20 questions
  (0.212 to 0.222) is already at that 0.217 oracle level: what is left is missing information in right/wrong answers, not
  a better selector. The PRD target text should say "within about 0.22 after 20 questions on the simulator" or be dropped.
- **Personas (50, `python -m simulation.noncircular --students-json ... --bank /data/bank`, items they answered only:
  41, none of the 14 new ones):**

| Setting | Error at 18 (adaptive pooled / random pooled) | Adaptive reaches random's 18-question error after | 5-question test (pooled RMSE vs mean predictor 0.061) | AUC / ECE adaptive pooled |
| --- | --- | --- | --- | --- |
| Old | 0.150 / 0.168 | 9 questions | 0.075, does not beat it | 0.867 / 0.145 |
| New | 0.147 / 0.167 | 11 questions | 0.080, does not beat it | 0.851 / 0.155 |

  The two settings are indistinguishable. The 5-question test (TR-V-06) fails on personas for a stated reason: their
  true average mastery hardly varies (predicting the mean already has RMSE 0.061), so five answers cannot beat it; it
  passes on the simulator (0.169 against 0.204 on seed 2026). Pooled estimates are less well calibrated than the
  ability-only baseline on personas (ECE 0.155 against 0.099).

## Not done, and limits

- The persona file has no answers for the 14 new questions; scoring them needs a new persona run with a local model
  (Ollama was not running). Persona results above therefore do not test the new bank.
- Slip, guess for code, correlation 0.3 and prior spread 1.5 are unchanged and still need real answers (TR-M-05).
- Everything depends on the simulator and the personas; a pilot with students is the only way to settle these targets.
