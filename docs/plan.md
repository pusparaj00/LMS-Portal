# Implementation plan — Adaptive AI-Powered LMS

Oct 15, 2026 · @Joseph

## 1. Plan at a glance

The project is built in six phases before the review on Wed 21 Oct 2026, then three more phases that turn the demo into evidence and a deployable system. Each phase ends at a gate with a pass condition, and the phases overlap because they use different streams.

&#91;embedded content: phase roadmap · 6 phases, 6 gates, 15 to 21 Oct\]

Phase 3 cannot start until G1 and G2 are met, because it needs run results and the mastery service. The phases after the review are in section 8.

**Streams.** The plan assumes three people, one stream each. If your split is different, move the tasks, not the gates.

| Stream | Owns | Main phases |
| --- | --- | --- |
| A: Models and backend | Schema, API, mastery service, diagnostic, router, simulation | 0, 2, 4 |
| B: Sandbox and AI | Judge0, question bank, retrieval, LLM, verifier | 1, 3 |
| C: Frontend and LMS | Login, editor, dashboards, the screen for every flow | 1 to 5 |

**Assumptions.** Day 1 is Thu 15 Oct. Features freeze at the end of Mon 19 Oct. The review is on Wed 21 Oct. Requirement IDs refer to the PRD (F-xx) and the TRD (TR-xx).

## 2. Phase 0: Foundation (Thu 15 Oct)

By the end of today every teammate can run the system from a clean machine, and the interfaces between the three streams are frozen so they can work in parallel.

| Task | Stream | Requirement | Done when |
| --- | --- | --- | --- |
| Create the repository with a branch per stream, a README and a lint and test check on every push | A | TR-A-01 | A new clone builds and the check passes |
| Write the Docker Compose file for frontend, API, PostgreSQL with pgvector and Redis | A | TR-A-01, TR-A-08 | One command starts all services and the health checks are green |
| Freeze the API contracts for auth, problems, submissions, diagnostic and chat as an OpenAPI file, with mock responses | A and C | TR-D-02 | The frontend can call mock endpoints |
| Write schema version 1 and the migrations for the 15 core tables | A | TR-D-01 | Migrations run on an empty database |
| Choose the sandbox host: a Linux virtual machine for Judge0, or the custom Docker runner | B | TR-X-04, TR-X-08 | The host exists and every teammate has access |
| Draft about 12 Python concepts and about 10 misconceptions, each linked to a concept | B | TR-D-03 | A second person has reviewed the list |
| Pick the LLM provider and key, write the adapter stub, and decide whether a local model is also used | B | TR-A-04 | The adapter returns a canned reply through the real interface |

**Gate G0, end of Thu 15 Oct.** The system starts with one command, the contracts are frozen, and the sandbox host is chosen. If the host is not chosen, Phase 1 starts tomorrow without it.

## 3. Phase 1: Execution core (Thu 15 to Sat 17 Oct)

This phase delivers the thing every later phase depends on: a student submits code and gets structured test results back from an isolated sandbox. It also builds the question bank.

**Deployment warning for Day 1.** Judge0's release notes recommend Ubuntu 22.04 with a GRUB change that sets `systemd.unified_cgroup_hierarchy=0`, followed by a reboot ([release notes](https://www.github.com/judge0/judge0/releases/tag/v1.13.1)). Community reports say the same release fails on hosts that use the newer cgroup version, and that on WSL2 every submission returns Internal Error ([report](https://glama.ai/mcp/servers/SundaeYAGO/judge0-mcp)). Do not try it on a Windows laptop. Use a Linux virtual machine, and if it does not return a correct result by noon on Fri 16 Oct, switch to the custom Docker runner (TR-X-08).

