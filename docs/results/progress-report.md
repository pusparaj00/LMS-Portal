# Progress report: Adaptive AI-Powered LMS

Status on **16 Oct 2026**. Development ran on 15 and 16 Oct 2026 in 27 steps, each on its own branch of
`github.com/pusparaj00/LMS-Portal`. Latest branch: `step-27-audit-followups`, with **652 automated tests passing**. Every number
below was measured and comes from a results file in this folder, which gives the command and the date.

## 1. Where the project stands

The whole demo flow in the plan works end to end and is tested: placement test, coding exercises in a sandbox,
per-concept mastery, verified explanations and hints, the assistant chat, and the instructor dashboards. Since the demo
milestone, the system has gained:
- assignments and a gradebook;
- announcements;
- launching from Moodle (LTI 1.3), and sending grades back to it;
- consent, deletion and retention, and an audit trail with a breach procedure.

What is missing is mostly work only people can do:
- the explanation ratings;
- the demo video and the report;
- the IPR conversation;
- the data-protection review;
- the evaluation with real students.

| Measure | Status |
| --- | --- |
| Plan gates G0 to G4 | All passed (G2 with a caveat, see section 3) |
| Gate G5 (demo readiness) | Technical part passed (10 of 10 clean demo runs); people part open |
| PRD features (34) | 34 done |
| TRD implementation requirements (69) | 52 done, 5 partly done, 3 not built or not run, 9 not applicable (custom sandbox instead of Judge0) |
| Validation tests (12) | 7 pass, 1 fails (TR-V-05, simulation), 2 partly met, 2 not run (need raters or a local model) |
| Automated tests | 652 passing, lint clean; CI green on the final push of every step from Step 7 on (Step 15's first push failed on a flaky test, since fixed) |

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
| Full-solution leaks (TR-V-04) | Guarded 0 of 50; plain model 44 of 50 | 0 of 50 | Pass |
| Chat routing (TR-V-08) | 50 of 50 (keyword rules alone 41 of 50) | 90% | Pass |
| Course-note retrieval (TR-V-09) | Right chunk in the top 3 for 17 of 20 (85%) | 80% | Pass |
| Reliability (TR-V-10) | 0 of 210 steps failed with 10 concurrent and 10 consecutive users; sessions survived restarts | No failures | Pass |
| Stored explanation (TR-V-11) | 0.02 to 0.04 s for 5 of 5 later students, no model call | Under 1 s | Pass |
| New verified explanation (TR-P-03) | Median 4.04 s, worst 14.75 s (n = 8); worst 15.31 s in the provider comparison | 15 s | Not reliably met |
| Adaptive placement (TR-V-05) | 10% fewer items (target 30%); mean error 0.27 after 10 items | 30% fewer; error under 0.15 | Fail (simulation only) |
| Reference solutions (TR-V-02) | 47 of 47 pass; 20 of 21 wrong solutions fail (one passes: no test checks ties) | All | Partly met |
| Explanation quality (TR-V-03) | Blinded sheet of 20 prepared | Two reviewers | Not run |
| Local model demo (TR-V-12) | Provider built and tested against a stand-in | Full run | Not run (no model installed) |

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

The three audits found and fixed 16 bugs, each with a test, and each recorded in `step-11-audit.md`,
`step-15-audit.md` and `step-18-audit.md`. More defects were found and fixed during the steps themselves and are
listed in each step's results.

## 5. What is open

**Needs people or decisions (cannot be built):**
- Two reviewers to rate the 20 blinded explanations (TR-V-03).
- The backup video, the updated report, two demo rehearsals and the IPR conversation (gate G5).
- The data-protection contact's review of the consent notice, retention, and the breach procedure, whose contact names
  are blank. The rules apply from May 2027.
- A production host, and choices for the retention periods (`RETENTION_DAYS`, `AUDIT_RETENTION_DAYS`) and backup
  expiry.
- Phase 6 evaluation: dataset licences (TR-D-05) and pilot students.
- A `main` branch on GitHub, so the step branches can be merged by pull request.

**Not built:**
- TR-S-09 and TR-V-12 (demo on a local model; needs a model installed).
- TR-S-10 (adult or parental-consent check).

**Known limits:**
- Adaptive placement misses its efficiency target in simulation.
- A new explanation can take just over 15 s.
- LTI is tested on Moodle only, launches open in a new window, and a course has one teacher.
- Grades go to Moodle when the teacher clicks.
- The development machine is short of memory (about 0.4 GB free during the last Moodle run).

## 6. Suggested next steps

1. Do the people items for gate G5 first (ratings, video, report, rehearsals, IPR), because the review depends on them.
2. Create `main` and merge the step branches by pull request, so there is one reviewed line of history.
3. Choose a host and move the system there (Phase 7), then fill in the breach-procedure contacts and retention periods
   with the data-protection contact.
4. Start Phase 6: check the dataset licences and plan a small pilot. The adaptive-placement result needs real answers,
   not simulated ones.
