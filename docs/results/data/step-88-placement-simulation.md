 Container lms-sandbox-1 Running 
 Container lms-db-1 Running 
 Container lms-mastery-test-1 Running 
 Container lms-worker-test-1 Running 
 Container lms-redis-1 Running 
 Container lms-db-1 Waiting 
 Container lms-db-1 Healthy 
 Container lms-testdb-1 Starting 
 Container lms-testdb-1 Started 
 Container lms-testdb-1 Waiting 
 Container lms-testdb-1 Exited 
 Container lms-mastery-test-1 Waiting 
 Container lms-redis-1 Waiting 
 Container lms-testdb-1 Waiting 
 Container lms-testdb-1 Exited 
 Container lms-redis-1 Healthy 
 Container lms-mastery-test-1 Healthy 
 Container lms-worker-test-1 Waiting 
 Container lms-sandbox-1 Waiting 
 Container lms-mastery-test-1 Waiting 
 Container lms-mastery-test-1 Healthy 
 Container lms-sandbox-1 Healthy 
 Container lms-worker-test-1 Healthy 
 Container lms-test-run-67cea34959ec Creating 
 Container lms-test-run-67cea34959ec Created 
=== SEED 2026
# Diagnostic simulation results

- Command: `python -m simulation.run --students 500 --seed 2026`
- Run at: 2026-10-27 18:35 UTC
- Simulated students: 500, bank: 75 items, test length: 20

## Error of the mastery vector (mean absolute error against true mastery)

| Items asked | adaptive | random | BKT (random order) | adaptive + pooled | random + pooled |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.281 | 0.283 | 0.283 | 0.275 | 0.277 |
| 3 | 0.279 | 0.282 | 0.282 | 0.263 | 0.268 |
| 5 | 0.277 | 0.281 | 0.280 | 0.251 | 0.260 |
| 8 | 0.276 | 0.277 | 0.276 | 0.240 | 0.251 |
| 10 | 0.275 | 0.275 | 0.273 | 0.234 | 0.244 |
| 16 | 0.260 | 0.272 | 0.269 | 0.218 | 0.233 |
| 20 | 0.254 | 0.271 | 0.265 | 0.212 | 0.228 |

Threshold = the error random selection reaches after 20 items (0.271). Adaptive selection reaches it after 12 items, 40% fewer than random (target in the PRD: at least 30% fewer).

With the pooled estimate the threshold is random's error after 20 items (0.228). Adaptive selection reaches it after 12 items, 40% fewer than random.

## Selection baselines, all with the pooled estimate (TR-V-05)

The same estimator for every way of choosing questions, so the comparison is about the choice alone. Max-information adaptive is the textbook adaptive test: the question with the largest 2PL information at the current ability estimate, with no concept coverage term. Fixed order asks the allowed questions in id order.

| Items asked | adaptive | max-information adaptive | random | fixed order |
| --- | --- | --- | --- | --- |
| 1 | 0.275 | 0.275 | 0.277 | 0.274 |
| 3 | 0.263 | 0.266 | 0.268 | 0.265 |
| 5 | 0.251 | 0.257 | 0.260 | 0.254 |
| 8 | 0.240 | 0.245 | 0.251 | 0.247 |
| 10 | 0.234 | 0.239 | 0.244 | 0.243 |
| 16 | 0.218 | 0.227 | 0.233 | 0.230 |
| 20 | 0.212 | 0.222 | 0.228 | 0.222 |

Items needed to reach random selection's final pooled error (0.228), out of 20: adaptive 12, max-information adaptive 16, fixed order 18.

## Coverage and ranking after the whole test

| Policy | Concepts touched (of 12) | Correlation of estimate with true mastery |
| --- | --- | --- |
| adaptive | 12.0 | 0.384 |
| random | 10.7 | 0.317 |
| BKT (random order) | 10.7 | 0.306 |
| adaptive + pooled | 12.0 | 0.396 |
| random + pooled | 10.7 | 0.333 |
| max-information adaptive + pooled | 10.5 | 0.343 |
| fixed order + pooled | 12.0 | 0.366 |

