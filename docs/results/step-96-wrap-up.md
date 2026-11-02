# Step 96: wrap-up status (2026-11-02)

Date: 2026-11-02. Code under test: tip of `step-95-paper-controls` (`a407bd9`); this step adds only this file.
This file replaces the status table of [verification-status-2026-10-20.md](verification-status-2026-10-20.md), which predates steps 58 to 95.

## Test run

    docker compose --profile test run --rm test

Result: `All checks passed!` (ruff) and **1171 passed, 2 warnings in 755.96 s**. The warnings are a Starlette deprecation notice and a
short test key; neither is from application code. The live stack was started from Docker Desktop for this run and not rebuilt.

## Status by area, from the results files

All students in every measurement are synthetic, except where a row says otherwise. No study with enrolled learners has been run.

| Area (IDs) | Measured result | Source | Verdict |
| --- | --- | --- | --- |
| Roles, access, fuzz (F-01, TR-V-07) | 0 answered 5xx in 3,896 HTTP calls of a 32-student adversarial agent run; no refused action allowed, no allowed action refused | [step-78](step-78-adversarial-coverage.md) | Pass (synthetic agents) |
| Sandbox (TR-V-01, TR-X-01 to TR-X-06, TR-P-04) | four jobs at a time; 30 concurrent students: 0 of 690 steps failed in two runs (was 7 of 30 flows refused) | [step-85](step-85-sandbox-concurrency.md) | Pass |
| Production configuration (TR-O-01 to TR-O-07) | headers, redirect, single published port, weak-secret refusal, backup and restore row counts equal, checked on a throwaway stack | [step-58](step-58-production.md), [step-80](step-80-local-hosting.md) | Pass on the development PC; no public host exists |
| Explanations (TR-L-04, TR-L-12) | 26 of 28 verified on the first attempt, median 2.0 s | [step-79](step-79-gate-75-rerating.md) | Pass |
| Explanation quality (TR-V-03) | two LLM raters: verified 95%, plain 95% (21 rows). One human rater, 1 to 5 scale, 27 rows: hint-only 3.89, plain 3.30, verified 3.00. No two-human result | [step-79](step-79-gate-75-rerating.md), [step-89](step-89-single-rater-pilot.md) | **Open** (G-5); the single human rater does not support "verified explains better" |
| Placement (TR-V-05) | pooled estimate: 12.2 questions on average, 30% to 45% fewer than random over five seeds; held-out AUC higher in 5 of 5 seeds; ECE higher in 5 of 5 seeds; "within 0.15" target replaced (floor 0.167 on the simulator) | [step-72](step-72-targets.md), [step-93](step-93-claim-validity.md) | Met on the simulator for the pooled estimate only; **not shown on real students** |
| 5-item test (TR-V-06) | RMSE 0.169 to 0.177 against 0.204 to 0.218 for the population mean | [step-72](step-72-targets.md) | Met on the simulator |
| Cold-start prediction (TR-M-01, TR-V-05) | stack with transfer weights: AUC +0.022, +0.034, +0.040 over the default rule at N = 0; transfer itself adds 0.002 to 0.005 at N = 30 and almost nothing at 100 | [step-91](step-91-cold-start.md), [step-95](step-95-paper-controls.md) | Measured on public data; no Python course |
| Pilot with real students (TR-M-05, G-6) | five outside accounts, four active, six code submissions | [step-90](step-90-synthetic-vs-pilot.md) | **Open**: too few for any comparison |
| Reliability (TR-V-10) | 0 of 420 steps failed in the step-30 evidence run | [step-30](step-30-g5-evidence.md) | Pass (older run) |
| Dependencies | 0 known vulnerabilities from `pip-audit` and `npm audit` on 2026-10-20 | [dependency-audit-2026-10-20](dependency-audit-2026-10-20.md) | Not re-run in this step |

## Paper deliverables (outside the repository, in `docs/Report/Phase 1 Project reports/`)

| File | State |
| --- | --- |
| `Research_Paper_Audited.docx` and `.pdf` | 12 pages in Word; 36 references with DOI, arXiv or search links, in-text citations link to the list; layout gaps closed |
| `Research_Paper_ICALT_5page.docx` and `.pdf` | 5 pages including 25 references (the last page is references only); authors and affiliation removed for double-blind review; same numbers as the full paper |
| Numbers check | 456 distinct decimals in the full paper compared with the files in `docs/results/`: 443 found verbatim; the other 13 are in `Datasets/kt_predictions/table4_full.txt` (earlier runs, Table VII), except 0.0858, which is the difference of two Table VI cells (0.7261 − 0.6403) |

Placeholders still in the full paper: author emails, funding, competing interests, author contributions, model versions of the AI
assistant, a seed for the third EdNet sample, licence status of the ASSISTments and CSEDM data, and whether the repository is
readable by reviewers. The 5-page version withholds the first four and has no repository link.

## Needs people or approval (nothing here can be done from this machine alone)

1. Two human raters for the blinded sheet (TR-V-03).
2. A pilot with real students and consent (TR-M-05, TR-V-05, TR-V-06, G-6).
3. G5 people items: demo video, report, IPR conversation, data-protection review.
4. A public host and domain (step 81); the live stack runs the development configuration.
5. A decision on the TR-V-05 wording: keep the 30% target as met on the simulator for the pooled estimate, or require real students.
6. Cleanup of leftover test accounts: the cleanup SQL has to be run by the owner.
7. Paper placeholders above; ICALT 2027 submission (deadline 15 Jan 2027, per the note of 2026-11-02).
8. Optional: pretrained or tuned neural comparators on EdNet and CSEDM (hours of compute).
