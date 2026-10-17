# Progress report: Adaptive AI-Powered LMS

Status on **17 Oct 2026**. Development ran on 15 to 17 Oct 2026 in 36 steps, each on its own branch of
`github.com/pusparaj00/LMS-Portal`. Latest branch: `step-36-problem-drafts`, with **672 automated tests passing** and CI
green on the last push of every step from Step 7 on. Every number below was measured and comes from a results file in
this folder, which gives the command and the date.

## 1. Where the project stands

The whole demo flow in the plan works end to end and is tested: placement test, coding exercises in a sandbox,
per-concept mastery, verified explanations and hints, the assistant chat, and the instructor dashboards. Beyond the
demo, the system has:
- assignments and a gradebook, and announcements;
- launching from Moodle (LTI 1.3), and sending grades back to it;
- consent with an adult confirmation, deletion and retention, an audit trail and a breach procedure;
- a separate screen layout for each of the three roles (student, instructor, admin);
- model-drafted practice problems that an instructor reviews, and that pass sandbox checks before they are offered.

What is missing is mostly work only people can do: the explanation ratings, the demo video and report, the IPR
conversation, the data-protection review, and an evaluation with real students.

| Measure | Status |
| --- | --- |
| Plan gates G0 to G4 | All passed (G2 with a caveat, see section 3) |
| Gate G5 (demo readiness) | Technical part passed on 17 Oct on the code of Step 30: 10 of 10 clean runs, 10 concurrent students, restart and cache ([step-30](step-30-g5-evidence.md)); people part open |
| PRD features (34) | 34 done |
| TRD implementation requirements (69) | 56 done, 2 partly done, 2 not built or not run, 9 not applicable (custom sandbox instead of Judge0) |
| Validation tests (12) | 8 pass, 1 fails (TR-V-05, simulation), 1 partly met, 2 not run (need raters or a local model) |
| Automated tests | 672 passing, lint clean |

## 2. Plan gates

| Gate | Condition | Status |
| --- | --- | --- |
| G0 | One-command start, frozen contracts, sandbox host chosen | Pass |
| G1 | Student submits in the browser, adversarial suite passes, 30+ validated problems | Pass: 47 problems validated |
| G2 | 10-item placement test, mastery ledger, 5-item sanity test | Pass with a caveat: the 5-item test beats the population mean on tested concepts only |
| G3 | 10 verified or fallback explanations, zero leaks in 50 prompts | Pass: 10 of 10 verified; guarded 0 of 50 leaked |
| G4 | 90% routing, class heatmap | Pass: 50 of 50 routed; heatmap with 20 labelled synthetic students |
| G5 | 10 clean demo runs, backup video, updated report, IPR conversation | 10 of 10 runs with 0 failed steps; video, report and IPR conversation not done |

## 3. Measured results

| What | Result | Target | Verdict |
| --- | --- | --- | --- |
| Sandbox attacks (TR-V-01) | All contained, host clean | All contained | Pass |
| Reference and wrong solutions (TR-V-02) | 47 of 47 references pass; 21 of 21 wrong solutions fail in the expected category (17 Oct, [step-35](step-35-wrong-solutions.md)) | All | Pass |
| Full-solution leaks (TR-V-04) | Guarded 0 of 50; plain model 44 of 50 | 0 of 50 | Pass |
| Chat routing (TR-V-08) | 50 of 50 (keyword rules alone 41 of 50) | 90% | Pass |
| Course-note retrieval (TR-V-09) | Right chunk in the top 3 for 17 of 20 (85%) | 80% | Pass |
| Reliability (TR-V-10) | 0 of 420 steps failed with 10 concurrent and 10 consecutive users; sessions survived restarts | No failures | Pass |
| Stored explanation (TR-V-11) | 0.02 to 0.04 s for 5 of 5 later students, no model call | Under 1 s | Pass |
| New explanation (TR-P-03) | Always within 15 s since Step 28: 40 of 40, max 12.69 s; on a slow model some students get the template instead | 15 s | Pass (bounded) |
| Chat speed with the working model first ([step-31](step-31-provider-order.md)) | "chat: hint" median 1.29 s (was 9.31 s before the change); one of three runs had a 17 s stall that was not explained | None set | Improved; stall open |
| Model-drafted problems (TR-L-10, [step-36](step-36-problem-drafts.md)) | 3 of 3 live drafts passed both sandbox checks on the first attempt, 3.9 to 5.5 s | Reference passes, planted mistake caught | Pass (3 samples) |
| Adaptive placement (TR-V-05) | 10% fewer items (target 30%); mean error 0.27 after 10 items | 30% fewer; error under 0.15 | Fail (simulation only) |
| 5-item test (TR-V-06) | Beats the mean on the tested concepts; on all concepts in 3 of 10 seeds | Beats the mean | Partly met |
| Explanation quality (TR-V-03) | Blinded sheet of 20 prepared | Two reviewers | Not run |
| Local model demo (TR-V-12) | Provider built and tested against a stand-in | Full run | Not run (postponed by the owner) |

