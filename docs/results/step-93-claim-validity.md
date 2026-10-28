# Step 93: published DKT and AKT, validity checks of the research claims, re-test of the placement claim (TR-V-05, TR-M-01)

Date: 2026-10-28. Raw outputs: `docs/results/data/step-93-*.txt`. Python 3.12.10, PyTorch 2.14.1 (CPU), numpy 2.5.4, pandas 3.1.0,
scikit-learn 1.9.1, scipy 1.18.1, pykt-toolkit 0.0.38 (MIT) for the model classes. Research code only; the product is unchanged.

## Status of this document (read first)

- **Complete:** the published models on CSEDM (5 folds), the placebo check, the constants check, the training-order check, the third EdNet
  sample, the placement re-test on 5 seeds.
- **Partial, still running when this was written:** the published DKT and AKT on ASSISTments (2 folds at N of 30, 100 and 300; 1 fold with all
  training students), EdNet sample 1 (4 folds; 3 with all), EdNet sample 2 (3 folds; 2 with all), and the half-sample replications. The
  numbers below say how many folds they use. The runs write each fold's test predictions to disk, and
  `analyze_predictions.py` recomputes the tables from whatever folds exist.
- **Not re-tested:** the explanation flows (they need model-provider quota and the correctness question needs human raters, G-5), the
  textbook max-information and fixed-order placement comparisons (the report of this command does not print them), and anything about learning.

## 1. Published DKT and AKT on the same folds

Model code from pyKT (`dkt.py`, `akt.py`) with our windows, folds, early stopping and scoring (`published_models.py`). Both pass the
causality check (changing one answer changes no prediction up to and including that position). Sizes were declared before the runs and
not tuned (d = 128; AKT with 2 blocks and 8 heads). DKT has no prediction for a student's first answer; those rows get the training mean.
The other models are those of step 92 and reproduce its numbers on the CSEDM folds (default 0.7080, hybrid 0.7848 at N = 30).

Mean AUC over the folds available (folds in brackets: N = 30 and 100 / all):

| Dataset (folds) | N | Rasch | GBDT | stack | hybrid | DKT | AKT |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CSEDM (5 / 5) | 30 | 0.7619 | 0.7587 | 0.7843 | **0.7848** | 0.7736 | 0.7621 |
| | 100 | 0.7744 | 0.7967 | 0.7982 | **0.8014** | 0.7856 | 0.7768 |
| | all | 0.7792 | 0.8111 | 0.8041 | **0.8119** | 0.7952 | 0.7989 |
| ASSISTments (2 / 1) | 30 | 0.6768 | 0.6507 | 0.7108 | **0.7109** | 0.6124 | 0.6696 |
| | 100 | 0.6872 | 0.7194 | 0.7268 | **0.7301** | 0.6712 | 0.7112 |
| | all | 0.7610 | 0.7807 | 0.7684 | 0.7807 | 0.7553 | **0.7827** |
| EdNet sample 1 (4 / 3) | 30 | 0.6381 | 0.5933 | **0.6548** | 0.6527 | 0.5399 | 0.5652 |
| | 100 | 0.6539 | 0.6422 | **0.6661** | **0.6661** | 0.5719 | 0.6126 |
| | all | **0.7298** | 0.7263 | 0.7246 | 0.7270 | 0.6482 | 0.6912 |
| EdNet sample 2 (3 / 2) | 30 | 0.6538 | 0.6423 | **0.6633** | **0.6633** | 0.5748 | 0.6005 |
| | 100 | 0.6758 | 0.6724 | 0.6804 | **0.6808** | 0.6026 | 0.6365 |
| | all | **0.7304** | 0.7219 | 0.7205 | 0.7227 | 0.6537 | 0.6977 |

AUC difference of the hybrid minus the published model, 95% interval over students (on the folds above):

| Dataset | N | vs DKT | vs AKT |
| --- | --- | --- | --- |
| CSEDM | 100 | +0.016 (+0.012, +0.020) | +0.028 (+0.024, +0.033) |
| | all | +0.017 (+0.013, +0.021) | +0.013 (+0.010, +0.018) |
| ASSISTments | 30 | +0.098 (+0.088, +0.107) | +0.044 (+0.040, +0.048) |
| | 100 | +0.059 (+0.052, +0.065) | +0.021 (+0.018, +0.023) |
| EdNet sample 1 | 100 | +0.097 (+0.085, +0.108) | +0.061 (+0.048, +0.068) |
| | all | +0.077 (+0.070, +0.085) | +0.037 (+0.029, +0.044) |
| EdNet sample 2 | 100 | +0.085 (+0.070, +0.095) | +0.046 (+0.038, +0.052) |
| | all | +0.068 (+0.063, +0.075) | +0.025 (+0.021, +0.029) |

Reading: the published DKT and AKT are below the hybrid at N of 30 and 100 on every dataset, with intervals above zero. With all
training students the published AKT reaches the leaders only on ASSISTments (0.7827 against 0.7807 for the hybrid, one fold, no
interval) and is below the hybrid on CSEDM (+0.013) and on both EdNet samples. DKT is below the hybrid everywhere. The published AKT
scores lower on CSEDM with all students (0.7989) than the simplified AKT-style model of step 92 (0.8147); its larger default-sized
network is likely over-parameterised for 400 students, but this was not tested.

## 2. Validity checks of the cold-start claims

