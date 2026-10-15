# Diagnostic simulation results

- Command: `python -m simulation.run --students 500 --seed 2026`
- Run at: 2026-10-15 09:33 UTC
- Simulated students: 500, bank: 47 items, test length: 10

## Error of the mastery vector (mean absolute error against true mastery)

| Items asked | adaptive | random | BKT (random order) |
| --- | --- | --- | --- |
| 1 | 0.280 | 0.279 | 0.280 |
| 3 | 0.278 | 0.280 | 0.280 |
| 5 | 0.277 | 0.280 | 0.279 |
| 8 | 0.275 | 0.275 | 0.274 |
| 10 | 0.270 | 0.273 | 0.271 |

Threshold = the error random selection reaches after 10 items (0.273). Adaptive selection reaches it after 9 items, 10% fewer than random (target in the PRD: at least 30% fewer).

## Coverage and ranking after 10 items

| Policy | Concepts touched (of 12) | Correlation of estimate with true mastery |
| --- | --- | --- |
| adaptive | 10.0 | 0.297 |
| random | 8.0 | 0.259 |
| BKT (random order) | 8.0 | 0.247 |

## Five-item sanity test (TR-V-06)

RMSE of the ability estimate after 5 adaptive items, against two definitions of true ability, compared with predicting the population mean (ability 0).

| True ability is | Estimate RMSE | Population-mean RMSE | Result |
| --- | --- | --- | --- |
| the average over all 12 concepts (declared before the first run) | 0.618 | 0.675 | beats the mean predictor |
| the average over the concepts the 5 items tested | 0.630 | 0.725 | beats the mean predictor |

## Prediction of held-out responses

16220 responses to bank items the adaptive test did not ask, pooled over students.

| Predictor | AUC | Calibration error (ECE, 10 bins) |
| --- | --- | --- |
| Adaptive selection + mastery update | 0.607 | 0.129 |
| Random selection + mastery update | 0.602 | 0.108 |
| BKT baseline (random order, learning rate 0.1) | 0.597 | 0.120 |
| Ability-only 2PL baseline (random order) | 0.680 | 0.071 |
| No evidence (every concept at its prior) | 0.502 | 0.076 |

## Limits

The students are synthetic and drawn from a different response model than the one the selector assumes (correlated continuous abilities, perturbed item parameters, different slip and guess values), but the simulator is my own and is not fitted to real learners. These numbers describe this bank and this simulator only, say nothing yet about real students, and the simulator was not changed after seeing results.

## Reading the results

- **PRD targets not met.** Adaptive selection reaches the random test's final error one item sooner (10% fewer items, target 30%), and the mastery vector stays far from true mastery after 10 items (mean error 0.27 against 0.28 for no evidence at all, target 0.15). Ten answers across twelve concepts carry little information about each concept.
- **The adaptive test does cover more concepts** (10.0 against 8.0 of 12) and ranks concepts better (correlation 0.30 against 0.26), which is where its advantage shows.
- **The concept-level mastery vector predicts held-out answers worse than a single ability number** (AUC 0.61 against 0.68) and is less well calibrated (ECE 0.13 against 0.07). This is the risk the TRD names for fixed slip and guess rates; the model should be described as a prototype.
- **The 5-item sanity test (TR-V-06) is only partly met, and the single-seed table above flatters it.** Across 10 seeds of 300 students (`python -m simulation.run` logic, seeds 1 to 10, run 2026-10-15), the 5-item ability estimate beat the population-mean predictor in **10 of 10** seeds when "true ability" means the concepts the five items tested, but in only **3 of 10** seeds when it means the average over all 12 concepts. Five items cannot say much about concepts they never touched. The reported seed 2026 happens to fall in the favourable 3.
- **What changed after the first run, so you can judge it.** The first run exposed two faults of mine. The held-out set contained items some predictors had already seen (fixed: it now excludes items asked by either test), and the 5-item ability estimate did not beat the mean predictor. I then made the ability likelihood allow for guessing and slipping, using the same default rates as the mastery update; it helped on every seed I tried and is also the correct model for four-option items. The simulator was not touched.
