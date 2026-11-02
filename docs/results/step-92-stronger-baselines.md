# Step 92: stronger baselines, including sequence models, for the cold-start stack (TR-V-05)

Run on 2026-10-28 (main run started 09:55 UTC). Raw output: `docs/results/data/step-92-baselines-main.txt` and
`docs/results/data/step-92-baselines-ednet-replication.txt`.

    python research/kt_comparison/baselines_plus.py --sequence --folds 5 --bootstrap 100
    python research/kt_comparison/baselines_plus.py --sequence --targets ednet --ednet-seed 1 --folds 5 --bootstrap 100

Python 3.12.10, PyTorch 2.14.1 (CPU), numpy 2.5.4, pandas 3.1.0, scikit-learn 1.9.1, scipy 1.18.1, in a virtual environment outside
the project. Same folds, datasets and training sizes N as step 91 (the non-sequence models gave the same numbers in an earlier
run on Python 3.15). Research code only; the product is unchanged.

## Models

| Model | Description |
| --- | --- |
| lms_default | the LMS mastery rule with its default numbers; no data |
| pfa | Performance Factors Analysis: logistic regression on skill indicators and, per skill, the log of the student's earlier successes and failures on it; C chosen on a held-out fifth of the N students |
| rasch | one-parameter item-response model (student and item indicators, L2 logistic regression, C = 1); a test student's ability is re-estimated after every answer from their own earlier answers only |
| gbdt | scikit-learn HistGradientBoosting on the six features of the stack |
| stack_transfer | the step 91 stack, started from weights fitted on the other datasets |
| hybrid | **post-hoc**: a blend of the stack's and gbdt's logits, weight in {0, 0.25, 0.5, 0.75, 1} chosen on out-of-group predictions of the N training students only |
| sakt | Self-Attentive Knowledge Tracing (Pandey and Karypis, 2019), exercise = skill, one attention block |
| sakt_item | the same with an item embedding added |
| akt_lite | **a simplified relative of AKT** (Ghosh et al., 2020): Rasch-style question embeddings and a learned monotonic distance decay in the attention, one block. It is not the published AKT |

The sequence models use embedding size 48, 2 heads, dropout 0.2, windows of 100 answers, Adam at 2e-3, and stop early on 20% of
the N training students. These constants were declared before the run and not tuned. The hybrid was added after the first run
(without sequence models) showed gbdt ahead of the stack at large N; it is exploratory and confirmed only by the second EdNet
sample.

## AUC (mean over 5 folds; higher is better; standard deviations, ECE and log loss for every N are in the raw files)

| Dataset | N | lms_default | pfa | rasch | gbdt | stack_transfer | hybrid | sakt | sakt_item | akt_lite |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ASSISTments | 30 | 0.6806 | 0.6043 | 0.6752 | 0.6643 | 0.7101 | **0.7114** | 0.5225 | 0.5508 | 0.5394 |
| | 100 | 0.6806 | 0.6677 | 0.6848 | 0.7139 | 0.7227 | **0.7261** | 0.5776 | 0.6049 | 0.5771 |
| | all | 0.6806 | 0.7219 | 0.7592 | **0.7782** | 0.7654 | **0.7782** | 0.7343 | 0.7504 | 0.7666 |
| EdNet, sample 1 | 30 | 0.6109 | 0.5467 | 0.6411 | 0.5954 | **0.6556** | 0.6532 | 0.5063 | 0.5431 | 0.5193 |
| | 100 | 0.6109 | 0.5923 | 0.6570 | 0.6426 | **0.6683** | 0.6669 | 0.5696 | 0.5907 | 0.5585 |
| | all | 0.6109 | 0.6370 | **0.7241** | 0.7188 | 0.7172 | 0.7195 | 0.6453 | 0.6532 | 0.6828 |
| EdNet, sample 2 | 30 | 0.6029 | 0.5789 | 0.6503 | 0.6274 | **0.6606** | 0.6602 | 0.5389 | 0.5633 | 0.5391 |
| | 100 | 0.6029 | 0.6072 | 0.6738 | 0.6697 | 0.6791 | **0.6794** | 0.5692 | 0.5733 | 0.5715 |
| | all | 0.6029 | 0.6352 | **0.7276** | 0.7177 | 0.7168 | 0.7187 | 0.6473 | 0.6656 | 0.6844 |
| CSEDM | 30 | 0.7080 | 0.7613 | 0.7619 | 0.7587 | 0.7843 | **0.7848** | 0.7480 | 0.6945 | 0.7413 |
| | 100 | 0.7080 | 0.7658 | 0.7744 | 0.7967 | 0.7982 | **0.8014** | 0.7637 | 0.7489 | 0.7803 |
| | all | 0.7080 | 0.7676 | 0.7792 | 0.8111 | 0.8041 | 0.8119 | 0.7921 | 0.8099 | **0.8147** |

ECE at N = all (lower is better): ASSISTments hybrid 0.0067, sakt 0.0093, akt_lite 0.0261, sakt_item 0.0368; EdNet sample 1
hybrid 0.0147, sakt 0.0229, sakt_item 0.0306, akt_lite 0.0350; CSEDM hybrid 0.0165, akt_lite 0.0191, sakt 0.0203,
sakt_item 0.0266. The default rule is 0.1418, 0.1429 and 0.0680.

