# Step 99: fastembed 0.9.1 so that Pillow 13 is allowed (TR-L-02, TR-S-03)

Date: 2026-11-02. Closes the one finding left in [step-97](step-97-dependency-updates.md): Pillow 12.3.0, 39 advisories, fixed in 13.0.0, required by
`fastembed==0.9.0` (which does not allow Pillow 13).

| Change | Where |
| --- | --- |
| `fastembed` 0.9.0 to 0.9.1 (allows Pillow below 14); `pillow==13.0.0` pinned | `backend/requirements.txt` |
| Chunks tagged `...@fastembed-0.9.0` are retagged `...@fastembed-0.9.1` | migration 0035 |

## Why a migration

`embedder.model_id()` includes the fastembed version, and `store.search` only reads chunks whose `embedding_model` equals it. Nothing re-embeds
chunks when the tag changes, so upgrading alone would have hidden every stored note from search. The retag is correct only if the vectors are the
same, which was measured:

    53 texts from data/eval/retrieval_questions.json and retrieval_threshold_set.json, each embedded as a query and as a passage,
    in the live image (fastembed 0.9.0, Pillow 12.3.0) and in the rebuilt test image (fastembed 0.9.1, Pillow 13.0.0)
    largest absolute difference over 106 vectors: 0

Same model (`BAAI/bge-small-en-v1.5`), identical vectors, so retrieval results (TR-V-09, 17 of 20 in the top 3) cannot change. The full
retrieval evaluation was not re-run against a database.

## Tests and audit (2026-11-02)

- `docker compose -p lms --profile test run --rm --build test`: ruff clean, **1171 passed**, 2 warnings, 1442 s (slower than the 488 s of step 97
  because two research jobs were using the CPU at the same time).
- `pip-audit -r requirements.txt` in the test container: **No known vulnerabilities found.**
- `npm audit` (step 97): 0 vulnerabilities.

## Not done

The live stack is not rebuilt and migration 0035 is not applied to the live database; that happens when the branch is merged and the stack is
rebuilt (take a backup first, `scripts/backup.sh`).
