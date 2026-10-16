# Gap report: project plan against current status

Audit date 2026-10-15, first written on branch `step-7-cache-stretch` (409 tests) and **updated after Step 8** on branch
`step-8-gap-closure` (450 tests), then after Step 9 on `step-9-concepts-consent-claims` (493 tests), then after Step 10 on `step-10-deletion-retention`
(505 tests); the statuses below are the updated ones, and sections 9 and 10 list what Steps 8 to 10 closed.
Sources compared: `docs/plan.md`, `docs/PRD.md` (34 features), `docs/TRD.md` (81 requirements), `docs/DRD.md`, the code and
tests in the repository, and the measured results in `docs/results/`. Every status below was checked in the code, the
tests or a measured result; where a status could not be checked it says so.

## 1. Summary

The system is a working, tested prototype of the whole demo flow in the plan (phases 0 to 5, gates G0 to G4 passed, the
technical part of G5 passed). It is not the full product in the PRD, and four kinds of gap remain:

1. **Features not built or only partly built:** 1 of 34 PRD features not built, 2 partly built.
2. **Requirements not met:** of 69 implementation requirements, 52 done, 5 partly done, 3 not built or not run, 9 not
   applicable by design (the sandbox is a custom runner, not Judge0). Compliance is built (TR-S-05 to S-08) but
   awaits the data protection contact's review.
3. **Validation targets missed or unproven:** of 12 validation tests, 7 pass, 1 fails (adaptive selection, in simulation
   only), 2 are partly met, 2 are not run (they need human raters or a local model).
4. **Gate G5 items that only people can do:** the explanation ratings, the backup video, the report, two rehearsals and the
   IPR conversation.

| Gate | Plan's condition | Status | Evidence |
| --- | --- | --- | --- |
| G0 | One-command start, frozen contracts, sandbox host chosen | Pass | Compose stack, `backend/openapi.json`, custom runner chosen (see section 6) |
| G1 | Student submits in the browser, adversarial suite passes, 30+ validated problems | Pass | 47 problems validated; `step-2-g1.md` |
| G2 | 10-item placement test, ledger rows, 5-item sanity test passes | Pass with a caveat | Sanity test beats the mean on tested concepts only (`diagnostic.md`) |
| G3 | 10 verified or fallback explanations, logs, zero leaks in 50 prompts | Pass | 10 of 10 verified; guarded 0 of 50 leaked (`feedback.md`) |
| G4 | 90% routing, heatmap with seeded class | Pass | 50 of 50 routed; heatmap with 20 synthetic students (`router.md`) |
| G5 | 10 clean demo runs, backup video, updated report, IPR conversation | Technical part passes; people part open | 10 of 10 runs, 0 failed steps (`integration.md`); video, report, IPR not done |

## 2. Product features (PRD)

Status of all 34 features. P0, P1 and P2 are the PRD's priorities.

| Status | Features |
| --- | --- |
| Done (31) | F-01, F-04, F-05, F-02, F-03, F-10, F-11, F-12, F-13, F-20, F-21, F-22, F-24, F-30, F-31, F-32, F-33, F-34, F-40, F-41, F-42, F-43, F-44, F-45, F-46, F-50, F-51, F-53, F-60, F-61, F-70 |
| Partly built (2) | **F-52** (P0) four of six routes work; `recommend` and `lms` answer "not available" by design. **F-62** (P1) the hint limit is per problem and approval of stored explanations works, but the leak threshold is global, not per problem. |
| Not built (1) | **F-23** difficulty estimates for new items from text and tags (P2). |

F-02 and F-03 are closed: a teacher can create a course and its concepts, add problems and upload notes (text, Markdown or
PDF) in the browser.

## 3. Technical requirements (TRD), excluding validation

69 requirements in groups A (architecture), M (mastery), X (sandbox), L (LLM), D (data), S (security and privacy), P
(performance).

| Group | Done | Partly done | Not built or not run | Not applicable |
| --- | --- | --- | --- | --- |
| A architecture (9) | 8 | 1 | 0 | 0 |
| M mastery (12) | 7 | 3 | 0 | 2 |
| X sandbox (9) | 2 | 0 | 0 | 7 |
| L LLM (12) | 12 | 0 | 0 | 0 |
| D data (8) | 7 | 0 | 1 | 0 |
| S security and privacy (10) | 8 | 0 | 2 | 0 |
| P performance (9) | 8 | 1 | 0 | 0 |
| **Total (69)** | **52** | **5** | **3** | **9** |

### 3.1 Partly done (5)

