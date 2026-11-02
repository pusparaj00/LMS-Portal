# Step 95: controls and statistics for the cold-start paper (TR-V-05)

Run on 2026-11-01. Raw outputs: `docs/results/data/step-95-*.txt`. Code: `research/kt_comparison/baselines_plus.py` (new `--controls`,
N = 30 intervals, one shared student resample per draw) and `test_cold_start_plus.py`. Python 3.12 environment of step 92.

    python research/kt_comparison/baselines_plus.py --controls --folds 5 --bootstrap 1000 --levels 30,100,all
    python research/kt_comparison/baselines_plus.py --targets ednet --ednet-seed 3 --controls --folds 5 --bootstrap 1000 --levels 30,100,all
    for s in 1..9: python research/kt_comparison/baselines_plus.py --skip pfa,rasch --folds 5 --bootstrap 10 --levels 30,100 --order-seed $s
    python research/kt_comparison/test_cold_start_plus.py

Columns below: `stack` is the transfer stack, `flat` the same six features with prior weights 0 (no transfer), `hybrid` the post-hoc blend.
Bootstrap: 1,000 resamples of whole test students, the same resample for every model, so differences are paired. This differs from steps
91 to 93, where each pair had its own 100 resamples; the point estimates are unchanged.

## 1. All models, N = 30, 100, all (mean AUC over 5 folds, order seed 0)

| Dataset | N | default | PFA | Rasch | GBDT | stack | hybrid | flat |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ASSISTments | 30 | 0.6806 | 0.6043 | 0.6752 | 0.6643 | 0.7101 | **0.7114** | 0.7080 |
| | 100 | 0.6806 | 0.6677 | 0.6848 | 0.7139 | 0.7227 | **0.7261** | 0.7223 |
| | all | 0.6806 | 0.7219 | 0.7592 | **0.7782** | 0.7654 | **0.7782** | 0.7654 |
| EdNet 1 | 30 | 0.6109 | 0.5467 | 0.6411 | 0.5954 | **0.6556** | 0.6532 | 0.6511 |
| | 100 | 0.6109 | 0.5923 | 0.6570 | 0.6426 | **0.6683** | 0.6669 | 0.6674 |
| | all | 0.6109 | 0.6370 | **0.7241** | 0.7188 | 0.7172 | 0.7195 | 0.7172 |
| CSEDM | 30 | 0.7080 | 0.7613 | 0.7619 | 0.7587 | 0.7843 | **0.7848** | 0.7812 |
| | 100 | 0.7080 | 0.7658 | 0.7744 | 0.7967 | 0.7982 | **0.8014** | 0.7981 |
| | all | 0.7080 | 0.7676 | 0.7792 | 0.8111 | 0.8041 | **0.8119** | 0.8040 |

The sequence models of step 92 and the published models of step 93 are not repeated here (see those files). On CSEDM with all students
`akt_lite` scores 0.8147, above the hybrid, so no model is bold-faced as best there in the paper.

ECE and log loss (same runs; `platt` is the default rule with a Platt map fitted on the other datasets):

