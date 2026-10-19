# Step 39: Graphify audit and verifier fixes (TR-L-04, TR-L-06, F-43, F-44)

Date: 2026-10-18. Committed on 2026-10-19 in `2a4d8b0` on branch `step-40-profiles-dashboard` (written while the changes were still uncommitted on `step-38-ux-foundation`).

## What was audited

The whole codebase was mapped with Graphify (code-only AST: 2529 nodes, 7304 edges, 120 communities, no import
cycles) and compared with `docs/plan.md`, `docs/PRD.md`, `docs/TRD.md` and `docs/DRD.md`. The system is ahead of the
plan's 21-Oct demo: phases 0 to 5 are built and tested, plus several phase 6 to 8 items (consent, erasure, LTI,
gradebook, announcements, breach procedure). The custom Docker runner replaces Judge0, as the plan's fallback allows.

## Bugs fixed

| Bug | Where | Fix |
| --- | --- | --- |
| Hidden-test leak: a claim could repeat a *passed* hidden test's input and pass | `feedback/verifier.py` | The `no_hidden_test_leak` check now tests the claim and `example_input` against all hidden inputs and failed hidden outputs, not only failed hidden tests. |
| Syntax errors could name a non-syntax concept | `feedback/verifier.py`, `feedback/{explain,signature_cache,demo_cache}.py` | `Evidence` carries `error_type`; on `syntax_error` only `error_concept_ids` are allowed, matching the mastery update. |

Two regression tests were added in `tests/test_verifier.py`.

## Investigated and dismissed

- Sandbox OOM classification: RLIMIT_AS (256 MB) fires before the cgroup limit, so Python raises `MemoryError`; the
  adversarial suite already covers the memory bomb (`memory_limit`).
- Unmapped test category falling back to all tagged concepts is intentional
  (`test_an_unmapped_category_changes_all_tagged_concepts`).
- A missing concept in `_locked_mastery` cannot happen through the schema's foreign keys.

## Measured (2026-10-18, `docker compose --profile test`)

| Check | Command | Result |
| --- | --- | --- |
| Lint | `ruff check .` | clean |
| Backend suite | `docker compose --profile test run --rm test` (image rebuilt first) | 674 passed, 2 warnings in 257.52 s (was 672; +2 new tests) |
| Sandbox adversarial | included in the suite | all 13 attacks contained |

`.gitignore` now ignores `graphify-out/`.

## Weak-spot investigation (TR-V-05)

Measured a fresh baseline (`python -m simulation.run --students 500 --seed 2026`): adaptive reaches random's
10-item error after 9 items (10% fewer; target 30%), and the concept model's held-out AUC is 0.607 against 0.680
for the ability-only 2PL baseline. Tried adding the standard IRT logistic scaling (`D = 1.702`) to the selector and
ability estimator, on the hypothesis that the selector was missing the scaling the truth model uses. It did not help
(adaptive error 0.272 vs 0.270, coverage 9.6 vs 10.0), so it was reverted. Conclusion: the efficiency gap is structural
— the independent per-concept update cannot match the correlated ability-based truth model, and the fixed
8-MCQ + 2-code structure caps coverage at ~10 of 12 concepts. Closing TR-V-05 needs a model change (Phase 6), not a
selection tweak.