| Check | What it tests | Result | Verdict |
| --- | --- | --- | --- |
| Placebo: labels permuted across all answers, N = 100 and all, 3 folds | that no model gets information from the test labels or the future | AUC 0.498 to 0.509 for the default rule, gbdt, stack and hybrid on all three datasets | **No sign of leakage** |
| Constants: each of 5 pseudo-count constants halved and doubled, transfer weights re-learned | that the gain is not tuned through the declared constants | Gain over the default rule moves by at most 0.0013 AUC at N = 0 and N = 100 on all three datasets (declared: +0.0216/+0.0378 ASSISTments, +0.0336/+0.0687 EdNet, +0.0401/+0.0887 CSEDM at N of 0 and 100) | **Robust to the constants** |
| Training order: 4 random orders of the training students (the original and 3 new), N = 30 and 100, 5 folds | that the ranking is not an accident of which students were drawn | The stack beats the best of Rasch and gbdt in 24 of 24 cells (+0.001 to +0.035 AUC); the hybrid in 23 of 24, the exception a tie on EdNet at N = 30 (-0.0002) | **Stable ranking** |
| Third EdNet sample (new students), N = 30, 100, all, 5 folds | that the hybrid is not fitted to the first sample | Hybrid minus Rasch: +0.0082 (+0.0046, +0.0119) at N = 100 and -0.0036 (-0.0052, -0.0020) with all students; hybrid minus stack with all students +0.0015 (+0.0006, +0.0025). Same direction as samples 1 and 2 | **Replicated for EdNet** |
| Half-sample replications of ASSISTments and CSEDM (disjoint random halves of students) | that the hybrid and ranking hold on other students of the same course | Running at the time of writing; see the raw files when finished | **Open** |
| Causality unit tests of the features, the sequence models and the published models | that predictions use only earlier answers | 8 of 8 pass | **Pass** |

What these checks do not cover: other datasets; stronger tuning of the baselines; whether the ranking holds for Python learners (none of the datasets
is Python); the pilot.

## 3. Re-test of the placement claim (adaptive selection needs fewer questions)

    python -m simulation.run --students 500 --seed S     (S = 2026, the reported seed, and 3001 to 3004, new seeds)

Questions needed to reach the error that random selection reaches after 20 questions (500 simulated students, bank of 75):

| Seed | pooled estimate: adaptive needs | independent estimates: adaptive needs |
| --- | --- | --- |
| 2026 | 12 (40% fewer) | 12 |
| 3001 | 11 (45% fewer) | 5 |
| 3002 | 12 (40% fewer) | 14 |
| 3003 | 14 (30% fewer) | 1 |
| 3004 | 12 (40% fewer) | 15 |

- **The pooled result is stable** (11 to 14 questions, 30% to 45% fewer; mean 12.2) and agrees with step 88 (12.25).
- **The independent-estimate result is not.** It ranges from 1 to 15 questions, because that error curve is almost flat (0.28 to 0.25 over 20
  questions), so the crossing point jumps. The "40% fewer" figure for independent estimates should not be quoted.
- **Held-out AUC:** adaptive with the pooled estimate 0.682 to 0.708, random with the pooled estimate 0.676 to 0.699 (adaptive higher in 5 of 5 seeds,
  by 0.002 to 0.013), the ability-only 2PL baseline 0.673 to 0.695 (adaptive-pooled higher by 0.006 to 0.015). With the independent mastery update
  the AUC is 0.606 to 0.629, below the ability-only 2PL baseline by 0.05 to 0.08. If the product shows the independent estimate, that
  path predicts held-out answers worse than a one-number ability model.
- **Calibration:** the adaptive pooled estimate has a higher ECE than the random pooled one in 5 of 5 seeds (0.057 to 0.072 against 0.051 to 0.059).
- The students are synthetic and drawn from a different response model, so this tests the selector's logic, not real learners.

## 4. Claim ledger

| Claim | Evidence | Verdict |
| --- | --- | --- |
| The default rule is badly calibrated (ECE 0.14) and calibration maps repair it without losing AUC | Step 88 (not re-run); consistent with the AUC-invariance noted in the literature | Supported on two datasets |
| A stack started from other datasets' weights beats the default rule with no course data | Table 1 of the paper (+0.022 to +0.040 AUC, intervals above zero); placebo-clean; robust to constants | **Supported** (CSEDM ECE slightly worse) |
| With 100 students or fewer the stack or hybrid beats every learned model, published DKT and AKT included | Complete on CSEDM; in the folds finished on ASSISTments and EdNet; stable across 4 orders; replicated on 3 EdNet samples | **Supported; final folds pending** |
| Sequence models need far more than 100 students | SAKT, SAKT with items, AKT-style, published DKT and AKT all below the hybrid at N of 30 and 100 | **Supported**; the published AKT catches up only with all of ASSISTments |
| The hybrid improves on the stack alone at large N | +0.002 to +0.013 with all students; replicated on EdNet samples 2 and 3 | Supported, post-hoc, ties at N = 100 on EdNet |
| No model wins everywhere with all students | Rasch on EdNet, gbdt or hybrid on ASSISTments and CSEDM, AKT-style on CSEDM | Supported |
| Adaptive placement needs about 40% fewer questions | Pooled: 30% to 45% on five seeds. Independent: 1 to 15 questions | **Supported for the pooled estimate only** |
| Adaptive selection predicts held-out answers better | +0.002 to +0.013 AUC over random (pooled), but worse calibration | Small and consistent in sign |
| The verified explanation flow is better than a plain model | Leak rates (step 88) not re-run; correctness unrated by humans | **Not re-tested; open (G-5)** |
| The system improves learning | No evidence | **Open (G-6)** |

## 5. Threats this step does not remove

The three datasets are not Python courses; the published models were run at declared, untuned sizes and (on ASSISTments and EdNet) on part of the
folds so far; the hybrid is post-hoc; many comparisons were made and no correction for multiple comparisons was applied; the placement result comes from a
simulator written for this project.
