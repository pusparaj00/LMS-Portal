# Step 54: placement simulation after the cold-start changes (TR-V-05, TR-V-06)

Measured on 2026-10-19 (about 12:30 UTC) on branch `step-54-placement-core`, in the test container. The test is now
18 questions long on this bank (47 questions: 12 tracing, 35 coding; the limit is 14 tracing plus 6 coding, but the
bank has only 12 tracing questions). Both runs use the same code the app uses (`selection.py`), including the type
limits, the four-question warm-up and the seeded choice among near-best questions.

Commands:

- `python -m simulation.run --students 500 --seed 2026` (synthetic 2PL-family students, so partly circular)
- `python -m simulation.noncircular --students-json MiroFish/student_eval/synthetic_students.json --bank data/bank`
  (50 LLM-persona students from the earlier step; their file is not in this repository)

## Before and after

| Measure | Before (10 questions, 2026-10-15 / 10-18) | After (18 questions, 2026-10-19) |
| --- | --- | --- |
| Circular run: concepts touched | adaptive 10.0, random 8.0 | adaptive 12.0, random 10.6 |
| Circular run: correlation of estimate with true mastery | adaptive 0.297, random 0.259 | adaptive 0.384, random 0.346 |
| Circular run: error at the end (MAE) | adaptive 0.270, random 0.273 (10 questions) | adaptive 0.265, random 0.267 (18 questions) |
| Circular run: questions saved against random (target 30%) | 10% | 0% (adaptive reaches random's final error at question 18) |
| Circular run: 5-question ability estimate beats the mean predictor | yes, 0.618 vs 0.675 | yes, 0.613 vs 0.675 |
| Circular run: held-out AUC, concept vector / ability-only | 0.607 / 0.680 | 0.630 / 0.701 |
| Persona run: concepts touched | adaptive 10.0, random 8.0 | adaptive 12.0, random 10.7 |
| Persona run: correlation with true mastery | adaptive 0.616, random 0.551 | adaptive 0.717, random 0.621 |
| Persona run: error at the end (MAE) | adaptive 0.192, random 0.197 (10 questions) | adaptive 0.204, random 0.218 (18 questions) |
| Persona run: 5-question ability estimate beats the mean predictor | no, 0.631 vs 0.542 | no, 0.616 vs 0.542 |
| Persona run: held-out AUC adaptive / random / ability-only | 0.782 / 0.771 / 0.751 | 0.822 / 0.837 / 0.760 |

## What this does and does not show

- **Better:** every concept now gets evidence (12 of 12 against 10 of 12), and the estimate ranks the concepts better
  against the truth in both runs. That is the cold-start aim the changes were built for.
- **Not better:** the number of questions saved against random selection is 0% (target 30%), so TR-V-05 is still not
  met. The 5-question sanity test (TR-V-06) still fails on the persona students. On the circular run the ability-only
  baseline still predicts held-out answers better than the concept vector (0.701 against 0.630).
- **One figure to ignore:** the persona report says adaptive reaches random's final error "after 1 item (94% fewer)".
  That is an artifact of the metric. In that data the error with no evidence at all (about 0.21) is already below the
  error random selection ends with (0.218), because updates from random questions make the persona estimates slightly
  worse, so the threshold is crossed before any question is asked. It is not a saving, and I do not claim it.
- The persona run has 50 students from a small local model; the circular run uses the simulator I wrote. Neither
  describes real learners. The confidence rating, "I don't know" and the background answer are not simulated at all, so
  their effect is untested here; their rates are starting values.

## Gate check

A strong student (all answers right) ends above ability 1.0 and a weak student (all answers wrong) below -1.0 on each
of 10 seeds in the same bank (`tests/test_simulation.py::test_a_strong_student_ends_above_a_weak_one_on_every_seed`).