## Five-item sanity test (TR-V-06)

RMSE of the average mastery estimated after 5 adaptive items against the student's true average mastery, compared with predicting the population mean of the true average mastery.

| Estimate | True value is | Estimate RMSE | Population-mean RMSE | Result |
| --- | --- | --- | --- | --- |
| independent | average over all concepts | 0.175 | 0.204 | beats the mean predictor |
| independent | average over the concepts the 5 items tested | 0.177 | 0.218 | beats the mean predictor |
| pooled | average over all concepts | 0.169 | 0.204 | beats the mean predictor |
| pooled | average over the concepts the 5 items tested | 0.175 | 0.218 | beats the mean predictor |

## Prediction of held-out responses

20459 responses to bank items the adaptive test did not ask, pooled over students.

| Predictor | AUC | Calibration error (ECE, 10 bins) |
| --- | --- | --- |
| Adaptive selection + mastery update | 0.629 | 0.094 |
| Random selection + mastery update | 0.612 | 0.103 |
| BKT baseline (random order, learning rate 0.1) | 0.611 | 0.122 |
| Ability-only 2PL baseline (random order) | 0.681 | 0.034 |
| Adaptive selection + pooled estimate | 0.690 | 0.065 |
| Random selection + pooled estimate | 0.683 | 0.058 |
| No evidence (every concept at its prior) | 0.520 | 0.053 |

## Limits

The students are synthetic and drawn from a different response model than the one the selector assumes (correlated continuous abilities, perturbed item parameters, different slip and guess values), but the simulator is my own and is not fitted to real learners. These numbers describe this bank and this simulator only, say nothing yet about real students, and the simulator was not changed after seeing results.
=== SEED 2027
# Diagnostic simulation results

- Command: `python -m simulation.run --students 500 --seed 2027`
- Run at: 2026-10-27 18:36 UTC
- Simulated students: 500, bank: 75 items, test length: 20

## Error of the mastery vector (mean absolute error against true mastery)

| Items asked | adaptive | random | BKT (random order) | adaptive + pooled | random + pooled |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.279 | 0.280 | 0.280 | 0.275 | 0.274 |
| 3 | 0.282 | 0.281 | 0.281 | 0.268 | 0.267 |
| 5 | 0.280 | 0.280 | 0.279 | 0.255 | 0.260 |
| 8 | 0.282 | 0.279 | 0.278 | 0.247 | 0.253 |
| 10 | 0.283 | 0.277 | 0.275 | 0.240 | 0.248 |
| 16 | 0.267 | 0.279 | 0.272 | 0.226 | 0.240 |
| 20 | 0.262 | 0.277 | 0.268 | 0.222 | 0.235 |

Threshold = the error random selection reaches after 20 items (0.277). Adaptive selection reaches it after 14 items, 30% fewer than random (target in the PRD: at least 30% fewer).

With the pooled estimate the threshold is random's error after 20 items (0.235). Adaptive selection reaches it after 13 items, 35% fewer than random.

## Selection baselines, all with the pooled estimate (TR-V-05)

The same estimator for every way of choosing questions, so the comparison is about the choice alone. Max-information adaptive is the textbook adaptive test: the question with the largest 2PL information at the current ability estimate, with no concept coverage term. Fixed order asks the allowed questions in id order.

| Items asked | adaptive | max-information adaptive | random | fixed order |
| --- | --- | --- | --- | --- |
| 1 | 0.275 | 0.274 | 0.274 | 0.272 |
| 3 | 0.268 | 0.266 | 0.267 | 0.268 |
| 5 | 0.255 | 0.258 | 0.260 | 0.262 |
| 8 | 0.247 | 0.250 | 0.253 | 0.257 |
| 10 | 0.240 | 0.245 | 0.248 | 0.252 |
| 16 | 0.226 | 0.230 | 0.240 | 0.240 |
| 20 | 0.222 | 0.222 | 0.235 | 0.234 |

