# Verification status by feature, 2026-10-20

Every figure comes from a results file in this folder. Only the 971-test run and the dependency audits were re-run on 2026-10-20 ([dependency-audit-2026-10-20.md](dependency-audit-2026-10-20.md)); older figures carry their own dates in the files named. All students in every measurement are synthetic. No pilot with real students has been run.

| Area (IDs) | How it is checked | Measured result | Data | Verdict |
| --- | --- | --- | --- | --- |
| Roles and access (F-01, TR-V-07) | Every endpoint called as student, instructor, anonymous; fuzz in [step-57](step-57-audit.md) | 0 server errors in fuzz | Synthetic accounts | Pass |
| Sandbox (F-10 to F-12, TR-V-01) | Fork bomb, memory bomb, network, symlink and similar attacks inside the sandbox | All contained, host clean | Real sandbox | Pass |
| Problem bank (F-13, TR-V-02) | References run; wrong solutions must fail in the expected category ([step-35](step-35-wrong-solutions.md)) | 47 of 47 references pass; 21 of 21 wrong solutions fail as expected | Real bank | Pass |
| Moodle launch and grades (F-70) | Live run on Moodle 5.3; Moodle's grader report showed the sent score ([step-16](step-16.md)) | Score 2.00 shown in Moodle | Real Moodle, test users | Pass |
| Gradebook, quizzes, hand-in, rubrics, weights, to-do, calendar, notifications (F-04, F-71 to F-80, F-84 to F-89) | Automated tests; scores compared before and after each change to `assignment_scores`; ledger replay in [step-57](step-57-audit.md) | 971 tests pass; 0 mismatches over 187 users | Synthetic | Pass (rules only, no real-use data) |
| Placement: question saving (F-21, F-22, TR-V-05) | Adaptive against random selection, simulator ([step-56](step-56-pooled-model.md)) | Mean 24% fewer questions (range 17 to 28%); target 30% | Simulated students | **Not met** |
| Placement: accuracy (TR-V-05) | Error of the pooled model with the whole bank, simulator | Floor 0.187; target "under 0.15" cannot be reached on the simulator | Simulated students | **Not met** |
| 5-item test (TR-V-06) | Error against the population mean | Met on the simulator; fails on persona students (no spread between personas) | Simulated students | Partly met |
| Difficulty estimate (F-23) | Leave-one-out on 35 bank problems ([step-25](step-25.md)) | Mean absolute error 0.370 against 0.607 for the mean | Real bank | Measured |
| Mastery updates (F-30 to F-34) | Ledger replay: stored values against the rules | 0 mismatches over 187 users | Synthetic | Pass (rules, not truth) |
| Leak guard (F-44, TR-V-04) | 50 adversarial help requests, live model | Guard on: 0 of 50 leaked; plain model: 44 of 50 | Real model calls | Pass |
| Chat routing (F-51, TR-V-08) | 50 hand-labelled messages | 50 of 50 (keyword rules alone 41 of 50); target 90% | Hand-labelled | Pass |
| Note retrieval (F-40, TR-V-09) | 20 questions with a known source chunk | Right chunk in top 3 for 17 of 20 (85%); target 80% | Real notes | Pass |
| Stored explanations (F-46, TR-V-11) | Same failing submission for a second student | 0.02 to 0.04 s, no model call | Synthetic | Pass |
| New explanations (TR-P-03) | 40 timed requests | 40 of 40 within 15 s (max 12.69 s) | Real model calls | Pass (bounded) |
| Explanation quality (F-41, F-43, TR-V-03) | Two raters, blinded sheet of 20 | Not run: needs raters | None yet | **Not run** |
| Reliability (TR-V-10) | 10 concurrent users, 10 runs, restart | 0 of 420 steps failed | Synthetic | Pass |
| At-risk alerts and content report (F-90, F-92) | Each alert lists its triggering factors; report labelled as association | No check against real outcomes | Synthetic | Unvalidated |
| Dependencies | `pip-audit`, `npm audit` | 0 known vulnerabilities in each | n/a | Pass |

## What is missing and why

- **Real-student data.** Needed for TR-M-05 (refit item difficulty), for the TR-V-05 comparison with BKT and ability-only baselines, and for any claim that placement or mastery matches what students know. Needs a pilot; public datasets need a licence check (TR-D-05).
- **TR-V-03.** Needs two raters; the explanation verifier checks that a cited test and line exist, the concept matches and no solution appears. It does not check that the explanation is educationally right. Free-form chat answers are not verified in that way.
- **TR-V-12.** Local-model demo postponed by the owner.
