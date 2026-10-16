# Validation summary (TR-V-01 to TR-V-12)

All results were measured on 2026-10-15 on the local Docker Compose stack. The model is `gemini-3.5-flash-lite` unless a
row says otherwise. The detail and full command output are in the linked file. Small samples are marked as such and
should not be quoted as rates.

| ID | What was run | Command | Measured result | Target | Status |
| --- | --- | --- | --- | --- | --- |
| TR-V-01 | Sandbox adversarial suite | `pytest tests/test_sandbox_adversarial.py` ([step-2-g1](step-2-g1.md)) | Every attack contained with a structured error; host checks clean | Each stopped within limits, host unchanged | Pass |
| TR-V-02 | Reference and wrong solutions | `python -m app.bank_import data/bank --dry-run`; feedback and rating runs | 47 of 47 references pass. Of 21 wrong solutions written for the rating sheet, 20 failed and 1 passed ("Most common letter": the tests do not check ties) | Every reference passes; each wrong solution fails in the expected category | Partly met: one wrong solution is not caught; failure categories not checked one by one |
| TR-V-03 | Two reviewers rate verified and plain explanations | `python -m evaluation.rating_sheet generate` then `compute` ([integration](integration.md)) | Blinded sheet of 20 failing submissions prepared (`data/eval/rating_sheet.csv`, key separate). Verified flow: 19 of 20 accepted on attempt 1, 1 template | Verified share of correct claims higher than plain | Not run: needs two human reviewers |
| TR-V-04 | 50 adversarial help requests | `python -m evaluation.real_feedback leak` ([feedback](feedback.md)) | Guarded 0 of 50 leaked; plain model 44 of 50 | Zero with the guard | Pass (the leak guard itself never fired in this test, so its own effect is unmeasured) |
| TR-V-05 | Adaptive vs random selection; mastery vs baselines | `python -m simulation.run --students 500 --seed 2026` ([diagnostic](diagnostic.md)) | Adaptive 10% fewer items than random; mastery error 0.27 after 10 items; AUC 0.61 vs ability-only 0.68 | 30% fewer items; within 0.15 | Fail (simulation only) |
| TR-V-06 | 5-item test vs population mean | same ([diagnostic](diagnostic.md)) | Beats the mean on the tested concepts in 10 of 10 seeds; on all 12 concepts in 3 of 10 | Lower error than the mean | Partly met |
| TR-V-07 | Every endpoint as every role | `pytest tests/test_access_matrix.py` | 25 routes x 4 roles (anonymous, student, instructor, admin) match the written policy; a route without a rule fails the test | Each role reaches only its endpoints | Pass |
| TR-V-08 | Route 50 labelled messages | `python -m evaluation.router_eval routing` ([router](router.md)) | 50 of 50 (keyword rules alone 41 of 50) | At least 90% | Pass |
| TR-V-09 | 20 questions with a known source chunk | `python -m evaluation.retrieval` ([feedback](feedback.md)) | 17 of 20 (85%) in the top 3 after the notes revision | At least 80% | Pass |
| TR-V-10 | 10 concurrent students, 10 consecutive demo runs, restarts | `python -m evaluation.load concurrent 10`, `runs 10`, `prepare` / `verify` ([integration](integration.md)) | Concurrent: 0 of 210 steps failed. Consecutive: 0 of 210 failed (after the commit-order fix). Session survived an API and Redis restart and a full restart | No failed requests, no repair, no lost session | Pass |
| TR-V-11 | Same failing submission for later students | `python -m evaluation.load cache 5` ([cache](cache.md)) | First student 10.80 s from the model; the next 5 got the stored explanation in 0.02 to 0.04 s with only `cache` rows in explanation_checks | Stored explanation in under 1 s, no LLM call | Pass (small sample) |
| TR-V-12 | Full demo on a local model | none | Not run, by decision in Step 6 | Completes with no hosted call | Not run |

## Timing targets (TR-P)

| ID | Measured (median / 95th percentile / max) | Target | Status |
| --- | --- | --- | --- |
| TR-P-01 sandbox run | 0.17 / 0.39 / 0.44 s, n = 20 | within 5 s | Pass |
| TR-P-02 next diagnostic item | 0.1 / 0.2 / 9.3 ms, n = 200 | under 1 s | Pass |
| TR-P-03 new verified explanation | 4.04 / 14.75 / 14.75 s, n = 8; and 2.32 s median, 15.31 s max, n = 10 in the provider comparison | within 15 s | Not reliably met: the worst case sits at or just over 15 s |
| TR-P-03 prepared demo explanation | 0.04 / 0.07 / 0.07 s, n = 5 | within 1 s | Pass |
| TR-P-05 busy sandbox | Queue limit 20, 3 s wait, 503 with Retry-After, automatic retry; tested and shown in a browser ([step-8](step-8.md)) | A busy message and a retry, no drop | Pass |
| TR-P-08 model calls per 100 | 85.7 calls per 100 failed submissions, 21% served without a call (dev data, [step-8](step-8.md)); at most 2 calls for any submission | At most one call plus one retry; reported | Pass (dev data) |
| TR-P-09 1366 px | 12 screens at 1366 x 768 in Chromium, no overflow or console errors; Edge 155 login page only ([step-8](step-8.md)) | Works in Chrome and Edge | Pass for Chromium; Edge and Chrome themselves not fully driven |
| TR-S-05 consent | Notice before first use, recorded agreement and withdrawal, 403 on processing without agreement; 12 tests and a browser run ([step-9](step-9.md)) | Notice, recorded consent, withdrawal stops processing | Pass (text is a draft) |
| TR-S-07 deletion and retention | Request, 48-hour wait, cancel, full erasure and retention scheduling; 505 tests in the suite and a live run on the dev stack ([step-10](step-10.md)) | Deletion on request, configurable retention, 48-hour notice | Pass (notice is in the app only) |
| TR-S-08 breach logs and procedure | Audit trail of logins, refusals, exports, staff accounts, consent and erasure; report finds staged password guessing and submission probing; 7 tests, live checks ([step-12](step-12.md)) | Logs sufficient to detect and report; written procedure | Pass (procedure is a draft; contacts blank) |
| TR-A-09 LTI 1.3 launch | Teacher and student launched from Moodle 5.3 into the right course and role; 16 tests incl. 11 refusal cases ([step-13](step-13.md)) | Launch with role and course claims mapped | Pass (core launch only; Canvas not tested) |
| F-04 assignments and gradebook | 12 tests (scores, late work, due time edge, validation, access, download, erasure); browser run at 1366 and 390 px ([step-14](step-14.md)) | Assignments with due dates and a gradebook view | Pass |
| Grade passback (LTI AGS) | 6 tests against a fake LMS; live: Moodle's grader report showed the sent 2.00 ([step-16](step-16.md)) | Scores reach the LMS gradebook | Pass (sent on request; Canvas not tested) |
| F-05 announcements | 15 tests; browser run at 1366 and 390 px showed markup-like text as typed with no injection ([step-17](step-17.md)) | Announcements | Pass |
| TR-S-06 prompts | A test checks the explanation and chat prompts hold no email or local part ([step-9](step-9.md)) | No direct identifiers | Pass |
| TR-L-05 claimed input | Example input tried in the sandbox on both programs; 13 tests; live: 7 of 8 replies named one, all confirmed ([step-9](step-9.md)) | Output must differ from the reference | Pass (small live sample) |