Items needed to reach random selection's final pooled error (0.235), out of 20: adaptive 13, max-information adaptive 14, fixed order 19.

## Coverage and ranking after the whole test

| Policy | Concepts touched (of 12) | Correlation of estimate with true mastery |
| --- | --- | --- |
| adaptive | 12.0 | 0.360 |
| random | 10.7 | 0.307 |
| BKT (random order) | 10.7 | 0.302 |
| adaptive + pooled | 12.0 | 0.363 |
| random + pooled | 10.7 | 0.310 |
| max-information adaptive + pooled | 10.7 | 0.347 |
| fixed order + pooled | 12.0 | 0.311 |

## Five-item sanity test (TR-V-06)

RMSE of the average mastery estimated after 5 adaptive items against the student's true average mastery, compared with predicting the population mean of the true average mastery.

| Estimate | True value is | Estimate RMSE | Population-mean RMSE | Result |
| --- | --- | --- | --- | --- |
| independent | average over all concepts | 0.179 | 0.202 | beats the mean predictor |
| independent | average over the concepts the 5 items tested | 0.188 | 0.219 | beats the mean predictor |
| pooled | average over all concepts | 0.176 | 0.202 | beats the mean predictor |
| pooled | average over the concepts the 5 items tested | 0.187 | 0.219 | beats the mean predictor |

## Prediction of held-out responses

20437 responses to bank items the adaptive test did not ask, pooled over students.

| Predictor | AUC | Calibration error (ECE, 10 bins) |
| --- | --- | --- |
| Adaptive selection + mastery update | 0.613 | 0.103 |
| Random selection + mastery update | 0.592 | 0.116 |
| BKT baseline (random order, learning rate 0.1) | 0.593 | 0.131 |
| Ability-only 2PL baseline (random order) | 0.683 | 0.030 |
| Adaptive selection + pooled estimate | 0.689 | 0.080 |
| Random selection + pooled estimate | 0.682 | 0.062 |
| No evidence (every concept at its prior) | 0.531 | 0.063 |

## Limits

The students are synthetic and drawn from a different response model than the one the selector assumes (correlated continuous abilities, perturbed item parameters, different slip and guess values), but the simulator is my own and is not fitted to real learners. These numbers describe this bank and this simulator only, say nothing yet about real students, and the simulator was not changed after seeing results.
=== SEED 2028
# Diagnostic simulation results

- Command: `python -m simulation.run --students 500 --seed 2028`
- Run at: 2026-10-27 18:38 UTC
- Simulated students: 500, bank: 75 items, test length: 20

## Error of the mastery vector (mean absolute error against true mastery)

| Items asked | adaptive | random | BKT (random order) | adaptive + pooled | random + pooled |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.277 | 0.278 | 0.278 | 0.271 | 0.273 |
| 3 | 0.275 | 0.278 | 0.278 | 0.260 | 0.263 |
| 5 | 0.274 | 0.275 | 0.275 | 0.251 | 0.254 |
| 8 | 0.274 | 0.273 | 0.273 | 0.240 | 0.247 |
| 10 | 0.277 | 0.273 | 0.272 | 0.234 | 0.242 |
| 16 | 0.268 | 0.278 | 0.275 | 0.222 | 0.235 |
| 20 | 0.258 | 0.280 | 0.276 | 0.216 | 0.232 |

Threshold = the error random selection reaches after 20 items (0.280). Adaptive selection reaches it after 1 items, 95% fewer than random (target in the PRD: at least 30% fewer).

With the pooled estimate the threshold is random's error after 20 items (0.232). Adaptive selection reaches it after 11 items, 45% fewer than random.

## Selection baselines, all with the pooled estimate (TR-V-05)