| Dataset | N | ECE default | PFA | Rasch | GBDT | stack | hybrid | platt | log loss default / stack / hybrid |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ASSISTments | 30 | 0.1418 | 0.0525 | 0.0142 | 0.0550 | 0.0211 | 0.0222 | 0.1161 | 0.666 / 0.576 / 0.575 |
| | 100 | 0.1418 | 0.0337 | 0.0134 | 0.0206 | 0.0161 | 0.0135 | 0.1161 | 0.666 / 0.567 / 0.564 |
| | all | 0.1418 | 0.0113 | 0.0076 | 0.0067 | 0.0092 | 0.0067 | 0.1161 | 0.666 / 0.535 / 0.522 |
| EdNet 1 | 30 | 0.1429 | 0.0865 | 0.0181 | 0.0848 | 0.0296 | 0.0320 | 0.0816 | 0.704 / 0.602 / 0.604 |
| | 100 | 0.1429 | 0.0552 | 0.0200 | 0.0424 | 0.0148 | 0.0202 | 0.0816 | 0.704 / 0.593 / 0.594 |
| | all | 0.1429 | 0.0254 | 0.0151 | 0.0149 | 0.0178 | 0.0147 | 0.0816 | 0.704 / 0.568 / 0.565 |
| CSEDM | 30 | 0.0680 | 0.0341 | 0.0356 | 0.0438 | 0.0230 | 0.0240 | 0.2156 | 0.585 / 0.518 / 0.516 |
| | 100 | 0.0680 | 0.0323 | 0.0291 | 0.0225 | 0.0239 | 0.0191 | 0.2156 | 0.585 / 0.506 / 0.503 |
| | all | 0.0680 | 0.0299 | 0.0274 | 0.0152 | 0.0206 | 0.0165 | 0.2156 | 0.585 / 0.501 / 0.492 |

## 2. Intervals (hybrid or stack minus another model, AUC, 95% over students, 1,000 resamples)

Stack minus other model:

| Dataset | N | PFA | Rasch | GBDT | flat |
| --- | --- | --- | --- | --- | --- |
| ASSISTments | 30 | +0.108 (+0.101, +0.117) | +0.034 (+0.031, +0.037) | +0.047 (+0.045, +0.050) | +0.0026 (+0.0019, +0.0033) |
| | 100 | +0.056 (+0.050, +0.061) | +0.037 (+0.035, +0.041) | +0.009 (+0.007, +0.011) | +0.0006 (+0.0002, +0.0011) |
| | all | +0.044 (+0.041, +0.046) | +0.006 (+0.005, +0.008) | −0.013 (−0.014, −0.012) | 0.0000 |
| EdNet 1 | 30 | +0.116 (+0.100, +0.130) | +0.009 (+0.006, +0.013) | +0.067 (+0.045, +0.096) | +0.0031 (−0.0002, +0.0062) |
| | 100 | +0.085 (+0.070, +0.098) | +0.009 (+0.005, +0.012) | +0.032 (+0.025, +0.038) | +0.0012 (+0.0004, +0.0023) |
| | all | +0.080 (+0.073, +0.089) | −0.008 (−0.011, −0.005) | −0.002 (−0.003, −0.001) | 0.0000 |
| CSEDM | 30 | +0.023 (+0.018, +0.028) | +0.022 (+0.018, +0.027) | +0.025 (+0.020, +0.029) | +0.0033 (+0.0026, +0.0041) |
| | 100 | +0.032 (+0.027, +0.036) | +0.024 (+0.019, +0.028) | +0.002 (−0.001, +0.005) | +0.0003 (0.0000, +0.0006) |
| | all | +0.036 (+0.032, +0.041) | +0.025 (+0.020, +0.029) | −0.007 (−0.009, −0.005) | 0.0000 |

Hybrid minus other model, N = 30 and 100 only (all-student rows are in `data/step-95-controls-main.txt`):

| Dataset | N | Rasch | GBDT | stack |
| --- | --- | --- | --- | --- |
| ASSISTments | 30 | +0.035 (+0.032, +0.038) | +0.048 (+0.046, +0.051) | +0.0008 (+0.0004, +0.0013) |
| | 100 | +0.041 (+0.038, +0.044) | +0.013 (+0.011, +0.014) | +0.0035 (+0.0029, +0.0040) |
| EdNet 1 | 30 | +0.004 (−0.000, +0.011) | +0.062 (+0.043, +0.089) | −0.0043 (−0.0083, −0.0012) |
| | 100 | +0.006 (+0.002, +0.010) | +0.030 (+0.024, +0.035) | −0.0024 (−0.0039, −0.0010) |
| CSEDM | 30 | +0.023 (+0.018, +0.028) | +0.026 (+0.022, +0.029) | +0.0007 (−0.0002, +0.0017) |
| | 100 | +0.026 (+0.022, +0.031) | +0.005 (+0.003, +0.007) | +0.0028 (+0.0017, +0.0040) |

