# Step 88: stronger research evidence (TR-V-03, TR-V-05, TR-L-04, TR-M-01)

Dates: runs on 2026-10-27 and 2026-10-28. Raw outputs: `docs/results/data/step-88-*`. All evidence is machine-made
(synthetic students, public datasets, model providers); no human raters and no real students. Reproduction commands are in
`research/README.md`.

## 1. Explanation flows with repeats, a stronger model and intervals (TR-L-04, TR-V-03)

    docker exec lmssim-api-1 python -m evaluation.baselines --repeats 3 --strong groq:openai/gpt-oss-120b

28 failing submissions, 3 repeats, provider chain `gemini_pro` then groq, mistral, openai, local. The stronger plain
baseline is a larger open-weight model on Groq (`gpt-oss-120b`); it was not checked to be better at explaining. Intervals
are 95%, bootstrap over failures (all repeats of one failure move together). "Shows solution code" is the leak guard's
verdict on the reply, which also counts any fenced code block.

| Flow | Shows solution code | Repeats hidden test data |
| --- | --- | --- |
| plain | 73% (62% to 85%), 71 replies | 10% (0% to 22%) |
| hint-only | 5% (1% to 10%), 83 replies | 1% (0% to 4%) |
| plain, stronger model | 100% (100% to 100%), 84 replies | 10% (1% to 20%) |
| verified flow, first attempt, before the checks | 0% (0% to 0%), 82 replies | 5% (0% to 13%) |

Verified flow, first attempt (82 replies): 87% (77% to 94%) passed every static check; 1% (0% to 4%) were not valid JSON in
the required shape. Of 78 replies that gave a worked example, 17% (10% to 23%) had a predicted output the sandbox showed to
be false.

Ablation (first attempts rejected by each static check, and rejected by it alone): `no_hidden_test_leak` 4 and 4,
`quoted_code_is_theirs` 3 and 3, `claim_testable` 1 and 1, `sources_real` 1 and 1, `json_valid` 1 and 1,
`concept_matches` 1 and 1. Every rejection came from a single check, so removing any one of these checks would have let the
replies it rejected through; the sandbox check of the worked example is a further 17% of the replies that gave one.
Provider errors (no reply): plain 13, hint-only 1, verified 2, stronger plain 0.

Reading:
- A stronger plain model did not make the plain flow safer; it showed solution code in every reply. The prompt-only
  guardrail (hint-only) was much safer than the plain call (5% against 73%), so the hint-only row is the fair baseline for
  the leak guard.
- Correction to step 87: that report quoted 10 of 24 worked examples (42%) with a false predicted output in one run. This
  larger measurement gives 17% (10% to 23%), so the single-run figure should not be quoted. The two runs differed in which
  provider answered, which was not recorded per reply.
- Not measured: whether the explanations are correct or helpful. That needs people (G-5).

## 2. Larger rating sheet for the human raters (TR-V-03)

`python -m evaluation.rating_sheet generate SHEET.csv KEY.csv --size 60 --hint` writes up to 60 failing submissions with
three blinded explanations each (verified, plain, hint-only) in a random order, and a separate key with the provider that
answered. `compute` reports the share correct per flow per reviewer and where both agree, with a 95% Wilson interval, and
Cohen's kappa. 49 extra failing submissions on 35 problems were added (`evaluation/rating_more.py`); all 49 failed in the
sandbox on 2026-10-27 and none duplicates an existing one. A 3-item smoke run of `generate --hint` worked against the
sandbox and the model on 2026-10-27; a full 60-item sheet has not been generated. The sheet is not filled in by me.

## 3. Mastery rule against the other models, with student-bootstrap intervals (TR-M-01)

`research/kt_comparison/significance.py`, 5 folds, 500 resamples of whole students, pooled test answers.

ASSISTments 2009 (283,105 answers, 4,163 students):

| Model | AUC | 95% interval |
| --- | --- | --- |
| per-skill mean | 0.6276 | 0.6232 to 0.6318 |
| LMS rule, fixed defaults | 0.6811 | 0.6754 to 0.6872 |
| LMS rule, fitted per skill | 0.7188 | 0.7137 to 0.7238 |
| pyBKT | 0.7196 | 0.7146 to 0.7245 |

| Pair (first minus second) | Difference | 95% interval |
| --- | --- | --- |
| LMS default - per-skill mean | +0.0535 | +0.0467 to +0.0607 |
| LMS fitted per skill - LMS default | +0.0378 | +0.0356 to +0.0398 |
| pyBKT - LMS default | +0.0385 | +0.0362 to +0.0405 |
| pyBKT - LMS fitted per skill | +0.0007 | -0.0001 to +0.0017 |

EdNet-KT1, 1,500-student sample (175,088 answers):