| ID (priority) | What is missing | Detail |
| --- | --- | --- |
| TR-A-08 (P1) | Request ID in the sandbox | Structured logs carry the request ID through the API, router and model calls; it is not passed into the sandbox container. |
| TR-M-05 (P1) | Refitting item parameters | Difficulty and discrimination are stored with a source flag (`prior`), but there is no refit from pilot answers. It needs real answers first. |
| TR-M-08 (P2) | Chat questions as a mastery signal | The route is stored with each chat message; the concept tag is not. |
| TR-M-10 (P0) | 5-item test beats the mean | True on the concepts the five items tested (10 of 10 seeds); true on all 12 concepts in only 3 of 10 seeds. |
| TR-P-03 (P0) | Explanation within 15 s | Median 4.04 s, but worst cases 14.75 s and 15.31 s in two measured runs; earlier runs reached 23 s. |

### 3.2 Not built or not run (6)

| ID (priority) | Requirement | Note |
| --- | --- | --- |
| TR-A-09 (P2) | LTI 1.3 launch | Done for the core launch ([step-13](step-13.md)) and grade passback ([step-16](step-16.md)), tested on Moodle 5.3; no roster sync or deep linking. |
| TR-D-05 (P2) | Offline experiments on CodeWorkout or FalconCode | Not started; licences not checked. Planned for phase 6. |
| TR-S-07 (P1) | Configurable retention; deletion on request; 48-hour erasure notice | Done, with one gap: the notice is in the app only, so a student who never signs in is not told ([step-10](step-10.md)). |
| TR-S-08 (P1) | Breach detection logs and a written breach procedure | Done: audit trail, breach report command and a draft procedure awaiting review ([step-12](step-12.md)). |
| TR-S-09 (P1) | Full demo on a local model | Not run (same as TR-V-12). The `local` provider now exists (TR-A-04); what is missing is a model installed on this machine. |
| TR-S-10 (P2) | Adult confirmation or parental consent | Not built. |

### 3.3 Not applicable by design

TR-X-01 to TR-X-06 and TR-X-09 are Judge0-specific (pinned release, credentials, network setting, compiler options, GPL
licence). The system uses the custom runner that TR-X-08 allows, so they do not apply literally. The equivalent controls
(no network, read-only root, non-root user, explicit limits, structured result only) are covered by TR-X-07, TR-X-08 and the
adversarial suite TR-V-01. TR-M-11 (DINA fit) and TR-M-12 (code-aware tracing) are "not to be used" and "future work"
statements and need no code.

## 4. Validation tests (TR-V)

| ID | Target | Measured | Status |
| --- | --- | --- | --- |
| TR-V-01 | Every sandbox attack contained | All contained, host clean | Pass |
| TR-V-02 | Every reference passes; each wrong solution fails in the expected category | 47 of 47 references pass; of 21 wrong solutions, 20 fail and 1 passes ("Most common letter": no test checks ties); expected categories not checked one by one | Partly met |
| TR-V-03 | Verified flow has more correct claims than plain, rated by two reviewers | Blinded sheet of 20 prepared, not rated | **Not run: needs two people** |
| TR-V-04 | Zero full-solution leaks in 50 requests | Guarded 0 of 50; plain model 44 of 50 | Pass (the n-gram guard itself never fired in this test) |
| TR-V-05 | Adaptive reaches the error threshold in 30% fewer items; mastery within 0.15 of truth after 15 submissions | 10% fewer; mean error 0.27 after 10 items; concept-level AUC 0.61 against 0.68 for an ability-only baseline | **Fail** (simulation only) |
| TR-V-06 | 5-item test beats the population mean | Yes on tested concepts, 3 of 10 seeds on all concepts | Partly met |
| TR-V-07 | Each role reaches only its own endpoints | 25 routes by 4 roles, a new route without a rule fails the test | Pass |
| TR-V-08 | 90% routed correctly | 50 of 50 (keyword rules alone: 41 of 50) | Pass |
| TR-V-09 | Right chunk in top 3 for 80% | 17 of 20 (85%) | Pass |
| TR-V-10 | 10 concurrent, 10 consecutive, restart | 0 of 210 steps failed in each; sessions survived restarts | Pass |
| TR-V-11 | Stored explanation under 1 s, no model call | 0.02 to 0.04 s for 5 of 5 later students | Pass (6 students, one problem) |
| TR-V-12 | Full demo on a local model | Not run; the local provider is built and tested against a stand-in server | **Not run** (needs a model installed) |

## 5. Plan tasks and gate items that are still open

