# Step 91: cold start with a transfer-initialised stack (TR-M-01, TR-V-05)

Run on 2026-10-28 (started 08:54 UTC). Raw output, including every fold: `docs/results/data/step-91-cold-start-plus.txt`.

    python research/kt_comparison/cold_start_plus.py --folds 5 --bootstrap 100

Python 3.15.0, numpy 2.5.4, pandas 3.1.0, scikit-learn 1.9.1, scipy 1.18.1, in a virtual environment outside the project.
Checks of the stack's core functions: `python research/kt_comparison/test_cold_start_plus.py`, 5 of 5 passed. Research code
only; the product is unchanged.

## What was compared

Next-answer prediction from earlier answers, 5 folds split by student, N training students used for fitting (the same
setup as step 87). Datasets: ASSISTments 2009 skill-builder (283,105 answers, 4,163 students), an EdNet KT1 sample (175,088
answers, 1,500 students) and CSEDM, Java programming, first run of each student on each problem, one assignment as one skill
(24,032 answers, 506 students). Models:

| Model | What it uses |
| --- | --- |
| lms_default | the LMS mastery rule with its default numbers; no data |
| item_mean | item mean of the N students, shrunk to the skill mean, then to the overall mean |
| stack_plain | logistic stack of six features (below), ridge-pulled toward "the LMS default alone" |
| stack_transfer | the same stack, ridge-pulled toward weights fitted on the other two datasets; needs no course data |
| stack_no_lms | ablation: stack_transfer without the LMS rule's feature |

Features: the LMS rule's prediction, the student's smoothed accuracy over all skills so far, the count of the student's
earlier answers on the skill, the student's last five answers, a skill effect and an item effect (both from the N students).
The ridge strength is chosen by cross-validation inside the N students; keeping the prior weights is one of the choices.
Constants (pseudo-counts 3, 2, 50, 20, 10) were declared before the run and not tuned.

## Rule set before the run, and the outcome

1. On every dataset, at every N: AUC and ECE of stack_transfer never worse than lms_default. **AUC: met in all 20 cells (7 training
   sizes on ASSISTments and EdNet, 6 on CSEDM). ECE: not met in 1 of 20 cells** (CSEDM, N = 0: 0.0769 against 0.0680).
2. At N of 100 or more: AUC higher than lms_default with a bootstrap lower bound above zero. **Met on all three datasets.**

So the rule is met except for one ECE cell. It is reported as it came out.

## Results (mean over 5 folds; full tables with every N, log loss and standard deviations are in the raw file)

AUC, higher is better:

| N training students | ASSIST default | ASSIST stack_transfer | EdNet default | EdNet stack_transfer | CSEDM default | CSEDM stack_transfer |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 0.6806 | 0.7022 | 0.6109 | 0.6434 | 0.7080 | 0.7483 |
| 30 | 0.6806 | 0.7101 | 0.6109 | 0.6556 | 0.7080 | 0.7843 |
| 100 | 0.6806 | 0.7227 | 0.6109 | 0.6683 | 0.7080 | 0.7982 |
| all | 0.6806 | 0.7654 | 0.6109 | 0.7172 | 0.7080 | 0.8041 |

ECE, lower is better:

| N | ASSIST default | ASSIST stack_transfer | EdNet default | EdNet stack_transfer | CSEDM default | CSEDM stack_transfer |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 0.1418 | 0.0228 | 0.1429 | 0.0508 | 0.0680 | 0.0769 |
| 30 | 0.1418 | 0.0211 | 0.1429 | 0.0296 | 0.0680 | 0.0230 |
| 100 | 0.1418 | 0.0161 | 0.1429 | 0.0148 | 0.0680 | 0.0239 |
| all | 0.1418 | 0.0092 | 0.1429 | 0.0178 | 0.0680 | 0.0206 |

AUC difference stack_transfer minus lms_default, 95% interval from 100 student bootstrap resamples:

| N | ASSIST | EdNet | CSEDM |
| --- | --- | --- | --- |
| 0 | +0.0216 (+0.0194 to +0.0239) | +0.0337 (+0.0289 to +0.0391) | +0.0403 (+0.0335 to +0.0456) |
| 30 | +0.0286 (+0.0268 to +0.0303) | +0.0422 (+0.0340 to +0.0529) | +0.0749 (+0.0679 to +0.0832) |
| 100 | +0.0417 (+0.0394 to +0.0441) | +0.0571 (+0.0490 to +0.0670) | +0.0890 (+0.0803 to +0.0962) |
| all | +0.0847 (+0.0821 to +0.0870) | +0.1043 (+0.0917 to +0.1173) | +0.0953 (+0.0867 to +0.1029) |

## Findings

1. **Without any course data the transferred weights beat the LMS defaults.** At N = 0, AUC is higher by 0.022, 0.034 and
   0.040, with intervals that exclude zero, and ECE falls from 0.142 to 0.023 on ASSISTments and from 0.143 to 0.051 on EdNet.
   On CSEDM, ECE is slightly worse (0.077 against 0.068), the one failure of the rule.
2. **The earlier problem with small N is gone.** Step 87 found that per-skill fitting scored 0.669 and 0.660 at 10 and 30
   students on ASSISTments, below the 0.681 default. The stack is above the default at every N on every dataset, because it
   starts from the transferred weights and the cross-validation can keep them.
3. **Transfer matters mainly below about 30 students.** Against stack_plain, stack_transfer gains +0.022 to +0.040 AUC at
   N = 0 and +0.003 to +0.005 at N = 30; from N = 100 the two are within 0.0011.
4. **Most of the late gain comes from the added features, not from the LMS rule.** Without the LMS feature, AUC drops by
   0.002 to 0.003 at N = all and by 0.005 to 0.013 at N = 0. The student's cross-skill accuracy and the item effect carry the
   rest, which is what item-based and student-ability models already use.
5. **A student's very first answer is not helped.** At N = all the stack scores 0.655 on ASSISTments against 0.664 for
   item_mean (EdNet 0.607 against 0.633; CSEDM 0.491 against 0.486), because a new student has no history. From the second
   answer on the stack is better than both baselines on all three datasets, except EdNet answers 3 to 5 (0.649 against 0.652).

## Limits and what this does not show

- **Not a comparison with published knowledge-tracing models.** The stack uses item ids and cross-skill student accuracy,
  which BKT does not, so its 0.765 on ASSISTments is not comparable with the BKT range (0.648 to 0.73) or with published
  DKT and AKT figures, whose splits and filters differ. The fair next step is baselines with the same inputs: PFA,
  an item-response (Rasch) model, and a sequence model such as SAKT or AKT, evaluated on the same folds.
- **The ideas are known.** Ridge toward a prior, logistic stacking and item and student effects are standard. What this step
  adds is the cold-start protocol (a fixed number of training students, no test data used for fitting), the transfer
  initialisation from other datasets, and the calibration results. A paper would need to say so and cite the related work.
- **Transfer is shown across three datasets only.** CSEDM is Java, one assignment is one skill, and it has 506 students and
  5 skills; it differs from the other two in domain, so the CSEDM numbers say least about the LMS's Python course.
- **The LMS's own fitted course data is not used.** Nothing here has been run on the live course or pilot data.
- **One run per fold.** The student ordering inside each fold uses one seed; the bootstrap covers test students, not the
  choice of training students.
- **A product change is not made.** Using the stack in the interface would need its own step (TR-M-01 calibration decision).
