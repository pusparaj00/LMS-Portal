# Step 40: Non-circular diagnostic eval with MiroFish synthetic students (TR-V-05, TR-V-06)

Date: 2026-10-18. Branch `step-38-ux-foundation` (uncommitted working tree).

## What was done

The existing TR-V-05 simulation is circular: its students are drawn from a 2PL response model, which is the
same family as the selector it evaluates. To break that, I used MiroFish (a multi-agent LLM engine) to generate
synthetic student *personas* with per-concept Python mastery, and derived their answers with a deliberately
different response model (a linear difficulty threshold with noise and MCQ guessing) instead of the 2PL logistic.

- `MiroFish/student_eval/generate_students.py` (kept in the MiroFish clone, AGPL) generates the students using
  MiroFish's `LLMClient` against a local Ollama model (`qwen2.5:3b`).
- `backend/simulation/noncircular.py` runs the same adaptive-vs-random comparison as `simulation.run` on that output.

Command: `python -m simulation.noncircular --students-json <path> --bank data/bank`.

## Measured (2026-10-18, 50 synthetic students, local Ollama qwen2.5:3b)

| Items asked | adaptive MAE | random MAE |
| --- | --- | --- |
| 1 | 0.216 | 0.210 |
| 5 | 0.229 | 0.202 |
| 10 | 0.192 | 0.197 |

Adaptive reaches random's 10-item error only at item 10 (**0% fewer items; target 30%**). The 5-item ability
estimate does **not** beat the population mean (RMSE 0.631 vs 0.542 over all concepts). Coverage is still better
for adaptive (10.0 vs 8.0 concepts) and ranking correlation is higher (0.616 vs 0.551).

Held-out AUC: adaptive + mastery update 0.782, random 0.771, ability-only 2PL 0.751.

## Conclusion

TR-V-05 and TR-V-06 still fail when the students are generated non-circularly, so the earlier failure is not an
artifact of the circular simulator. The one positive signal: when ground truth is concept mastery (as the personas
are), the concept model now *beats* the ability-only baseline on held-out prediction (0.782 vs 0.751), which the
circular 2PL-truth run did not show. The adaptive selector's early items are noisy against a non-2PL response
process, which is where the efficiency loss comes from. These numbers are LLM personas, not real learners, and are
labelled synthetic.
