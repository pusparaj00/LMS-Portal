# Step 92: stronger baselines for the cold-start stack (TR-V-05)

Run on 2026-10-28 (main run started 09:17 UTC). Raw output: `docs/results/data/step-92-baselines-main.txt` and
`docs/results/data/step-92-baselines-ednet-replication.txt`.

    python research/kt_comparison/baselines_plus.py --folds 5 --bootstrap 100
    python research/kt_comparison/baselines_plus.py --targets ednet --ednet-seed 1 --folds 5 --bootstrap 100

Same folds, datasets and training sizes N as step 91 (Python 3.15.0, numpy 2.5.4, pandas 3.1.0, scikit-learn 1.9.1, scipy 1.18.1).
Research code only; the product is unchanged.

## Models

| Model | Description |
| --- | --- |
| lms_default | the LMS mastery rule with its default numbers; no data |
| pfa | Performance Factors Analysis: logistic regression on skill indicators and, per skill, the log of the student's earlier successes and failures on it; C chosen on a held-out fifth of the N students |
| rasch | one-parameter item-response model (student and item indicators, L2 logistic regression, C = 1); a test student's ability is re-estimated after every answer from their own earlier answers only |
| gbdt | scikit-learn HistGradientBoosting on the six features of the stack |
| stack_transfer | the step 91 stack, started from weights fitted on the other datasets |
| hybrid | **post-hoc**: a blend of the stack's and gbdt's logits, weight in {0, 0.25, 0.5, 0.75, 1} chosen on out-of-group predictions of the N training students only |

The hybrid was added after the first run (below) showed gbdt ahead of the stack at large N. It is therefore exploratory. It is
confirmed only by the second EdNet sample; ASSISTments and CSEDM have no independent sample here. SAKT and AKT were **not
run**: PyTorch has no wheel for Python 3.15, the only Python installed. Published sequence-model scores are not comparable
to these numbers.

## AUC (mean over 5 folds; higher is better; full tables with standard deviations, ECE and log loss are in the raw files)

| Dataset | N | lms_default | pfa | rasch | gbdt | stack_transfer | hybrid |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ASSISTments | 30 | 0.6806 | 0.6043 | 0.6752 | 0.6643 | 0.7101 | **0.7114** |
| | 100 | 0.6806 | 0.6677 | 0.6848 | 0.7139 | 0.7227 | **0.7261** |
| | all | 0.6806 | 0.7219 | 0.7592 | **0.7782** | 0.7654 | **0.7782** |
| EdNet, sample 1 | 30 | 0.6109 | 0.5467 | 0.6411 | 0.5954 | **0.6556** | 0.6532 |
| | 100 | 0.6109 | 0.5923 | 0.6570 | 0.6426 | **0.6683** | 0.6669 |
| | all | 0.6109 | 0.6370 | **0.7241** | 0.7188 | 0.7172 | 0.7195 |
| EdNet, sample 2 (replication) | 30 | 0.6029 | 0.5789 | 0.6503 | 0.6274 | **0.6606** | 0.6602 |
| | 100 | 0.6029 | 0.6072 | 0.6738 | 0.6697 | 0.6791 | **0.6794** |
| | all | 0.6029 | 0.6352 | **0.7276** | 0.7177 | 0.7168 | 0.7187 |
| CSEDM | 30 | 0.7080 | 0.7613 | 0.7619 | 0.7587 | 0.7843 | **0.7848** |
| | 100 | 0.7080 | 0.7658 | 0.7744 | 0.7967 | 0.7982 | **0.8014** |
| | all | 0.7080 | 0.7676 | 0.7792 | 0.8111 | 0.8041 | **0.8119** |

ECE at N = all (lower is better): ASSISTments pfa 0.0113, rasch 0.0076, gbdt 0.0067, stack 0.0092, hybrid 0.0067; EdNet sample 1
pfa 0.0254, rasch 0.0151, gbdt 0.0149, stack 0.0178, hybrid 0.0147; CSEDM pfa 0.0299, rasch 0.0274, gbdt 0.0152, stack 0.0206,
hybrid 0.0165.

AUC difference of the hybrid minus another model, 95% interval over students (100 resamples):

