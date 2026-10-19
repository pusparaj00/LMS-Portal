# Step 56: the error floor and the pooled placement model (TR-V-05, TR-V-06, TR-M-15, TR-M-18)

Measured on 2026-10-19, branch `step-56-pooled-model`, in the test container. Every number below comes from a command in
this document. The students are synthetic (a simulator I wrote, and 50 LLM-persona students from step 40), not real learners.

## 56a: how low can the error go? (`python -m simulation.floor --students 300 --seed 2026`, 13:35 UTC)

An oracle that knows the simulator's true item parameters, slip, guess and ability correlation, using the exact Bayesian
estimate. No estimator can beat it on average on these students.

| Answers behind the estimate | Questions | Oracle error (mean absolute) |
| --- | --- | --- |
| none (the prior only) | 0 | 0.282 |
| 1 best question per concept, same for everyone | 12 | 0.226 |
| 2 best questions per concept | 24 | 0.206 |
| 3 best questions per concept | 33 | 0.198 |
| the 18 questions the adaptive test chose | 18 | 0.224 |
| the whole bank | 47 | 0.187 |

**Finding:** the PRD target "error under 0.15" cannot be reached on this simulator and bank by any estimator, even with
all 47 questions answered. A right or wrong answer carries little information about a continuous mastery, so the error
only falls from 0.282 (no answers) to 0.224 (18 questions). The room for improvement is the gap between the old estimate
(0.278 after 18 questions) and 0.224. The 30%-fewer-questions part of TR-V-05 is still reachable in principle: 12 well-chosen
questions already give the oracle 0.226, about what random order needs 18 for.

## 56b: what was built

- `app/diagnostic/pooled.py`: a multidimensional 2PL, one ability per concept, with the abilities correlated, solved by
  Fisher scoring (numpy only). Mastery = chance of a right answer to an item with a = 1, b = 0, no guessing.
- Selection (`selection.py`) now scores each question by concept coverage plus the expected shrinkage of the uncertainty of
  that estimate. The old per-concept entropy and the ability-information terms are gone.
- At the end of placement the mastery service writes one `pooled_estimate` ledger row per concept that rests on the
  placement alone (value stored, replayable); concepts with other evidence keep their own estimate. This replaces the
  step-54 `ability_inference` rows, which still replay.
- Selection takes 2.9 ms (median) and 5.0 ms (max) per question on the demo bank, measured in the test container.

## Choosing the two settings (correlation, prior spread)

Chosen before looking at any held-out data, on training data only: circular seeds 1, 2, 3 (300 students each) and the
first 25 persona students. Rule: the smallest worst-case relative regret across the two training sets.

| Correlation / spread | Circular, mean error at 18 (best 0.2210) | Persona, error at 18 (best 0.136) |
| --- | --- | --- |
| 0.1 / 1.5 | 0.2307 | 0.142 |
| 0.3 / 1.0 | 0.2263 | 0.152 |
| **0.3 / 1.5 (chosen)** | 0.2253 | 0.142 |
| 0.5 / 1.5 | 0.2210 | 0.147 |
| 0.7 / 1.5 | 0.2213 | 0.158 |

The two training sets disagree on the best correlation (0.5 to 0.7 on the simulator, whose true pairwise correlation is
0.36; 0.0 on the personas), so 0.3 is a compromise, not a finding about real students. It must be refitted from real answers.

## Held-out results with the chosen settings

Circular simulator, `python -m simulation.run --students 500 --seed S` (seed 2026 at 13:50 UTC; 2027 to 2029 after):

| Measure | Before (step 54, seed 2026) | After, seed 2026 | After, seeds 2027 / 2028 / 2029 |
| --- | --- | --- | --- |
| Error at 18 questions, adaptive | 0.265 (independent estimate) | 0.219 (pooled) | 0.226 / 0.224 / 0.226 |
| Error at 18 questions, random | 0.267 | 0.228 | 0.233 / 0.230 / 0.234 |
| Questions saved vs random (target 30%) | 0% | 28% | 22% / 17% / 28% |
| Held-out AUC, concept estimate / ability-only | 0.630 / 0.701 | 0.712 / 0.703 | 0.698 / 0.694, 0.692 / 0.683, 0.693 / 0.691 |
| 5-question test beats the mean predictor | yes (old metric) | yes, 0.174 vs 0.204 | not run |

Persona students (held-out second half, 25 students, `--part second`; all 50 in brackets):

| Measure | Result |
| --- | --- |
| Error at 18 questions, adaptive pooled / random pooled | 0.154 / 0.177 (0.150 / 0.168) |
| Adaptive reaches random's 18-question error after | 9 questions (9) |
| Held-out AUC, pooled / ability-only | 0.879 / 0.786 |
| Calibration error (ECE), pooled / ability-only | 0.168 / 0.087 (worse) |
| 5-question test beats the mean predictor | no, 0.073 vs 0.057 (0.075 vs 0.061) |

## Verdicts

- **TR-V-05, efficiency (30% fewer questions): not met.** Mean over four untouched simulator seeds is 24% (17% to 28%).
  On the persona half it is 9 of 18 questions, but that is 25 students from a small model.
- **TR-V-05, error under 0.15: not reachable on the simulator** (floor 0.187 even with the whole bank). On the personas
  the pooled error is 0.150 to 0.154, at the edge of the target on very few students.
- **TR-V-05, beats the ability-only baseline on held-out answers: met** on all four simulator seeds (by 0.002 to 0.009,
  a slim margin) and on the personas (0.879 vs 0.786), with worse calibration on the personas.
- **TR-V-06: met on the simulator, not met on the personas.** The persona students differ so little in average mastery
  (population-mean RMSE 0.057 to 0.061) that no five-question estimate can beat predicting the mean.

## Two corrections to earlier results

- **The TR-V-06 check was flawed.** It compared an ability on a log-odds scale with mean mastery between 0 and 1 and
  used "predict 0" as the population mean, which is not a mean for the persona data. It now compares the estimated
  average mastery with the true average mastery and the sample mean of it. Before and after on the simulator: the old
  check passed on the concepts tested only; the new one passes both ways. The persona check still fails, for the reason above.
- **The early stop is removed.** After 16 questions the three least certain concepts have a mastery spread of 0.46 / 0.47 /
  0.49 (10th / 25th / 50th percentile, 200 simulated students, seed 2026), and only 4% are below 0.45. No threshold
  separates students who could stop, so a rule "stop at 16 when uncertainty is low" would never fire. The test now runs to
  the longest length the course allows (PRD F-22 and TRD TR-M-03 updated).

## Other measurements

- Shuffling costs nothing measurable. Questions needed to reach random's 18-question error, four seeds of 300 students:
  13, 13, 18, 15 with the 10% shuffle, 14, 14, 15, 15 at 3%, 13, 13, 17, 14 with none (deterministic).
- Live probe on course 409: an all-wrong student ends with concepts at 0.08 to 0.18 (before: several at 0.00); an
  all-right student at 0.78 to 0.86; a mixed student at 0.32 to 0.64.
- `python -m pytest` through `docker compose --profile test run --rm --build test`: 950 passed, lint clean.

## What this means

The new estimate cuts the error from 0.265 to 0.219 on the same seed (about 17% lower), which is at the level of the oracle's
0.224 (a different student sample, so only roughly comparable). The remaining gap to the PRD targets is information, not method: one answer per concept cannot
pin down a concept. More questions per concept, questions that cover several concepts, or answers from real students to
fit the correlation and difficulties (TR-M-05) are what can still move it.