| Task | Stream | Requirement | Done when |
| --- | --- | --- | --- |
| Deploy Judge0 v1.13.1 or a newer security release on the dedicated machine, with changed passwords and an authentication token | B | TR-X-01, TR-X-03, TR-X-04 | A test submission returns an Accepted result |
| Turn off network access, compiler options, command-line arguments and additional files, turn on submission deletion, and set explicit time, memory and process limits | B | TR-X-02, TR-X-05, TR-X-06 | A configuration check lists every setting and a network call from a test program fails |
| Build the submission service that sends code and test inputs and stores a structured run result | B | TR-X-07, F-12 | A run result row exists for each submission, and hidden inputs are never returned |
| Run the sandbox adversarial suite | B | TR-V-01 | Every attack is contained and reported as a structured error |
| Write about 35 Python problems with weighted concepts, categorised tests and reference solutions, drafted with an LLM and checked by hand; the three teammates write about a third each | All | TR-D-03 | The bank file contains at least 30 problems |
| Write the import and validation script | A | TR-D-04, TR-V-02 | A bad problem is rejected and every reference solution passes |
| Write about 10 code-tracing multiple-choice items whose wrong options map to misconceptions | B | F-24, TR-D-03 | Each wrong option has a misconception ID |
| Build login, the course page, and the problem page with a code editor and Run and Submit buttons | C | F-01, F-10 | A student can submit code in the browser and see the result |

**Gate G1, end of Sat 17 Oct.** A student submits code in the browser and sees structured test results from the sandbox, the adversarial suite passes, and at least 30 validated problems are loaded.

## 4. Phase 2: Diagnostic and mastery (Fri 16 to Sat 17 Oct)

This phase delivers the cold-start diagnostic and the mastery service, the two pieces the project is about. It runs in parallel with Phase 1 and uses the existing IRT and CAT code.

| Task | Stream | Requirement | Done when |
| --- | --- | --- | --- |
| Build the mastery service with the Bayesian update, a configuration table for slip and guess rates, and a database role that is the only writer of mastery | A | TR-M-01, TR-A-02 | Unit tests pass, and the API role cannot write to the mastery table |
| Add the ledger: each update writes before and after values, a rule ID and an evidence reference, and repeated requests for the same submission change nothing | A | TR-M-07, TR-M-09 | Replaying a submission list gives the same vector |
| Map test categories and error types to concepts | A | TR-M-02 | A failed category changes only its linked concepts |
| Port the IRT and CAT code into the diagnostic service, add a prior to the ability estimate, and select items by information over the concept vector | A | TR-M-03, TR-M-05, TR-M-10 | A 5-item test beats predicting the population mean |
| Add misconception probabilities and the top suspected misconceptions output | A | TR-M-04 | A wrong tagged option raises its misconception |
| Keep diagnostic sessions in Redis | A | TR-A-05 | Restarting the API does not lose a test in progress |
| Build the simulation harness with a simulator that differs from the selection model, comparing adaptive and random selection and a BKT baseline | A | TR-M-06, TR-V-05 | A results table with the date it was run |
| Build the placement test screen, the mastery dashboard and the "why did my mastery change" view | C | F-20, F-34, F-60 | A new student completes the test and sees the vector and misconceptions |

**Gate G2, end of Sat 17 Oct.** A new student completes a 10-item placement test and sees a mastery vector and the top suspected misconceptions, each submission moves mastery and writes a ledger row, and the 5-item sanity test passes. If the simulation is unfinished, finish the adaptive versus random comparison first and the baselines on Mon 19 Oct.

## 5. Phase 3: Verified feedback loop (Sun 18 Oct)

This phase builds the part that makes the product different: an explanation reaches the student only after code-level checks pass. It needs the run results from Phase 1 and the mastery service from Phase 2, so it starts once G1 and G2 are met.