## 4. What each step delivered

| Step | Branch | Delivered |
| --- | --- | --- |
| 1 to 6 | `step-1-foundation` to `step-6-integration` | Foundation, sandbox and question bank, placement test and mastery service, verified explanations and hints, chat router and dashboards, demo integration (gates G0 to G5) |
| 7 | `step-7-cache-stretch` | Shared, re-verified explanation cache; instructor review of stored explanations |
| 8 | `step-8-gap-closure` | Local-model provider, busy sandbox handling, data export, PDF notes, instructor screens |
| 9 | `step-9-concepts-consent-claims` | Concepts in the browser, privacy notice and consent, claim checking with example inputs |
| 10 | `step-10-deletion-retention` | Deletion on request and retention, 48-hour notice |
| 11 | `step-11-bug-audit` | First audit: 9 bugs fixed |
| 12 | `step-12-breach-procedure` | Audit trail, breach report command, draft breach procedure |
| 13 | `step-13-lti-launch` | Launch from Moodle (LTI 1.3), tested on a real Moodle 5.3 |
| 14 | `step-14-gradebook` | Assignments with due dates, gradebook, download |
| 15 | `step-15-audit` | Second audit: 5 bugs fixed |
| 16 | `step-16-grade-passback` | Grades sent to Moodle; shown in Moodle's own grader report |
| 17 | `step-17-announcements` | Course announcements |
| 18 | `step-18-audit` | Third audit: 2 bugs fixed, including a hint that could reveal the answer to graded work |
| 19 | `step-19-content-management` | Edit and archive problems and courses, manage concepts and notes, leave or remove from a course |
| 20 | `step-20-accounts` | Password change, admin resets, display names, admin user page, sessions end on a change |
| 21 | `step-21-test-database` | Tests run on their own database, Redis database and service copies; the app's data is untouched by a run |
| 22 | `step-22-student-work` | The teacher sees a student's mastery history, submissions and code (audited), completing F-34's instructor side |
| 23 | `step-23-chat-routes` | The assistant answers "what next" and deadlines, grades and announcements from records, completing F-52 |
| 24 | `step-24-leak-policy` | Per-problem help policy: hint limit and a stricter-only leak level, completing F-62 |
| 25 | `step-25-difficulty-estimates` | "Estimate it for me": a measured, model-free difficulty estimate for new problems, completing F-23 |
| 26 | `step-26-audit` | Audit: archived courses closed to students, chat skips them, estimate uses the course's concept names |
| 27 | `step-27-audit-followups` | A course owner is not demoted to student; DOMPurify pinned to 3.4.16 (npm audit: 0) |
| 28 | `step-28-explain-budget` | A new explanation always ends within 15 s; the template is shown when the model is too slow (TR-P-03) |
| 29 | `step-29-request-trace` | One checked request ID through API and sandbox (TR-A-08); chat questions tagged with their concept (TR-M-08) |
| 30 | `step-30-g5-evidence` | Gate G5 evidence measured again: 0 of 420 steps failed, restart and cache pass, fresh dump |
| 31 | `step-31-provider-order` | The working model first in the provider order (the `gemini_pro` key is refused); chat speed measured again |
| 32 | `step-32-role-ui` | A menu and layout per role; student course home with a next-step card and solved/in-progress badges; admin user table with counts and pages |
| 33 | `step-33-audit` | Audit: a seen worked solution can no longer become a probe or placement item; Account and Privacy back where the notice says; editor drafts kept and cleared on logout |
| 34 | `step-34-adult-confirmation` | Students confirm they are 18 or older when agreeing to the notice (TR-S-10); notice v4 |
| 35 | `step-35-wrong-solutions` | A tie test that catches the last uncaught wrong solution, and a check that each one fails in its expected category (TR-V-02) |
| 36 | `step-36-problem-drafts` | Model-drafted problems for instructors, offered only after the reference passes and a planted mistake fails in the sandbox (TR-L-10) |