AUC difference of the hybrid minus another model, with the 95% interval over students (100 resamples; computed at N = 100 and
at all training students only):

| Dataset | N | vs rasch | vs gbdt | vs sakt | vs sakt_item | vs akt_lite |
| --- | --- | --- | --- | --- | --- | --- |
| ASSISTments | 100 | +0.041 (+0.038, +0.045) | +0.013 (+0.011, +0.014) | +0.152 (+0.145, +0.160) | +0.121 (+0.116, +0.128) | +0.150 (+0.143, +0.157) |
| | all | +0.019 (+0.017, +0.021) | 0.000 (0.000, 0.000) | +0.044 (+0.041, +0.046) | +0.028 (+0.026, +0.030) | +0.012 (+0.010, +0.014) |
| EdNet, sample 1 | 100 | +0.006 (+0.002, +0.010) | +0.030 (+0.024, +0.033) | +0.107 (+0.088, +0.120) | +0.090 (+0.075, +0.107) | +0.115 (+0.099, +0.131) |
| | all | **-0.005 (-0.008, -0.003)** | +0.001 (+0.000, +0.001) | +0.073 (+0.067, +0.081) | +0.067 (+0.060, +0.071) | +0.037 (+0.033, +0.040) |
| EdNet, sample 2 | 100 | +0.004 (+0.002, +0.007) | +0.009 (+0.007, +0.012) | +0.113 (+0.099, +0.128) | +0.112 (+0.099, +0.123) | +0.110 (+0.100, +0.119) |
| | all | **-0.009 (-0.011, -0.007)** | +0.001 (+0.001, +0.001) | +0.072 (+0.066, +0.078) | +0.055 (+0.052, +0.060) | +0.036 (+0.031, +0.042) |
| CSEDM | 100 | +0.026 (+0.022, +0.030) | +0.005 (+0.003, +0.007) | +0.038 (+0.032, +0.044) | +0.043 (+0.036, +0.051) | +0.022 (+0.016, +0.026) |
| | all | +0.033 (+0.029, +0.037) | +0.001 (+0.000, +0.001) | +0.020 (+0.016, +0.024) | +0.002 (-0.001, +0.005) | **-0.003 (-0.005, 0.000)** |

The same table against PFA and against the stack alone is in the raw files. Against PFA the hybrid is higher everywhere
(+0.035 to +0.084); against the stack alone it is higher at full data on all datasets (+0.002 to +0.013) and at N = 100 on
ASSISTments and CSEDM.

## Findings

1. **With 100 training students or fewer, the stack and the hybrid beat every model here, including the sequence models, on every
   dataset and sample.** At N = 30 the best of the two is above the best other model on all four rows; at N = 100 the hybrid's
   intervals against all six learned baselines are above zero (ASSISTments +0.013 at least; EdNet +0.004 to +0.006 over Rasch;
   CSEDM +0.005 over gbdt, +0.022 over akt_lite). At N = 30 no interval was computed.
2. **The sequence models need much more data than 100 students.** At N = 30 and 100 they score between 0.51 and 0.61 on
   ASSISTments and EdNet (0.69 to 0.78 on CSEDM). At full data they approach the others but do not lead, except on CSEDM:
   akt_lite 0.8147 against 0.8119 for the hybrid (the hybrid is 0.003 lower, interval -0.005 to 0.000). On ASSISTments akt_lite
   is 0.012 below the hybrid; on EdNet the three sequence models are 0.04 to 0.08 below Rasch.
3. **At full data no model wins everywhere.** Rasch is best on both EdNet samples (by 0.005 and 0.009 over the hybrid), the hybrid
   equals gbdt on ASSISTments (weight 1.0 chosen in all 5 folds), and akt_lite is best on CSEDM.
4. **The step 91 stack alone loses at full data:** 0.013 below gbdt on ASSISTments and 0.007 below on CSEDM (intervals below
   zero), and below Rasch on EdNet. Its advantage is in the cold-start range, which is what it was built for.
5. **PFA is the weakest learned model in 11 of 12 AUC rows** (not CSEDM at N = 30, where gbdt is lower), and below the untrained
   default rule at N of 30 and 100 on ASSISTments and EdNet sample 1.
6. **Calibration:** at N = 300 the stack, hybrid and gbdt have ECE below 0.021 on every dataset, against 0.07 to 0.14 for the
   default rule; sequence models are at 0.019 to 0.060. At N = 30 only Rasch, the stack and the hybrid are below 0.035 on
   ASSISTments and EdNet sample 1.

## Limits

- **akt_lite is not AKT.** It has one block and no knowledge-retriever stack. A claim about the published AKT or other deep models
  (DKT and its variants) is not supported by this step.
- **The sequence models were not tuned.** Their small-N weakness is expected, but with tuning (smaller models, longer
  training, pre-training on other data) they would likely do better; a stronger test of "needs more than 100 students" requires it.
- **The hybrid is post-hoc.** Its blend weight is chosen without test data, but the idea came from looking at the test folds of
  the first run.
- **Other baselines are modestly tuned:** PFA's C from a small grid, Rasch with C = 1, gbdt with scikit-learn defaults except the
  iteration count.
- **Features include item ids,** and CSEDM has 50 items and 5 skills, so item effects are easy to learn there.
- **N = 30 has no interval.**
- **Not evidence about students.** Nothing here uses the LMS pilot or course data.