| Model | AUC | 95% interval |
| --- | --- | --- |
| per-skill mean | 0.5811 | 0.5669 to 0.5949 |
| LMS rule, fixed defaults | 0.6155 | 0.5910 to 0.6370 |
| LMS rule, fitted per skill | 0.6310 | 0.6170 to 0.6440 |
| pyBKT | 0.6307 | 0.6169 to 0.6431 |

| Pair (first minus second) | Difference | 95% interval |
| --- | --- | --- |
| LMS default - per-skill mean | +0.0344 | +0.0008 to +0.0688 |
| LMS fitted per skill - LMS default | +0.0154 | -0.0015 to +0.0320 |
| pyBKT - LMS default | +0.0151 | -0.0017 to +0.0320 |
| pyBKT - LMS fitted per skill | -0.0003 | -0.0029 to +0.0024 |

Reading: on ASSISTments the fixed rule beats the per-skill mean and per-skill fitting beats the fixed rule, both with
intervals that exclude zero; fitted LMS and pyBKT are indistinguishable (interval within about 0.002). On the EdNet sample
the fixed rule's lead over the per-skill mean is borderline (interval starts at +0.0008), and the gain from fitting is not
separable from zero. The pooled Platt row in the raw files (`lms_platt`) is lower than the default, which is an artefact of
pooling folds that each used a different map; within a fold Platt scaling cannot change the AUC (section 4).

## 4. Calibration of the mastery rule (TR-M-01, research only)

`research/kt_comparison/calibration.py`, 3 folds. Rule set before the run: a map succeeds on a dataset if, with every
training student, the calibrated ECE is at most 0.05 and the AUC is at most 0.005 below the uncalibrated rule's.

| | ECE uncalibrated | ECE Platt (all students) | ECE isotonic (all students) | log loss: uncal. / Platt / isotonic |
| --- | --- | --- | --- | --- |
| ASSISTments | 0.1418 | 0.0234 | 0.0062 | 0.6663 / 0.5990 / 0.5888 |
| EdNet sample | 0.1428 | 0.0298 | 0.0118 | 0.7039 / 0.6216 / 0.6172 |

**Both maps met the rule on both datasets.** AUC: Platt unchanged (0.6810 and 0.6146); isotonic +0.0044 and +0.0026. A
monotone map cannot reorder predictions but can merge close ones into ties, which scores a wrongly ordered pair as half
right; the default rule has 3,270 distinct predictions on one fold and isotonic reduces them to 43, so the rise says that
fine differences between the default rule's predictions carry little signal. How much data the map needs (ECE, Platt /
isotonic): 10 students 0.057 / 0.054 on ASSISTments and 0.129 / 0.150 on EdNet (not usable; Platt's AUC on EdNet fell to
0.540 with a spread of 0.108); 30 students 0.045 / 0.042 and 0.048 / 0.039; 100 students 0.027 / 0.015 and 0.043 / 0.021.
The product code is not changed; whether the interface should show calibrated values is a separate decision.

## 5. Adaptive placement against a textbook adaptive test and a fixed form (TR-V-05)

    python -m simulation.run --students 500 --seed S     (S = 2026 to 2029, bank of 75)

Pooled estimate for every way of choosing questions, so the comparison is about the choice alone. Max-information adaptive
is the textbook test: the question with the largest 2PL information at the current ability estimate, with no coverage term.
Fixed order asks the allowed questions in id order. Error is the mean absolute error of the mastery vector after 20
questions (lower is better); "items to reach" is how many questions each needs to reach random selection's final error.

| Seed | adaptive | max-information | random | fixed | items to reach: adaptive / max-info / fixed |
| --- | --- | --- | --- | --- | --- |
| 2026 | 0.212 | 0.222 | 0.228 | 0.222 | 12 / 16 / 18 |
| 2027 | 0.222 | 0.222 | 0.235 | 0.234 | 13 / 14 / 19 |
| 2028 | 0.216 | 0.222 | 0.232 | 0.226 | 11 / 15 / 16 |
| 2029 | 0.221 | 0.221 | 0.232 | 0.230 | 13 / 14 / 19 |
| Mean | 0.2178 | 0.2218 | 0.2318 | 0.2280 | 12.25 / 14.75 / 18.0 |

Questions saved against random's 20: adaptive 38.75%, max-information 26.25%, fixed order 10%. The adaptive and random
results match the step 68 report, so adding the baselines did not change them. The new policies are not scored on
held-out responses because their answers can overlap the held-out items.

Reading: the project's selection needs 2.5 fewer questions than the textbook test on average and meets the 30% target; the
textbook test does not. On seeds 2027 and 2029 the two reach the same final error and differ only in speed. Limits: four
seeds of 500 synthetic students, one run each, no intervals; the students come from the simulator, not from real learners.
An earlier draft of this comparison used the independent mastery estimate, whose error curve is nearly flat, and gave
meaningless "items to reach" values (for example 1); it was replaced by the pooled comparison above.

## Not done

Human ratings, a pilot, ethics approval, a `LICENSE` decision, and any change to what the interface shows. A full 60-item
rating sheet has not been generated.