## 3. What the controls show

- **Transfer adds little once a few students exist.** Stack minus no-transfer stack is at most +0.0033 AUC at N = 30 (interval above zero on
  ASSISTments and CSEDM, not on EdNet 1), at most +0.0012 at N = 100, and 0.0000 with all students. On the new EdNet sample (section 5) the
  flat stack scored 0.6226 at N = 30 with a fold SD of 0.063, against 0.6530 with transfer, so transfer also guards against a bad draw at N = 30.
  The transfer-specific result is the N = 0 case, where the flat stack has no weights to use.
- **Calibration does not transfer through a Platt map.** The default rule with a Platt map fitted on the other datasets keeps ECE 0.116
  (ASSISTments) and 0.082 (EdNet) and gets worse on CSEDM (0.216 against 0.068). Its AUC equals the default rule's, because the map is monotone.
  The stack with transfer weights at N = 0 had ECE 0.023, 0.051 and 0.077 in step 91 (Table IV).
- **Leave-one-feature-out** (stack minus the stack without one feature, mean AUC over 5 folds, all students; the prior is refitted on the other
  datasets without that feature):

| Feature left out | ASSISTments | EdNet 1 | CSEDM |
| --- | --- | --- | --- |
| rule prediction | −0.0023 | −0.0018 | −0.0028 |
| student accuracy | −0.0121 | −0.0101 | −0.0058 |
| log count on skill | −0.0020 | +0.0002 | −0.0006 |
| last five answers | −0.0030 | −0.0026 | −0.0083 |
| skill effect | −0.0163 | −0.0066 | −0.0024 |
| item effect | −0.0365 | −0.0600 | −0.0351 |

  With no course data (N = 0, AUC over all answers, nothing fitted on the dataset; stack 0.7027, 0.6492, 0.7491) leaving out the rule prediction
  costs 0.0111, 0.0058 and 0.0027; leaving out the last five answers costs 0.0042, 0.0064 and 0.0141; the skill and item effects are
  neutral at N = 0, so removing them changes only the refitted prior (−0.0031 to +0.0023). The item effect carries most of the AUC with course data.
  The paper's earlier "0.005 to 0.013 with no data" for the rule prediction is replaced by these measured values (0.003 to 0.011).

## 4. Draws of the N training students (nine extra order seeds, 1 to 9; GBDT, stack, hybrid, default rule only)

N = 30 and 100, 5 folds each. Across the nine draws the hybrid's mean AUC has a standard deviation of 0.0023 (ASSISTments, N = 30), 0.0013
(N = 100), 0.0016 and 0.0009 (CSEDM), 0.0046 and 0.0009 (EdNet 1). The hybrid stayed above the better of GBDT and the default rule in all
nine draws in all six cells (smallest margin +0.0049, CSEDM N = 100; mean margins +0.0066 to +0.0395). The stack alone was also above both in all nine
(smallest +0.0011, CSEDM N = 100). PFA and Rasch were left out of these runs to save time, so this does not repeat the comparison with them.
The N = 30 below N = 10 pattern for per-skill fitting noted in the audit was not re-run here.

## 5. Frozen test on a new EdNet sample (order and sample not used in design: `--ednet-seed 3`)

Samples 0 to 2 were used before this step. Seed 3 is a new 1,500-student sample, 5 folds, run on 2026-11-01 with the hybrid unchanged.

| N | default | PFA | Rasch | GBDT | stack | hybrid | flat |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 30 | 0.5966 | 0.5688 | 0.6419 | 0.5947 | **0.6530** | 0.6495 | 0.6226 |
| 100 | 0.5966 | 0.6004 | 0.6635 | 0.6539 | 0.6707 | **0.6710** | 0.6706 |
| all | 0.5966 | 0.6330 | **0.7217** | 0.7137 | 0.7142 | 0.7152 | 0.7142 |