| Dataset | N | vs pfa | vs rasch | vs gbdt | vs stack_transfer |
| --- | --- | --- | --- | --- | --- |
| ASSISTments | 100 | +0.059 (+0.054, +0.064) | +0.041 (+0.038, +0.044) | +0.013 (+0.011, +0.014) | +0.004 (+0.003, +0.004) |
| | all | +0.056 (+0.054, +0.059) | +0.019 (+0.017, +0.021) | 0.000 (0.000, 0.000) | +0.013 (+0.012, +0.014) |
| EdNet, sample 1 | 100 | +0.083 (+0.065, +0.095) | +0.006 (+0.002, +0.011) | +0.030 (+0.025, +0.035) | -0.002 (-0.004, -0.001) |
| | all | +0.083 (+0.076, +0.092) | **-0.005 (-0.009, -0.003)** | +0.001 (+0.000, +0.001) | +0.002 (+0.002, +0.003) |
| EdNet, sample 2 | 100 | +0.077 (+0.066, +0.085) | +0.004 (+0.002, +0.007) | +0.009 (+0.007, +0.012) | 0.000 (0.000, +0.001) |
| | all | +0.084 (+0.079, +0.089) | **-0.009 (-0.011, -0.007)** | +0.001 (+0.001, +0.002) | +0.002 (+0.001, +0.003) |
| CSEDM | 100 | +0.035 (+0.031, +0.039) | +0.026 (+0.023, +0.030) | +0.005 (+0.003, +0.006) | +0.003 (+0.002, +0.004) |
| | all | +0.044 (+0.039, +0.049) | +0.033 (+0.028, +0.037) | +0.001 (+0.000, +0.001) | +0.008 (+0.006, +0.010) |

## Findings

1. **With few students the stack and the hybrid lead every baseline on all datasets.** At N = 30 and N = 100 the best of the two
   exceeds PFA, Rasch and gradient boosting on ASSISTments, both EdNet samples and CSEDM. At N = 100 the hybrid's lead over the
   best baseline is +0.013 (ASSISTments, gbdt), +0.004 to +0.006 (EdNet, Rasch) and +0.005 (CSEDM, gbdt), each with an interval
   above zero. At N = 30 no interval was computed.
2. **At full data no model wins everywhere.** The Rasch model with online ability is the best on both EdNet samples (by
   0.005 and 0.009 AUC over the hybrid). Gradient boosting and the hybrid are best on ASSISTments (hybrid equals gbdt, the
   cross-validation chose weight 1.0) and on CSEDM, where the hybrid is 0.0007 above gbdt.
3. **The first run was a negative result for the stack alone:** at full data it was 0.013 below gbdt on ASSISTments, 0.007
   below on CSEDM (intervals below zero), and below Rasch on EdNet (-0.008 and -0.011). Its advantage is in the cold-start range.
4. **PFA is the weakest learned model in 11 of the 12 AUC rows** (the exception is CSEDM at N = 30, where gbdt is lower). At
   N = 30 and 100 it is below the untrained default rule on ASSISTments and on EdNet sample 1. It is the baseline with the
   least information (no item, no student ability).
5. **Calibration:** at N = 300 the stack, the hybrid and gbdt all have ECE below 0.021 on every dataset, against 0.07 to 0.14
   for the default rule; PFA is at 0.023 to 0.033. At N = 30 only Rasch, the stack and the hybrid are below 0.035 on
   ASSISTments and EdNet sample 1.
6. **Where the hybrid improves on the stack alone:** the interval is above zero at full data on all datasets (+0.002 to
   +0.013), and at N = 100 on ASSISTments and CSEDM. It is slightly lower at N = 100 on EdNet sample 1 (-0.002).

## Limits

- **No sequence model.** SAKT or AKT would need another Python version with PyTorch, which has not been installed. Until it is
  run, no claim against deep knowledge tracing should be made.
- **Hybrid is post-hoc.** Its blend weight is chosen without test data, but the idea came from looking at the test folds of the
  first run.
- **The baselines' settings are modest.** PFA's C came from a small grid, Rasch used C = 1 without tuning, and gbdt used
  scikit-learn defaults except the declared iteration count; stronger tuning could shift the large-N comparisons.
- **Features include item ids.** Where items are few (CSEDM, 50 items) item effects are easy to learn; the advantage of any model
  using them is larger there.
- **N = 30 has no interval** (only N = 100 and all were bootstrapped).
- **Not evidence about students.** Nothing here uses the LMS pilot or course data.