| Task | Stream | Requirement | Done when |
| --- | --- | --- | --- |
| Write 5 to 8 short Python course notes, then chunk and embed them locally into pgvector and retrieve the top results above a minimum score | B | TR-L-01, TR-L-02 | A question about loops returns the loops note, and an unrelated question returns no source |
| Write the explain prompt and the JSON reply schema | B | TR-L-03, TR-L-04 | The model's reply parses against the schema |
| Implement the verifier: the test exists, the line exists, the concept matches, the sources are real and the leak guard, with one retry and then a template fallback | B | TR-L-04, TR-L-06, TR-L-12 | A deliberately wrong explanation is rejected and the fallback appears |
| Implement the hint ladder | B | F-45 | Each request moves one level, and no level shows a full solution |
| Select the probe question from the bank by concept, grade it, and send the result to the mastery service | A | TR-L-10, F-42 | A probe answer moves the mastery bar |
| Log every attempt with model name, prompt version and check results | B | TR-L-11 | Each explanation has check rows |
| Add the failure-signature cache if time allows | B | TR-L-09 | A repeat failure returns a stored explanation with no new model call |
| Build the explanation panel with a progress state, and the probe screen | C | TR-P-03, F-41 | The panel shows progress and then a verified answer |

**Gate G3, end of Sun 18 Oct.** Ten wrong submissions each produce a verified explanation or a template fallback, the verifier writes its logs, and the 50-prompt leak test shows zero leaks (TR-V-04). Rating 20 explanations for TR-V-03 happens on Mon 19 Oct.

## 6. Phase 4: Chat router and dashboards (Sun 18 to Mon 19 Oct)

This phase adds the agentic chat assistant and the instructor view. The router can be built and tested against stubs from Fri 16 Oct, so only the wiring waits for Phase 3.

| Task | Stream | Requirement | Done when |
| --- | --- | --- | --- |
| Build the router with a validated JSON route label, a confidence threshold and keyword fallback rules | A | TR-A-06, F-51, F-53 | Invalid model output still reaches a route |
| Build the four demo routes: explain, hint, progress and general | A and B | F-52 | Each route returns a reply with its sources |
| Keep a bounded chat history that resets when the problem changes, and pass student text as delimited data | A | TR-L-07, TR-L-08 | A pasted instruction in student text does not change the route or the rules |
| Give routes read-only mastery access and nothing that writes mastery | A | TR-A-02 | A route test cannot change a mastery value |
| Label 50 test messages and measure routing | A | TR-V-08 | At least 90% reach the right route |
| Build the chat panel with the route label shown | C | F-50, F-53 | The student can see and correct the route |
| Build the instructor class heatmap and misconception counts from seeded students | C | F-61 | The heatmap shows the seeded class |
| Add instructor approval of cached explanations, the gradebook and announcements only if the gates so far are met | C | F-62, F-04, F-05 | Each is a stretch item, in this order |

**Gate G4, end of Mon 19 Oct, noon.** At least 90% of the 50 labelled messages route correctly, and the instructor sees a class heatmap with seeded students. The recommend and LMS-query routes stay design only.

## 7. Phase 5: Integration and demo readiness (Mon 19 to Tue 20 Oct)

Features freeze at the end of Mon 19 Oct. Tuesday is for fixes, the evidence you will show, the report and rehearsal, so that the review shows a system that works and numbers that can be checked.

| Task | Stream | Requirement | Done when |
| --- | --- | --- | --- |
| Deploy everything on the demo machine, run the seed script and create two demo accounts | A | TR-D-06, TR-A-01 | A clean start reaches the login page with seeded data |
| Run the access-control tests for each role | A | TR-V-07 | A student cannot reach another student's data or an instructor endpoint |
| Rate 20 explanations with and without the verifier using two reviewers | B and C | TR-V-03 | A table of correct claim shares for both flows |
| Run the retrieval test with 20 questions | B | TR-V-09 | The right chunk is in the top 3 for at least 80% |
| Run 10 concurrent users, 10 consecutive demo runs and an API restart | All | TR-V-10, TR-P-06 | No failed requests and no manual repair |
| Cache the demo explanations, record a backup video of the whole flow, and take a database dump | B | TR-P-07, TR-L-12 | The demo works with the model switched off, and the video exists |
| Run the whole flow once on a local model if time allows | B | TR-V-12 | The log shows no call to a hosted provider |
| Rewrite the report around the new scope, with an honest status table and the results above | All | PRD section 3 | The abstract, status table and references match the system and the results |
| Rehearse the 8-minute demo script twice, once with a teammate playing the examiner | All | PRD section 7 | The run finishes in time and every step works |