The four audits found and fixed 21 bugs, each with a test, recorded in `step-11-audit.md`, `step-15-audit.md`,
`step-18-audit.md` and `step-33-audit.md`. More defects were found and fixed during the steps themselves and are
listed in each step's results.

## 5. What is open

**Needs people or decisions (cannot be built):**
- Two reviewers to rate the 20 blinded explanations (TR-V-03); moved to after the review, no reviewers before 21 Oct.
- The backup video, the updated report, two demo rehearsals and the IPR conversation (gate G5).
- The data-protection contact's review of the consent notice, retention, and the breach procedure, whose contact names
  are blank. The rules apply from May 2027.
- A production host, and choices for the retention periods (`RETENTION_DAYS`, `AUDIT_RETENTION_DAYS`) and backup
  expiry.
- Phase 6 evaluation: dataset licences (TR-D-05) and pilot students.
- A `main` branch on GitHub, so the step branches can be merged by pull request.
- A verified parental-consent route, if learners under 18 are ever to use the system (TR-S-10 asks for an adult
  confirmation or a parental-consent step; only the first is built).

**Hands-on tasks for the owner:**
- Run the test-data cleanup (`backup/cleanup-2026-10-17.sql`). The automatic safety check blocked it for me every time,
  so the leftover test accounts and about 40 test courses are still in the live database, and 80 of the 133 students in
  the demo class are test accounts.
- Fix or replace the `gemini_pro` key, or leave it out of the provider order as it is now.

**Not built:**
- TR-S-09 and TR-V-12 (demo on a local model): postponed by the owner until the move to a larger machine.
- TR-M-05 (refit item difficulty from real answers): needs real answers first.
- TR-D-05 (offline experiments on public datasets): licences not checked.

**Known limits:**
- Adaptive placement misses its efficiency target in simulation (TR-V-05 fails, TR-V-06 partly met).
- LTI is tested on Moodle only, launches open in a new window, and a course has one teacher.
- Grades go to Moodle when the teacher clicks.
- Backend Python packages have not been scanned for vulnerabilities (`pip-audit` is not installed; installing needs approval).
- Port 8000 (the API) is published on the local machine only. A production deployment must not expose it, because a caller
  there could get around the login rate limit.
- The development machine is short of memory (0.58 GB free of 7.7 GB during the Step 31 speed test).

## 6. Plan for the next steps

**Before the review on Wed 21 Oct** (the plan freezes features at the end of Mon 19 Oct):
1. Sat 17 Oct: run the cleanup script (two commands, trial run first), so the app shows only real and labelled
   synthetic data.
2. Sun 18 Oct: move the project to the larger machine: clone the repository, copy `.env` and the `backup/` folder by
   hand, restore the latest dump, start the stack, and run `docker compose --profile test run --rm test` there to
   confirm all 672 tests pass.
3. Mon 19 Oct: record the backup video after the cleanup, on the new screens. Rehearse the 8-minute demo twice.
4. Tue 20 Oct: have the IPR conversation. Re-run the G5 checks once on the new machine
   (`evaluation.load concurrent 10`, `evaluation.load runs 10`).
5. Wed 21 Oct: the review.

**After the review:**
1. Get two people to rate the blinded explanations (TR-V-03) and add the result to the report.
2. Create `main` on GitHub and merge the step branches by pull request, so there is one reviewed line of history.
3. Run the full demo on a local model once the larger machine is ready (TR-V-12, TR-S-09).
4. Start Phase 6: check the dataset licences and plan a small pilot. The adaptive-placement result needs real answers,
   not simulated ones, and refitting item difficulty (TR-M-05) depends on the same data.
5. Phase 7: choose a host, move the system, install `pip-audit` and scan the backend, and fill in the breach-procedure
   contacts and retention periods with the data-protection contact.
6. Phase 8, only after Phase 6 supports the core claims: C and Java runtimes, automatic probe generation, and the
   other extensions in the plan.