Hybrid minus stack: −0.0029 (−0.0051, −0.0010) at N = 30; +0.0003 (−0.0004, +0.0009) at N = 100; +0.0011 (+0.0005, +0.0017) with all students.
Hybrid minus Rasch: +0.0065 (+0.0031, +0.0104), +0.0074 (+0.0045, +0.0107), −0.0070 (−0.0088, −0.0050). Hybrid minus GBDT: +0.058, +0.018, +0.0015.
On fresh data the hybrid beats Rasch, GBDT and PFA at N of 30 and 100 but is not better than the stack, which is above it at N = 30 and tied at 100.
At N = 0 the stack scores 0.6384 against 0.5968 for the default rule. No second ASSISTments release or Python course is available here, so
ASSISTments and CSEDM still have no sample untouched by the design of the hybrid.

## 6. Truncation test (audit item 5)

Two new unit tests in `test_cold_start_plus.py`: all answers after position 7 of one test student are flipped; the stack's causal features, the
Rasch prediction and the PFA prediction at positions up to 7 do not change, and the course features of a test row use training answers only.
All 12 checks pass (`python research/kt_comparison/test_cold_start_plus.py`, 2026-11-01). The sequence and published models already had
the same test. Together with the label-permutation run of step 93 this covers both the target and the future-answer leaks.

## Limits

- Order seeds in section 4 vary the choice of N students; they do not vary neural-model seeds.
- The leave-one-feature-out stacks use the transfer prior refitted without the feature, with the same ridge choice by cross-validation.
- The no-transfer stack uses prior weights 0, so with N = 0 it predicts 0.5 for every answer and has no N = 0 row.
- The hybrid stays post-hoc; section 5 does not make it a pre-registered result.

## 7. Items checked against the audit that needed no new run

- **Published DKT and AKT, all five folds.** Recomputed from the saved test predictions (`analyze_predictions.py` inputs, 2026-11-01): the
  Table V values for DKT and AKT at N = 30, 100 and all are reproduced on ASSISTments, EdNet 1, EdNet 2 and CSEDM, each with 5 folds. Step 93
  listed them as partial; the later runs finished. ASSISTments with all students: AKT 0.77816 and GBDT 0.77823 (different predictions, per-fold
  AUC differ, prediction correlation 0.86 to 0.89), so the equal 0.7782 is a four-decimal coincidence and not a transcription error.
- **ECE with all students** (5 folds): published AKT 0.0302 (ASSISTments), 0.0350 and 0.0326 (EdNet 1 and 2), 0.0231 (CSEDM); Rasch 0.0274
  on CSEDM and PFA 0.0299, so AKT is not the worst on CSEDM.
- **Default rule AUC 0.6811 against 0.6806 (ASSISTments) and 0.6155 against 0.6109 (EdNet)**: pooled test answers (step 87/88) against the
  mean of fold AUCs (step 91 onward).
- **Constant 50** is the pseudo-count that shrinks the N-student overall mean to 0.55 (`M_GLOBAL` in `cold_start_plus.py`).

## 8. Not done

- **Tuned DKT and AKT on EdNet and CSEDM.** `step-94-tuned-neural.txt` holds ASSISTments at N = 30 and 100 with 5 folds (tuned AKT 0.6786 and
  0.7085, untuned 0.6483 and 0.7094; tuned DKT 0.6037 and 0.6425, untuned 0.5904 and 0.6403; stack 0.7101 and 0.7227) and an incomplete EdNet
  run. A completion run (`--targets ednet,csedm --published --neural-tuned dkt,akt --skip pfa,rasch --levels 30,100`) took about 20 minutes for
  one fold at N = 30 on EdNet, so it was stopped after fold 1 and its partial output deleted. It needs several hours.
- **Pretrained or fine-tuned comparators, PTADisc, a second ASSISTments release, neural-model seeds.**