The same estimator for every way of choosing questions, so the comparison is about the choice alone. Max-information adaptive is the textbook adaptive test: the question with the largest 2PL information at the current ability estimate, with no concept coverage term. Fixed order asks the allowed questions in id order.

| Items asked | adaptive | max-information adaptive | random | fixed order |
| --- | --- | --- | --- | --- |
| 1 | 0.271 | 0.274 | 0.273 | 0.272 |
| 3 | 0.260 | 0.265 | 0.263 | 0.263 |
| 5 | 0.251 | 0.257 | 0.254 | 0.253 |
| 8 | 0.240 | 0.248 | 0.247 | 0.248 |
| 10 | 0.234 | 0.242 | 0.242 | 0.241 |
| 16 | 0.222 | 0.228 | 0.235 | 0.230 |
| 20 | 0.216 | 0.222 | 0.232 | 0.226 |

Items needed to reach random selection's final pooled error (0.232), out of 20: adaptive 11, max-information adaptive 15, fixed order 16.

## Coverage and ranking after the whole test

| Policy | Concepts touched (of 12) | Correlation of estimate with true mastery |
| --- | --- | --- |
| adaptive | 12.0 | 0.362 |
| random | 10.8 | 0.301 |
| BKT (random order) | 10.8 | 0.283 |
| adaptive + pooled | 12.0 | 0.369 |
| random + pooled | 10.8 | 0.318 |
| max-information adaptive + pooled | 10.6 | 0.339 |
| fixed order + pooled | 12.0 | 0.322 |

## Five-item sanity test (TR-V-06)

RMSE of the average mastery estimated after 5 adaptive items against the student's true average mastery, compared with predicting the population mean of the true average mastery.

| Estimate | True value is | Estimate RMSE | Population-mean RMSE | Result |
| --- | --- | --- | --- | --- |
| independent | average over all concepts | 0.177 | 0.199 | beats the mean predictor |
| independent | average over the concepts the 5 items tested | 0.187 | 0.216 | beats the mean predictor |
| pooled | average over all concepts | 0.172 | 0.199 | beats the mean predictor |
| pooled | average over the concepts the 5 items tested | 0.183 | 0.216 | beats the mean predictor |

## Prediction of held-out responses

20497 responses to bank items the adaptive test did not ask, pooled over students.

| Predictor | AUC | Calibration error (ECE, 10 bins) |
| --- | --- | --- |
| Adaptive selection + mastery update | 0.617 | 0.103 |
| Random selection + mastery update | 0.601 | 0.109 |
| BKT baseline (random order, learning rate 0.1) | 0.599 | 0.124 |
| Ability-only 2PL baseline (random order) | 0.677 | 0.026 |
| Adaptive selection + pooled estimate | 0.692 | 0.059 |
| Random selection + pooled estimate | 0.680 | 0.053 |
| No evidence (every concept at its prior) | 0.519 | 0.047 |

## Limits

The students are synthetic and drawn from a different response model than the one the selector assumes (correlated continuous abilities, perturbed item parameters, different slip and guess values), but the simulator is my own and is not fitted to real learners. These numbers describe this bank and this simulator only, say nothing yet about real students, and the simulator was not changed after seeing results.
=== SEED 2029
# Diagnostic simulation results

- Command: `python -m simulation.run --students 500 --seed 2029`
- Run at: 2026-10-27 18:39 UTC
- Simulated students: 500, bank: 75 items, test length: 20

## Error of the mastery vector (mean absolute error against true mastery)

| Items asked | adaptive | random | BKT (random order) | adaptive + pooled | random + pooled |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.279 | 0.281 | 0.282 | 0.273 | 0.275 |
| 3 | 0.282 | 0.281 | 0.281 | 0.265 | 0.269 |
| 5 | 0.281 | 0.282 | 0.282 | 0.257 | 0.262 |
| 8 | 0.279 | 0.282 | 0.280 | 0.245 | 0.254 |
| 10 | 0.281 | 0.280 | 0.279 | 0.239 | 0.250 |
| 16 | 0.266 | 0.275 | 0.272 | 0.225 | 0.238 |
| 20 | 0.261 | 0.273 | 0.267 | 0.221 | 0.232 |