| Plan item (phase) | Status |
| --- | --- |
| Concepts and misconceptions "reviewed by a second person" (0) | Open. A person must review the 12 concepts and 13 misconceptions. |
| Problems "written by the three teammates, checked by hand" (1) | The 47 items were drafted and validated by the agent. Every one is flagged "needs human review"; no person has reviewed them. |
| Course notes (3) | 8 notes written, corrected after an outside review, flagged "needs human review". |
| Instructor approval, gradebook, announcements (4, stretch, in this order) | Approval done (F-62); gradebook and announcements not built. |
| Rate 20 explanations with two reviewers (5) | Open. Sheet and scoring script are ready. |
| Backup video of the whole flow (5) | Open. |
| Run the whole flow on a local model "if time allows" (5) | Not run (a decision in Step 6). |
| Rewrite the project report around the new scope with an honest status table (5) | Open. This document can supply the status table. |
| Rehearse the 8-minute demo twice (5) | Open. |
| IPR search and conversation (5, IP track) | Open. Nothing should be demoed publicly before it. |
| Phases 6 to 8 (after the review): real-data evaluation, pilot, hardening and compliance, C and Java, generated probes, recommender | Not started, as planned. |

## 6. Deviations from the plan

| Deviation | Why | Consequence |
| --- | --- | --- |
| Custom Docker runner instead of Judge0 CE | The plan names this as the cut line (TR-X-08) because Judge0 is unreliable on Windows hosts. | The Judge0 hardening list (TR-X-01 to X-06) is replaced by the runner's own limits. `CLAUDE.md` still says "a patched Judge0 version"; this should be confirmed as accepted. |
| One person and one agent instead of three streams | Team size. | No second reviewer exists for any content or code; the review items in section 5 are all open for that reason. |
| Failure-signature cache built (plan: "if time allows") | Requested. | Done and measured (TR-V-11). |
| Second Gemini key added, DeepSeek removed | Requested. | The new key is refused by Google (403 project denied for Flash models, 429 quota for Pro), so all live answers come from the original key. |
| Repository has no `main` branch; steps are stacked branches | GitHub blocked creating `main` from this session. | No pull request exists. The default branch on GitHub is `step-2-execution-core`. |

## 7. Quality and delivery risks

1. **Everything is synthetic or self-generated.** The class heatmap uses 20 synthetic students; item parameters are priors;
   the question bank, notes, test messages and rating submissions were written by the agent. Results show the system works,
   not that it works for learners.
2. **Small samples.** Most measurements use 10 to 50 items (the retrieval test has 20, the cache test 6 students). None
   should be quoted as a rate without saying so.
3. **The core diagnostic claim is not supported yet.** Adaptive selection saves 10% of items (target 30%) and the
   concept-level mastery model predicts worse than a single ability number. The report must describe the model as a prototype.
4. **Leak guard unproven in isolation.** In the 50-prompt test the verifier's structure already kept code out, so the
   n-gram guard never fired; its own effect is unmeasured.
5. **Explanation latency near the limit.** The 15 s target is met at the median and missed or touched at the worst case.
   The demo relies on prepared and stored explanations.
6. **Tests share the app's database.** Running them removes the synthetic class; the seed must be run again before a demo.
7. **Compliance partly done.** Consent, deletion and a breach procedure exist (the procedure is a draft with blank contacts), and the 48-hour erasure
   notice reaches only students who sign in. TR-S-05 to S-08 are P1 and are needed before any use by real students.
8. **No second reviewer.** The CI is green on every branch, but code and content have had one author.

## 8. Recommended next actions, in order

**Before the review (people):**
1. Two reviewers rate `data/eval/rating_sheet.csv`; then run `python -m evaluation.rating_sheet compute` (TR-V-03).
2. Review the concept list, the question bank and the notes (flagged "needs human review").
3. Record the backup video; rehearse the demo twice; write the status section of the report from this document.
4. Speak to the IPR cell before any public demo.
5. Fix the Gemini Pro key in Google's console, or confirm the original key alone is enough.
6. Open the pull request into `main`.

**Small engineering items (all done in Step 8, see section 9):**
7. DONE: TR-A-04: make the model host address configurable, so a local server works without code changes (also unlocks TR-V-12).
8. DONE: TR-P-09: test the interface at 1366 px in Chrome and Edge.
9. DONE: TR-P-08: a small report of model calls per 100 submissions and the cache share, from existing logs.
10. DONE: TR-P-05: a short queue and automatic retry when the sandbox is busy.
11. DONE: TR-D-07: CSV and JSON export of mastery and events.
12. DONE (except creating concepts in the browser): F-02 and F-03, instructor screens to create problems and upload notes, with PDF reading.