**IP track, in parallel.** Before the review, search the patent databases for the verified-loop idea, talk to the institution's IPR cell about a provisional filing, and ask whether an internal review counts as disclosure. Do not publish, post or demo publicly until that is settled. Keep dated notes of design decisions and test results.

**Gate G5, end of Tue 20 Oct.** Ten consecutive clean demo runs, a backup video, an updated report, and a conversation with the IPR cell has happened.

## 8. After the review: Phases 6 to 8

The final-year timeline after 21 Oct is not fixed yet, so these phases use weeks counted from the review. Replace them with real dates once the team knows the submission and viva dates.

| Phase | Window | Goal | Main tasks | Exit criterion |
| --- | --- | --- | --- | --- |
| 6. Evaluation and pilot | Weeks 1 to 3 | Turn demo claims into evidence on real data | Offline experiments on CodeWorkout or FalconCode if their licences allow (TR-D-05); a small pilot with classmates or juniors; refit item parameters from pilot answers; a controlled comparison of verified and plain LLM feedback; write up the results | Results for diagnostic efficiency, explanation accuracy and leak rate on real or non-circular data, with limits stated |
| 7. Hardening and compliance | Weeks 3 to 5 | Make the system safe to run beyond a demo | Consent notice, minimised prompts, retention and deletion, breach procedure (TR-S-05 to TR-S-08); rate limits and secret scanning; backups; move to a production host; start LTI 1.3 (TR-A-09) | Security tests pass, and the institution's data-protection contact has reviewed the consent and retention design before the May 2027 duties apply |
| 8. Extensions | Weeks 5 onwards | Widen coverage and strengthen the claim | C and Java runtimes and question banks; LLM-generated probes that pass a reference-solution check (TR-L-10); code-aware tracing in the style of Code-DKT and student-question tracing (TR-M-08, TR-M-12); the recommender and LMS-query routes; a provisional patent filing and then a paper | Each extension has its own test from the TRD before it is claimed |

**Step 41, dashboards (F-63, F-64, F-65).** Student and instructor dashboards with stats, analytics, a grades page and course ratings, modelled on the Edu-Hub portal's features, using this system's own data and access rules. Gate: each figure comes from a database query, role and ownership tests pass, and both roles are checked in the browser.

**Order matters.** Phase 6 comes before Phase 8, because the extensions are only worth building if the core claims hold on real data.

## 9. Cut lines and working agreements

Six days leaves no slack, so the team decides in advance what to drop when a gate is missed, instead of arguing about it at midnight.

| If this happens | Do this |
| --- | --- |
| Judge0 does not return a correct result by noon on Fri 16 Oct | Switch to the custom Docker runner with the same limits (TR-X-08) and keep going |
| G2 is late on Sat 17 Oct | Fix the placement test at 8 items, keep adaptive selection, and run only adaptive versus random in the simulation |
| The verifier is not finished by Sun 18 Oct | Ship three checks only (test exists, line exists, leak guard), and label the rest design only |
| The hosted model is slow or down | Use cached explanations and template hints, and play the backup video for the failing step |
| Phase 4 is late | Cut in this order: instructor approval, gradebook, announcements, then the progress route |

**Drop first, in order:** the LMS-query and recommend routes, announcements, the gradebook, instructor approval, the failure-signature cache, claim replay and the local model run.

**Never drop:** sandbox isolation, the mastery ledger, the minimal verifier and leak guard, the placement test, the seeded demo data and the backup video.

**Working agreements**

- Start and end each day with a 15-minute sync that states the gate for the day and what blocks it.
- Merge to the integration branch at least once a day, and keep it runnable, so Monday is not the first time the parts meet.
- Name pull requests with the requirement ID they implement, and merge only with a test.
- Feature freeze at the end of Mon 19 Oct; after that only fixes, evidence, the report and rehearsal.
- Anything shown in the demo must really run. A module that is not working is shown as design and labelled that way.