Threshold = the error random selection reaches after 20 items (0.273). Adaptive selection reaches it after 14 items, 30% fewer than random (target in the PRD: at least 30% fewer).

With the pooled estimate the threshold is random's error after 20 items (0.232). Adaptive selection reaches it after 13 items, 35% fewer than random.

## Selection baselines, all with the pooled estimate (TR-V-05)

The same estimator for every way of choosing questions, so the comparison is about the choice alone. Max-information adaptive is the textbook adaptive test: the question with the largest 2PL information at the current ability estimate, with no concept coverage term. Fixed order asks the allowed questions in id order.

| Items asked | adaptive | max-information adaptive | random | fixed order |
| --- | --- | --- | --- | --- |
| 1 | 0.273 | 0.273 | 0.275 | 0.274 |
| 3 | 0.265 | 0.263 | 0.269 | 0.266 |
| 5 | 0.257 | 0.256 | 0.262 | 0.260 |
| 8 | 0.245 | 0.247 | 0.254 | 0.250 |
| 10 | 0.239 | 0.242 | 0.250 | 0.245 |
| 16 | 0.225 | 0.228 | 0.238 | 0.235 |
| 20 | 0.221 | 0.221 | 0.232 | 0.230 |

Items needed to reach random selection's final pooled error (0.232), out of 20: adaptive 13, max-information adaptive 14, fixed order 19.

## Coverage and ranking after the whole test

| Policy | Concepts touched (of 12) | Correlation of estimate with true mastery |
| --- | --- | --- |
| adaptive | 12.0 | 0.377 |
| random | 10.7 | 0.327 |
| BKT (random order) | 10.7 | 0.318 |
| adaptive + pooled | 12.0 | 0.382 |
| random + pooled | 10.7 | 0.329 |
| max-information adaptive + pooled | 10.4 | 0.369 |
| fixed order + pooled | 12.0 | 0.326 |

## Five-item sanity test (TR-V-06)

RMSE of the average mastery estimated after 5 adaptive items against the student's true average mastery, compared with predicting the population mean of the true average mastery.

| Estimate | True value is | Estimate RMSE | Population-mean RMSE | Result |
| --- | --- | --- | --- | --- |
| independent | average over all concepts | 0.177 | 0.199 | beats the mean predictor |
| independent | average over the concepts the 5 items tested | 0.193 | 0.224 | beats the mean predictor |
| pooled | average over all concepts | 0.172 | 0.199 | beats the mean predictor |
| pooled | average over the concepts the 5 items tested | 0.188 | 0.224 | beats the mean predictor |

## Prediction of held-out responses

20464 responses to bank items the adaptive test did not ask, pooled over students.

| Predictor | AUC | Calibration error (ECE, 10 bins) |
| --- | --- | --- |
| Adaptive selection + mastery update | 0.612 | 0.110 |
| Random selection + mastery update | 0.601 | 0.113 |
| BKT baseline (random order, learning rate 0.1) | 0.604 | 0.127 |
| Ability-only 2PL baseline (random order) | 0.686 | 0.034 |
| Adaptive selection + pooled estimate | 0.692 | 0.064 |
| Random selection + pooled estimate | 0.686 | 0.060 |
| No evidence (every concept at its prior) | 0.524 | 0.061 |

## Limits

The students are synthetic and drawn from a different response model than the one the selector assumes (correlated continuous abilities, perturbed item parameters, different slip and guess values), but the simulator is my own and is not fitted to real learners. These numbers describe this bank and this simulator only, say nothing yet about real students, and the simulator was not changed after seeing results.