**After the review (the plan's phases 6 to 8):** consent, retention and breach procedure (TR-S-05 to S-08), a pilot with real
students and refitting item parameters (TR-M-05, TR-D-05), then F-04, F-05, LTI and the extensions.

Gradebook and announcements (F-04, F-05) are the remaining stretch items. The three suggested items before them were done
in Step 9 (section 10).

## 9. What Step 8 closed (2026-10-15)

Measured results and commands are in `docs/results/step-8.md`.

| Item | Before | After |
| --- | --- | --- |
| TR-A-04 local model | Host addresses fixed in code | `local` provider for any OpenAI-compatible server, configured by `LOCAL_LLM_BASE_URL`; tested against a real localhost server |
| TR-P-05 busy sandbox | Plain 503, no retry | Queue limit of 20 jobs, 3 s wait, 503 with `Retry-After`, automatic retry in the interface; verified in a browser against the real stack |
| TR-P-08 usage report | None | `python -m evaluation.llm_usage`: 85.7 model calls per 100 failed submissions and 21% served without a call, on dev data |
| TR-D-07 export | None | CSV and JSON export of mastery and the ledger, no emails; ledger replays to the current vector |
| F-03 notes | Text only, by script | Text, Markdown and PDF through an upload screen; PDFs read in a limited child process |
| F-02 instructor screens | API only | Create a course, add a problem, manage notes in the browser; gap left: creating concepts |
| TR-P-09 1366 px | Not tested | All 12 screens clean in Chromium at 1366 x 768; Edge 155 rendered the login page; other screens in Edge and Chrome themselves not driven |

Two defects found and fixed on the way: the JSON export first included email addresses (caught by its own test), and the
validator's message for a wrong reference solution was cryptic.

## 10. What Step 9 closed (2026-10-16)

Measured results and commands are in `docs/results/step-9.md`.

| Item | Before | After |
| --- | --- | --- |
| F-02 concepts | A new course had no concepts and none could be created in the browser | Concepts are added inside the problem form; a new concept needs no other setup (mastery uses the prior and default rates) |
| TR-S-05 consent | None | A privacy notice before first use (providers read from the live configuration), recorded agreement with timestamps, withdrawal that stops processing at once, and 403 on every processing endpoint without agreement |
| TR-S-06 no identifiers in prompts | Not enforced by a test | A test checks the explanation and chat prompts contain neither the email nor its local part |
| TR-L-05 claimed input | The verifier ran nothing | An example input named in a claim is run on the student's program and the reference in the sandbox; accepted only if the outputs differ; never a hidden test input; the student sees their own output only |

Defects found and fixed on the way: the problem page overflowed a 390 px phone; a passing check stored failure wording as
its detail. Still open from the audit: TR-S-09 and TR-V-12 (a
local-model demo, which needs a model installed), TR-S-10, TR-D-05, F-23, and the people items in
section 5. The consent text is a draft awaiting the data protection contact.

## 11. What Step 10 changed

| Item | Before | After |
| --- | --- | --- |
| TR-S-07 deletion and retention | A student could not delete anything | A student can ask for deletion of their account, submissions, chat and mastery; it runs 48 hours later and can be cancelled. `RETENTION_DAYS` (off by default) schedules the same erasure for inactive students ([step-10](step-10.md)) |

## 12. What Step 12 changed

| Item | Before | After |
| --- | --- | --- |
| TR-S-08 breach detection and procedure | Request log lines without user or address, lost on every rebuild; no procedure | An append-only audit trail in the database, a breach report command and `docs/breach-procedure.md` (draft) ([step-12](step-12.md)) |

## 13. What Step 13 changed

| Item | Before | After |
| --- | --- | --- |
| TR-A-09, F-70 LTI 1.3 | No LMS integration | Core launch (OIDC login, signed id_token checks, role and course mapping, one-time code handover); a teacher and a student opened the tool from a local Moodle 5.3 ([step-13](step-13.md)) |

## 14. What Step 14 changed

| Item | Before | After |
| --- | --- | --- |
| F-04 assignments and gradebook | None | Assignments of coding problems with points and a due date; scores computed from stored run results (best on-time attempt, share of tests passed); late work shown, not counted; gradebook view and CSV/JSON download ([step-14](step-14.md)). The TRD has no requirement for F-04, so its tests are named after the PRD feature. |

## 15. What Steps 15 and 16 changed

| Item | Before | After |
| --- | --- | --- |
| Second audit | | Gradebook column order, LMS students' deletion, LTI target check, double audit, a flaky test fixed ([step-15](step-15-audit.md)) |
| Grade passback | Scores stayed in this app | The teacher sends on-time scores to the LMS; one column per assignment; shown live in Moodle's grader report ([step-16](step-16.md)) |
| F-05 announcements | None | Plain-text course announcements, posted, edited and deleted by the course's teacher, shown newest first to members ([step-17](step-17.md)) |
| Third audit | | A hint could reveal the solution of a problem set in an assignment; a late run result showed on another problem ([step-18](step-18-audit.md)). Overall status in [progress-report](progress-report.md) |
| Content management | Content could only be added | Edit, archive and restore problems and courses, rename and delete concepts, delete notes, leave or remove from a course, with no history lost ([step-19](step-19.md)) |
