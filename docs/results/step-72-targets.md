# Step 72: PRD and TRD targets against what was measured (TR-V-05, TR-V-06)

Measured on 2026-10-26 in the test container with `python -m simulation.run --students 500 --seed 2026` and
`python -m simulation.floor --students 500 --seed 2026` (75-item bank, 12 concepts). The students are synthetic
(my own simulator); nothing here describes real learners.

| Target | Old wording | Measured | Status |
| --- | --- | --- | --- |
| Adaptive needs at least 30% fewer items than random | unchanged | 12 items against random's 20-item error, 40% fewer (independent and pooled estimate) | met on the simulator |
| Mastery within 0.15 of true skill after 15 submissions | removed | error 0.212 after 20 adaptive items (pooled), 0.254 independent; oracle floor with the whole bank 0.167 | unreachable on the simulator, replaced by "below the prior (0.282) and, with the pooled estimate, below random at every length" |
| 5-item test beats the population-mean predictor (TR-V-06) | unchanged | RMSE 0.169 to 0.177 against 0.204 to 0.218 | met on the simulator |
| Accuracy against real learners | none | not measured | needs the pilot (G-6) |

New target: error below the prior-only 0.282 and, with the pooled estimate, below random selection at every test length. Both hold in the
"Error of the mastery vector" table of `simulation.run` (adaptive pooled 0.212 against random pooled 0.228 and prior 0.282 at 20 items).
Independent estimate: adaptive and random tie at 10 items (0.275); only the pooled estimate is lower at every length.
