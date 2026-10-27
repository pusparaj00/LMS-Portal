# Step 87: research baselines for the verified flow and the mastery rule (TR-L-04, TR-V-03, TR-M-01)

Date: 2026-10-27. Raw outputs: `docs/results/data/step-87-*.txt`. Nothing here is a learning or human-rated result; every
number is a machine measurement on the datasets named, from one run unless stated.

## 1. Verified flow against a plain call and a hint-only call (TR-L-04, TR-V-03)

    docker exec lmssim-api-1 python -m evaluation.baselines

28 failed submissions (the `explain_rate` set), provider chain `gemini_pro` then groq, mistral, openai, local, one reply per
flow each. Provider errors left 22 plain and 26 verified replies (hint-only 28).

| Flow | Replies | Shows solution code | Repeats hidden test data |
| --- | --- | --- | --- |
| plain model | 22 | 19 (86%) | 2 (9%) |
| hint-only prompt | 28 | 1 (4%) | 1 (4%) |
| verified flow, first attempt, before the checks | 26 | 0 (0%) | 0 (0%) |

Of 26 verified-flow first attempts, 21 passed every static check. 24 gave a worked example, and in 10 of them the predicted
output was false when run in the sandbox. Checks that rejected a first attempt: `quoted_code_is_theirs` x2, `json_valid` x2,
`sources_real` x1. The plain prompt does not tell the model to withhold code, so the hint-only row is the fair guardrail
baseline. Correctness and helpfulness are not measured (G-5 needs human raters). Earlier the same day `explain_rate`
verified 24 of 28 (86%); the four fallbacks were three `no_hidden_test_leak` (the model chose a hidden test input, for
example `Racecar` and `1900`, as its worked example) and one `quoted_code_is_theirs`.

## 2. Mastery rule as a next-answer predictor (TR-M-01)

`research/kt_comparison/compare.py` calls `app.mastery.core.bayes_update` with the LMS defaults (prior 0.5, slip 0.10,
guess 0.20, no learning step). Each model predicts P(correct) for the next answer on a skill from that student's earlier
answers; students are split into folds (no test student is seen while fitting); metric AUC over all test predictions.

ASSISTments 2009 skill-builder, corrected file (283,105 answers with a skill, 4,163 students, 149 skills), 5 folds:

| Model | Mean AUC | Std over folds |
| --- | --- | --- |
| global mean (constant) | 0.5000 | 0.0000 |
| per-skill mean | 0.6284 | 0.0066 |
| LMS rule, fixed defaults | 0.6806 | 0.0079 |
| LMS rule, prior/slip/guess fitted over all skills, no learning step | 0.6717 | 0.0057 |
| LMS rule, same fitted, plus a learning step | 0.6834 | 0.0095 |
| LMS rule, numbers fitted per skill (with learning step) | 0.7188 | 0.0078 |
| pyBKT, one standard BKT model per skill | 0.7195 | 0.0083 |

EdNet-KT1, random sample of 1,500 students (175,088 answers, 141 skills; skill = first tag of the question), 5 folds:

| Model | Mean AUC | Std over folds |
| --- | --- | --- |
| global mean (constant) | 0.5000 | 0.0000 |
| per-skill mean | 0.5888 | 0.0103 |
| LMS rule, fixed defaults | 0.6109 | 0.0258 |
| pyBKT, one standard BKT model per skill | 0.6305 | 0.0182 |
| LMS rule, numbers fitted per skill (with learning step) | 0.6308 | 0.0191 |

Reading: the fixed rule beats the simple baselines on both sets; fitting one set of numbers for all skills does not help;
fitting per skill closes the gap to pyBKT (a difference of 0.0007 and 0.0003, far inside the fold spread). The gap to
fitted BKT therefore comes from per-skill parameters, which need data from the course.

## 3. Cold start and calibration

`research/kt_comparison/cold_start.py`, 3 folds, the first N of the shuffled training students used for fitting:

| Training students | ASSIST: LMS default | per-skill mean | LMS fitted | EdNet: LMS default | per-skill mean | LMS fitted |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 0.6810 | 0.5000 | 0.6810 | 0.6146 | 0.5000 | 0.6146 |
| 10 | 0.6810 | 0.5473 | 0.6690 | 0.6146 | 0.5193 | 0.6107 |
| 30 | 0.6810 | 0.5547 | 0.6600 | 0.6146 | 0.5462 | 0.6058 |
| 100 | 0.6810 | 0.5899 | 0.6813 | 0.6146 | 0.5668 | 0.6130 |
| 300 | 0.6810 | 0.6121 | 0.7032 | 0.6146 | 0.5771 | 0.6221 |
| all (EdNet: about 1,000 per fold) | 0.6810 | 0.6283 | 0.7195 | 0.6146 | 0.5862 | 0.6306 |

Fitting helps only from about 100 to 300 students; with fewer it is no better, and sometimes worse, than the defaults.

Calibration of the next-answer predictions (ECE with 10 bins; lower is better; the constant 0.5 has log loss 0.6931):

| | ASSIST ECE | ASSIST log loss | EdNet ECE | EdNet log loss |
| --- | --- | --- | --- | --- |
| LMS default | 0.1418 | 0.6663 | 0.1428 | 0.7039 |
| LMS fitted, all training students | 0.0114 | 0.5704 | 0.0187 | 0.6125 |

In ASSISTments fold 1 the default rule scored 0.222 on average where 0.477 were correct (bin 0.2-0.3, 28,640 answers) and
0.886 where 0.795 were correct (bin 0.8-0.9, 32,010 answers). The default rule ranks well but its numbers are not
probabilities. This tests the prediction of the next answer, not the `p_known` belief the interface shows.

## 4. Published scores for ASSISTments 2009 (from a web search on 2026-10-27; I have not read the tables myself)

BKT 0.648 in a survey table and 0.67 to 0.73 in a replication study ([1604.02416](https://arxiv.org/pdf/1604.02416)); DKT
0.72 to 0.82 across papers, 0.7657 in one head-to-head table, 0.720 on a rebuilt dataset; SAKT 0.7063; AKT 0.7772
([2501.05415](https://arxiv.org/pdf/2501.05415), [2112.15072](https://arxiv.org/pdf/2112.15072),
[2504.15163](https://arxiv.org/pdf/2504.15163)). Protocols and dataset versions differ (one 2026 paper reports label leakage
from duplicated multi-skill rows in some releases), so these are a range, not a target. The fitted LMS rule and pyBKT sit
inside the BKT range and below the deep models. No EdNet reference scores were looked up.

## 5. Limits and corrections

- A first pyBKT run fitted all skills in one call and scored about 0.51 on ASSISTments. That was a mistake in how pyBKT was
  called; fitting one model per skill gives 0.7195. Anyone who saw 0.51 (for example in an earlier Kaggle run of the first
  notebook version) should discard it.
- pyBKT needed two small compatibility changes with the installed scikit-learn and numpy: a shim for its import-time metric
  probe (in the scripts) and one line in its `EM_fit.py` that I edited in a throwaway virtual environment. The notebook
  applies the same line change when it detects the old text. The model itself is unchanged.
- One run per table, 2 to 5 folds, fold assignment from scikit-learn (it can differ between versions: a Kaggle run of the
  older notebook gave 0.6732 for the fixed rule where the local run gave 0.6806).
- EdNet used a 1,500-student sample of 784,309. ASSISTments rows without a skill were dropped. CSEDM was not used.
- Datasets are not in the repository (CC BY-NC 4.0 for EdNet; check each dataset's terms before redistributing). Run with
  `KT_DATA_DIR` pointing at the folder that holds `ASSISTments2009/` and `EdNet/`.
- The Kaggle notebook was run by the owner (older version); this step's rewrite was run locally on a 600-student sample only.

## Reproduce

    python research/kt_comparison/compare.py assist09 --folds 5 [--fit] [--fit-skill] [--no-bkt]
    python research/kt_comparison/compare.py ednet --students 1500 --folds 5 --fit-skill
    python research/kt_comparison/cold_start.py assist09 --folds 3
    python research/kt_comparison/cold_start.py ednet --students 1500 --folds 3

in a separate virtual environment with numpy, pandas, scikit-learn, scipy and pyBKT (not added to the project's
requirements).
