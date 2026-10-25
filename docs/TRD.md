# TRD — Adaptive AI-Powered LMS

Oct 15, 2026 · @Joseph

## 1. Purpose and traceability

This TRD states what the system shall do technically so that the PRD's goals can be built, tested and defended. Every requirement has an ID, a priority and a basis: either research (R) from the sources in section 12, or a design decision (D) from the PRD and DRD.

**How to read it**

- IDs use the form TR-\<area>-\<number>: A architecture, M models, X sandbox, L retrieval and LLM, D data and interfaces, S security, P performance, V verification.
- "Shall" marks a requirement. Priority P0 must work in the 21 Oct demo, P1 should, P2 is design only. This matches the PRD.
- Numeric targets are proposals and are marked "target". The team confirms or changes them after the first measurements.
- Where the research gives a number, the number is cited. Where it does not, the requirement says what to measure instead of inventing a figure.

**Related documents.** The PRD holds product goals and the user-facing requirements (F-xx). The DRD holds the architecture, data model, API list and verifier design. This TRD adds the measurable technical requirements, the research behind them and the acceptance tests.

## 2. Research basis

Eleven findings from the literature and from vendor and security sources drive the requirements in this document. Each row names the requirement it produced, so a reviewer can trace a technical choice back to evidence.

| # | Finding | Source | Requirements produced |
| --- | --- | --- | --- |
| 1 | In a benchmark of 45 student solutions, 63% of LLM feedback hints were accurate and complete and 37% contained mistakes, including wrong line numbers and hallucinated issues | [Silva and Costa, 2025](https://arxiv.org/abs/2503.14630v1) | TR-L-04, TR-V-03 |
| 2 | LLM replies to student help requests almost always contained code, and earlier work used a second LLM to strip it out | [Tutor Kai study](https://arxiv.org/pdf/2403.09744) | TR-L-06, TR-V-04 |
| 3 | One study validated each LLM-generated repair against test cases before releasing feedback to students | [NUS poster](https://comp.nus.edu.sg/~bleong/slides/gaied23-coverage-poster.pdf) | TR-L-05 |
| 4 | CodeHelp makes every request one-shot because the chance of an off-track reply grows with more rounds of dialogue | [CodeHelp](https://arxiv.org/pdf/2308.06921) | TR-L-07 |
| 5 | Error-explanation quality depends heavily on giving the LLM the source code as context | [Debugging without error messages](https://arxiv.org/abs/2501.05706) | TR-L-03 |
| 6 | Code-aware knowledge tracing beat deep knowledge tracing by 3.07 to 4.00% AUC on 5 assignments from 410 students | [Code-DKT](https://arxiv.org/pdf/2206.03545) | TR-M-06, TR-V-05 |
| 7 | Test-case-informed and concept-tagged knowledge tracing for coding already exists (TIKTOC, KCGen-KT) | [KCGen-KT](https://arxiv.org/pdf/2502.18632) | TR-M-02 |
| 8 | Students' own questions carry information about mastery that code alone does not | [SQKT](https://www.arxiv.org/pdf/2502.10408) | TR-M-08 |
| 9 | Public coding datasets with concept tags exist: CodeWorkout (Java, 18 concepts) and FalconCode (Python, 28,617 first submissions) | [KCGen-KT](https://arxiv.org/pdf/2502.18632) | TR-D-05 |
| 10 | Judge0 isolates code with Linux namespaces and control groups, runs in privileged Docker mode, allows network access by default configuration, and had three escape CVEs fixed in v1.13.1 | [Tanto Security](https://tantosec.com/blog/judge0/) | TR-X-01 to TR-X-06, TR-X-09 |
| 11 | India's data-protection rules were notified on 13 Nov 2025, with notice, consent, safeguards and 72-hour breach reporting applying from 13 May 2027 | [JSA](https://www.jsalaw.com/?p=55573), [AZB](https://www.azbpartners.com/bank/update-indias-digital-personal-data-protection-framework-comes-into-effect/) | TR-S-05 to TR-S-08 |

**What the research does not settle.** No source I read reports learning gains for a verified-feedback programming tutor, and none gives a cold-start result on real programming data. The requirements therefore ask the team to measure both, not to assume them.

## 3. System and architecture requirements

The architecture in the DRD stands. These requirements make its key rules enforceable in code and configuration instead of only in documentation.

| ID | Requirement | Priority | Basis |
| --- | --- | --- | --- |
| TR-A-01 | The system shall run as separate containers (frontend, API, PostgreSQL with pgvector, Redis, sandbox runner) and start with one Docker Compose command from a clean machine | P0 | D |
| TR-A-02 | Only the mastery service's database role shall have write permission on the mastery and mastery\_events tables; the API, router and LLM adapter roles shall be read-only on them | P0 | D (F-32) |
| TR-A-03 | The sandbox runner shall sit on its own network segment, with no route to PostgreSQL, Redis, the API's secrets or the internal network, and shall be reachable only by the submission service | P0 | R10 |
| TR-A-04 | The LLM shall be called only through one adapter interface that sets timeout, retry count and model name from configuration, and supports a hosted and a local model without code changes | P0 | D |
| TR-A-05 | The API shall hold no per-user state in process memory; diagnostic sessions and chat context shall live in Redis with an expiry | P0 | D |
| TR-A-06 | The chat router shall return JSON that is validated against a fixed schema of route labels; invalid output or confidence below a configured threshold shall fall back to keyword rules | P0 | D (F-51, F-53) |
| TR-A-07 | Document ingestion, chunking and embedding shall run as background jobs, not inside a user request | P1 | D |
| TR-A-08 | Every service shall expose a health check, and the API shall write structured logs with a request ID that is carried through router, sandbox and LLM calls | P1 | D |
| TR-A-09 | The system shall support launch from Moodle or Canvas through LTI 1.3 | P2 | D (F-70) |

## 4. Algorithm and model requirements

The published work on coding knowledge tracing already covers concept tagging and test-case evidence, so the goal here is a correct, auditable implementation with honest baselines, not a claim of a new tracing model.

| ID | Requirement | Priority | Basis |
| --- | --- | --- | --- |
| TR-M-01 | The mastery service shall keep one probability between 0 and 1 per student and concept, updated by the Bayesian rule in the DRD, with slip and guess rates stored per concept and evidence type in a configuration table | P0 | D |
| TR-M-02 | Run results shall be mapped to concepts through a table that links test-case category and error type to concept IDs; a failed category shall change only the concepts linked to it | P0 | R7 |
| TR-M-03 | The cold-start test shall start every concept at a population prior, pick each next item as TR-M-13 describes, and stop at the longest length the course allows (an uncertainty stop was measured and removed, step 56) | P0 | D (F-20 to F-22) |
| TR-M-04 | Each misconception shall carry its own probability; choosing a tagged wrong option shall raise it and lower the linked concept's mastery, and the test shall report the top suspected misconceptions | P0 | D (F-24) |
| TR-M-05 | Each problem shall store difficulty and discrimination with a source flag (prior or estimated); the existing 2PL code shall supply item information, and items flagged prior shall be re-fitted after the pilot | P0 | D |
| TR-M-06 | A fixed-parameter BKT baseline and an ability-only IRT baseline shall be implemented, and every model result shall be reported against them using AUC and calibration error on held-out responses | P1 | R6 |
| TR-M-07 | Every mastery update shall write a mastery\_events row with the before and after values, the rule ID and a reference to the run result or answer that caused it | P0 | D (F-34) |
| TR-M-08 | Chat questions shall be stored with their route and concept tag so they can be used later as a mastery signal | P2 | R8 |
| TR-M-09 | Mastery updates shall be idempotent per submission and replayable: applying the same event list to the same priors shall give the same vector | P1 | D |
| TR-M-10 | The ability estimator shall use a prior so that short tests do not snap to the bounds; a test that does worse than predicting the population mean shall fail | P0 | D (earlier CAT result at 5 items) |
| TR-M-11 | The earlier DINA fit shall not be used until its guess and slip rates satisfy the model's own condition that guess plus slip is below 1 | P1 | D (earlier DINA result) |
| TR-M-12 | A code-aware tracing model in the style of Code-DKT shall be described as future work and shall not be presented as implemented | P2 | R6 |
| TR-M-13 | Placement selection shall draw from the course's live, concept-tagged problems that are not assignment problems, in three difficulty bands (easy below -0.5, medium -0.5 to 0.5, hard above 0.5), score each allowed item by concept coverage and by the expected shrinkage of the uncertainty of the pooled estimate (TR-M-18), choose among items within 10% of the best score with a generator seeded from the session, and keep to the type limits (at most 14 multiple-choice, at most 6 coding, at most 2 hard coding, no coding task in the first 4 questions, no two coding tasks in a row while a multiple-choice item remains) | P0 | F-20 to F-27 |
| TR-M-14 | The mastery service shall apply the answer rules of F-27 as named evidence types with fixed slip and guess rates (guessing, sure, don't know), apply the misconception update twice for a wrong answer marked sure, and let a misconception rise never from a don't know; the rates shall be constants changed only with a simulation result | P0 | F-27 |
| TR-M-15 | At the end of placement the mastery service shall compute the pooled estimate (TR-M-18) from the placement answers and write, for each concept that rests on the placement alone, one ledger row (rule pooled_estimate) that sets the concept to the estimate and stores that value, so the row can be replayed; concepts with other evidence keep their own estimate; rows of the earlier rule ability_inference still replay | P0 | F-28 |
| TR-M-16 | The learner model shall be computed from the ledger and shall give for each concept the mastery, the evidence count and weight of real evidence, a confidence label from fixed cut points on 0.5 over the square root of (effective evidence plus 2), the time of the newest real evidence, and a status (assessed, estimated or not assessed) | P0 | F-28 |
| TR-M-17 | The recommendation shall put a weak prerequisite (concepts.parent_ids) before the concept that needs it, give the reason, and be the same for the dashboard and the assistant | P1 | F-29 |
| TR-M-18 | The pooled estimate shall be a multidimensional 2PL with one ability per concept, a Gaussian prior whose pairwise correlation and spread are declared constants chosen only on training seeds and refitted when real answers exist, the app's own slip and guess rates and item parameters, and mastery defined as the chance of a right answer to an item with a = 1 and b = 0 and no guessing | P0 | F-28, TR-V-05 |

## 5. Code execution and sandbox requirements

The sandbox is the highest-risk component. Security researchers published three escape vulnerabilities in Judge0, patched in v1.13.1, and the author warned that the underlying ability to write files outside the sandbox remained. The requirements below therefore assume the sandbox host could be compromised and limit what it can reach ([Tanto Security](https://tantosec.com/blog/judge0/)).

| ID | Requirement | Priority | Basis |
| --- | --- | --- | --- |
| TR-X-01 | Judge0 CE shall be pinned to an exact release of v1.13.1 or later, and the team shall check for newer security releases before the review | P0 | R10 |
| TR-X-02 | Network access for submissions shall be disabled in the Judge0 configuration (the setting that lets a request enable it is on by default), and a test shall confirm that a student program cannot open a connection | P0 | R10 |
| TR-X-03 | All default credentials shall be replaced, an authentication token shall be required, and the Judge0 API shall accept calls only from the submission service | P0 | R10 |
| TR-X-04 | The runner shall be treated as untrusted: a dedicated virtual machine or host, no other services or secrets on it, and no student data kept after a run (submission deletion switched on) | P0 | R10 |
| TR-X-05 | CPU time, wall time, memory, process count, file size and output size limits shall be set explicitly, with CPU time as the main limit and a higher wall time as a guard against sleeping programs | P0 | R10, [Judge0 docs](https://ce.judge0.com/) |
| TR-X-06 | Compiler options, command-line arguments and additional files shall be disabled for student runs, because the published exploits used these inputs | P0 | R10 |
| TR-X-07 | Student code shall never run inside the API process; the submission service shall send code and test inputs and receive only a structured result, and hidden test inputs shall never be returned to the client | P0 | D |
| TR-X-08 | If Judge0 cannot be deployed in time, a custom Docker runner shall be used with no network, a read-only root filesystem, a non-root user and the same resource limits | P1 | D |
| TR-X-09 | Judge0 is licensed under GPL v3, so it shall be used unmodified as a separate service called over its API, and the institution shall confirm the licence is acceptable | P1 | [Judge0 docs](https://api.judge0.com) |
| TR-X-10 | Java and C student programs shall be compiled and run in the same sandbox container under the same no-network, read-only, non-root and wall-clock rules as Python; the compile happens once per job, with its own time limit, as the unprivileged user; compiler output shown to a student shall not name host paths or include the contents of files outside the job directory; per-language memory and process limits shall be measured and recorded | P0 | F-94 |

## 6. Retrieval and LLM requirements

The research shows that LLM feedback on student code is useful but often wrong, and often gives away code. These requirements make accuracy and non-disclosure properties the code checks, not hopes about the model.

| ID | Requirement | Priority | Basis |
| --- | --- | --- | --- |
| TR-L-01 | Course notes shall be split into overlapping chunks that keep their document and section reference, embedded into pgvector, and retrieved top-k with a minimum relevance score; below the score the reply shall say no course source was found | P0 | D |
| TR-L-02 | The embedding model shall run locally, and its name and version shall be stored with every vector so a model change triggers re-embedding | P0 | D |
| TR-L-03 | The explain prompt shall contain the problem statement, the student's code, the run result (failed test categories and error message), the mapped concept and the retrieved chunks | P0 | R5 |
| TR-L-04 | The LLM shall return JSON with failing test ID, line, concept ID, claim, source chunk IDs and hint level; deterministic checks shall run before display, with at most two attempts and then a template fallback | P0 | R1 |
| TR-L-05 | When a claim names an input, the verifier shall run the student's code on it in the sandbox and confirm the output differs from the reference | P1 | R3 |
| TR-L-06 | The leak guard shall reject fenced code and code beyond a few lines, and shall compare token similarity with the reference solution against a threshold tuned on the question bank; it shall not depend on another LLM alone | P0 | R2 |
| TR-L-07 | The explain route shall use only the current submission's evidence; the chat route shall keep a bounded history window and reset it when the problem changes | P0 | R4 |
| TR-L-08 | Student code and chat text shall be passed as delimited data, the model shall have no tool that writes mastery or reads another user's data, and its output shall be accepted only in the fixed JSON schema | P0 | D |
| TR-L-09 | Verified explanations shall be cached by failure signature (problem, sorted failed categories, error type, normalised message) and reused until an instructor edits or rejects the entry | P1 | D (F-46) |
| TR-L-10 | Probe questions shall be selected from the vetted question bank by concept; LLM-generated probes are P2 and shall enter the bank only after a reference solution passes all their tests and a deliberately wrong solution fails | P0 | D, R3 |
| TR-L-11 | Temperature shall be set low through configuration, and each explanation shall log the model name, prompt version and check results | P0 | D |
| TR-L-12 | If the LLM times out or fails, the system shall show a template hint keyed on error type and concept, and shall record the fallback | P1 | D |
| TR-L-13 | The verifier, the leak guard and the template fallback shall use the problem's language for tokens, keywords, literals and error lines; a language without a measured wrong-solution result shall be labelled as such | P0 | F-94 |

## 7. Data, interface and integration requirements

Data quality decides whether the mastery model and the verifier can be trusted, so the question bank gets as much specification as the code.

| ID | Requirement | Priority | Basis |
| --- | --- | --- | --- |
| TR-D-01 | The schema in the DRD (15 core tables and 6 added tables) shall be created by versioned migrations, never by hand | P0 | D |
| TR-D-02 | The API shall publish an OpenAPI description, validate every request and response with typed models, and return errors in one JSON shape | P0 | D |
| TR-D-03 | Each problem shall store its statement, language, weighted concepts, test cases with category and hidden flag, a reference solution, difficulty and discrimination with a source flag, and for multiple-choice items the misconception behind each wrong option | P0 | D |
| TR-D-04 | A validation script shall run on import and reject a problem unless its reference solution passes every test, it has at least one concept, and every test has a category | P0 | D, R3 |
| TR-D-05 | CodeWorkout (Java) and FalconCode (Python) shall be considered for offline experiments on the mastery update and baselines, subject to their licence terms, and shall not be loaded into the product database | P1 | R9 |
| TR-D-06 | A seed script shall create one course, about 35 problems, a few notes and two demo accounts, so every demo run starts from the same state | P0 | D |
| TR-D-07 | Mastery vectors and mastery events shall be exportable as CSV or JSON for evaluation and for the instructor | P1 | D |
| TR-D-08 | Router decisions, sandbox runs, verifier checks and mastery updates shall be logged with UTC timestamps and the request ID | P0 | D |

**Interfaces**

| Interface | Protocol | Contract |
| --- | --- | --- |
| Frontend to API | HTTPS, JSON | OpenAPI description, JWT bearer token |
| API to sandbox | HTTP, JSON | Code and test inputs in; structured result out; authentication token required |
| API to LLM | HTTPS through the adapter | Fixed JSON schema in the reply, timeout and retry from configuration |
| API to PostgreSQL | SQL | Separate database roles per service, with only the mastery role allowed to write mastery |
| API to Redis | Redis protocol | Password required; keys expire; no data that must outlive a restart |
| LMS to API (P2) | LTI 1.3 | Launch with role and course claims mapped to the system's roles |

## 8. Security and privacy requirements

India's data-protection rules were notified on 13 Nov 2025. Law-firm summaries say the notice, consent, safeguard and breach-reporting duties apply from 13 May 2027, with one source giving 14 May ([JSA](https://www.jsalaw.com/?p=55573), [AZB](https://www.azbpartners.com/bank/update-indias-digital-personal-data-protection-framework-comes-into-effect/)). They are not yet in force for the 21 Oct review, but a system that stores student code and chat should be built for them now. This is orientation, not legal advice, so the institution's legal or data-protection contact should confirm the duties.

| ID | Requirement | Priority | Basis |
| --- | --- | --- | --- |
| TR-S-01 | Passwords shall be stored with a salted adaptive hash, and access tokens shall expire after a short time | P0 | D |
| TR-S-02 | Every endpoint shall check role, and every read of submissions, mastery or chat shall check ownership; automated tests shall prove a student cannot read another student's data or call instructor endpoints | P0 | D |
| TR-S-03 | Secrets shall come from environment variables, none shall be committed, and a secret scan shall run before each push | P0 | D |
| TR-S-04 | Submissions and chat shall have rate limits and maximum request sizes | P1 | D |
| TR-S-05 | Before first use, the system shall show a clear notice of what is collected (code, answers, chat), why, and which model provider receives it, and shall record consent with a timestamp; withdrawing consent shall stop processing | P1 | R11 |
| TR-S-06 | Prompts sent to a hosted model shall contain no name, email or other direct identifier, only a pseudonymous user ID where one is needed | P1 | R11 |
| TR-S-07 | Retention shall be configurable, deletion on request shall remove submissions, chat and mastery, and scheduled erasure shall notify the user at least 48 hours before it completes | P1 | R11 |
| TR-S-08 | Logs shall be sufficient to detect and report a personal data breach, and a written procedure shall cover reporting to the regulator and affected users, which law-firm summaries describe as within 72 hours | P1 | R11 |
| TR-S-09 | The full demo flow shall be shown working with a local model so that student code can stay inside the institution | P1 | D |
| TR-S-10 | The deployment shall confirm that users are adults, or add a verified parental-consent step before any use by learners under 18 | P2 | R11 |

## 9. Performance, reliability and capacity requirements

The research gives no performance figures for this kind of system, so every number below is a target the team should confirm after the first measurements. One design consequence is firm: an explanation cannot be streamed to the student before the verifier has seen all of it, so the earlier plan to stream explanations is replaced by a progress state followed by a verified answer.

| ID | Requirement | Priority | Basis |
| --- | --- | --- | --- |
| TR-P-01 | A sandbox run for a typical problem shall return within 5 s, with a hard stop at 10 s (target) | P0 | D |
| TR-P-02 | Selecting the next diagnostic item shall take under 1 s (target) | P0 | D |
| TR-P-03 | Explanations shall not be shown before verification; the interface shall show a progress state, and a verified explanation shall appear within 15 s for a new failure and within 1 s from the cache (target) | P0 | D, R1 |
| TR-P-04 | The demo deployment shall serve 10 concurrent students without failed requests (target), shown by a scripted load test | P0 | D |
| TR-P-05 | When the sandbox queue is full, the system shall show a busy message and retry, not return an error or drop the submission | P1 | D |
| TR-P-06 | The full demo script shall complete 10 times in a row without manual repair | P0 | D |
| TR-P-07 | A restart of the API container shall not lose any diagnostic session, and a database dump taken before the review shall restore the seeded state | P1 | D |
| TR-P-08 | Each failed submission shall cause at most one LLM call plus one retry, and the system shall report LLM calls per 100 submissions and the share served from cache | P1 | D |
| TR-P-09 | The interface shall work in current Chrome and Edge at 1366 px width | P1 | D |

### Deployment and operations

One VPS or college server, reached by IP address. A browser warns about the self-signed certificate until the institution installs a certificate from its own authority or gets a domain name.

| ID | Requirement | Priority | Basis |
| --- | --- | --- | --- |
| TR-O-01 | A reverse proxy shall terminate TLS with a self-signed certificate for the server's IP address and redirect plain HTTP to HTTPS | P1 | D |
| TR-O-02 | In the production configuration only the proxy shall publish ports (80 and 443); the API, the front end, the database, Redis and the mastery service shall be reachable only inside the container network | P0 | D, TR-S-02 |
| TR-O-03 | Behind the proxy, rate limits shall still count the real client address, and an address sent by the client in X-Forwarded-For shall be ignored | P0 | D, TR-S-04 |
| TR-O-04 | In production mode the API shall refuse to start if the JWT secret or the mastery token is shorter than 32 characters or still a placeholder, or if the database or Redis password is shorter than 16 characters | P0 | D, TR-S-03 |
| TR-O-05 | Every service shall restart on failure, rotate its logs and have a memory limit | P1 | D, TR-P-07 |
| TR-O-06 | A script shall back up the database on a schedule, delete dumps older than a set number of days, and a second script shall restore the latest dump into a scratch database and compare row counts with the live one | P1 | D, TR-S-07 |
| TR-O-07 | The proxy shall send X-Content-Type-Options, X-Frame-Options, Referrer-Policy and Permissions-Policy headers on every response, and a health check shall show whether the proxy and the API are up | P1 | D |

## 10. Verification and acceptance

Each requirement is checked by a test below. Results should be saved with the date they were run, because they are also the evidence for the final report and for any later patent filing.

| ID | Test | Verifies | Pass condition |
| --- | --- | --- | --- |
| TR-V-01 | Sandbox adversarial suite: infinite loop, memory bomb, fork bomb, network call, symlink to a host path, write outside the temp directory, very large output, shell characters in inputs | TR-X-01 to TR-X-07 | Each is stopped within limits, reported as a structured error, and leaves the host unchanged |
| TR-V-02 | Run every reference solution and a set of deliberately wrong solutions | TR-D-04, TR-M-02 | Every reference passes; each wrong solution fails in the expected test category |
| TR-V-03 | Two reviewers rate every claim in at least 20 explanations, with and without the verifier, on the same failing submissions | TR-L-03 to TR-L-05 | Verified flow has a higher share of correct claims than the plain LLM flow; the first-attempt pass rate is reported |
| TR-V-04 | Send 50 adversarial help requests such as "give me the full code" | TR-L-06, F-44 | Zero replies with a full or near-full solution with the guard on; the plain LLM rate is reported for contrast |
| TR-V-05 | Compare adaptive and random item selection, and compare mastery against BKT and ability-only baselines, using AUC and calibration error on held-out responses | TR-M-03, TR-M-06 | Adaptive reaches the error threshold in at least 30% fewer items, and mastery is within 0.15 of true skill after 15 submissions (targets from the PRD) |
| TR-V-06 | Run a 5-item test and compare its error with predicting the population mean | TR-M-10 | Test error is lower than the mean predictor |
| TR-V-07 | Call every endpoint as a student, an instructor and an anonymous user | TR-S-02 | Each role can reach only its own endpoints and data |
| TR-V-08 | Route 50 hand-labelled messages | TR-A-06 | At least 90% reach the right route |
| TR-V-09 | Ask 20 hand-written questions that each have a known source chunk | TR-L-01 | The right chunk is in the top 3 for at least 80% of questions |
| TR-V-10 | Run 10 concurrent students, 10 consecutive demo runs and an API restart | TR-P-04, TR-P-06, TR-P-07 | No failed requests, no manual repair, and no lost diagnostic session |
| TR-V-11 | Repeat the same failing submission for a second student | TR-L-09, TR-P-03 | The stored explanation is returned in under 1 s with no new LLM call logged |
| TR-V-12 | Run the full demo flow on a local model | TR-S-09 | The flow completes and the log shows no call to a hosted provider |
| TR-V-13 | Run the sandbox adversarial suite and the wrong-solution suite (TR-V-01, TR-V-02) for Java and C | TR-X-10, TR-L-13 | Every attack is stopped within limits and leaves the host unchanged; every reference solution passes and every deliberately wrong solution fails |

**Simulation caveat.** If simulated students are drawn from the same model that selects the items, the result is circular, as it was in the earlier CAT study. Generate the simulated answers with a different model (for example, a different response function and a different set of guess and slip values) and say so in the report.

## 11. Technical risks, constraints and open decisions

**Constraints.** Six working days to the review, a team of three, Python only, a single machine and one LLM API key or local model.

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Sandbox escape, as published for earlier Judge0 versions | Host and data compromised | Patched version, no network, dedicated host, no secrets on it (TR-X-01 to TR-X-06, TR-A-03) |
| Verifier rejects many explanations, so students see template hints | Weaker experience, and the differentiator looks empty | Log first-attempt pass rate, tune the prompt, allow one retry, reuse cached verified entries (TR-L-04, TR-L-09) |
| Verified explanation takes too long without streaming | Students wait | Progress state, cache, and a measured time budget (TR-P-03) |
| Fixed slip and guess rates make mastery look arbitrary | Reviewers doubt the model | Report calibration error against baselines and label the model a prototype (TR-M-06) |
| No real programming data for the cold-start claim | Claim is unsupported | Offline datasets where the licence allows, a small pilot, and non-circular simulation (TR-D-05, TR-V-05) |
| Writing misconception-tagged items takes longer than planned | Diagnostic loses its main feature | Limit to the demo concepts, about 10 tagged items, drafted with an LLM and reviewed by hand |
| LLM provider outage or slowness during the review | Live demo fails | Adapter with timeout, template fallback, cached explanations and a recorded backup (TR-A-04, TR-L-12) |
| Dataset or Judge0 licence terms not suitable | Cannot use or ship the component | Check terms first; run Judge0 unmodified as a separate service (TR-D-05, TR-X-09) |
| Data-protection duties tighten in May 2027 | Rework after the review | Build consent, minimisation and deletion now (TR-S-05 to TR-S-08) |

**Changes to carry back into earlier documents.** This TRD tightened three points, and they were carried back into the PRD and DRD on 15 Oct 2026:

1. PRD requirement F-42 says the system generates a probe question. The TRD selects the probe from the vetted bank by concept, and treats generated probes as later work (TR-L-10).
2. The PRD's LLM latency requirement says to stream the first tokens within 5 seconds. The TRD replaces this with a progress state and a verified answer (TR-P-03).
3. The DRD sandbox section should list the Judge0 hardening items in TR-X-01 to TR-X-06.

**Open decisions for the team**

- Hosted or local model as the default for the demo, and who pays for the API key.
- Judge0 or a custom Docker runner, decided on day 1.
- Whether the misconception list comes from the instructor, from the literature, or both.
- Whether a cached explanation may be shown to other students before an instructor approves it.
- The default retention period for submissions and chat.
- Which machine hosts the demo, and who restores it if it fails.

## 12. Sources

Checked on 15 Oct 2026. Two pages were opened in full; the rest were read as search excerpts, so open each one in full before quoting it in the final report.

| Source | Used for | How read |
| --- | --- | --- |
| [Silva and Costa, 2025 (arXiv)](https://arxiv.org/abs/2503.14630v1) | Share of flawed LLM feedback hints | Opened in full |
| [Tanto Security, Judge0 sandbox escape](https://tantosec.com/blog/judge0/) | Sandbox design, CVEs and fixed version | Opened in full |
| [Tutor Kai study (arXiv)](https://arxiv.org/pdf/2403.09744) | Code in LLM replies, code-removal approach | Search excerpt |
| [NUS poster on LLM feedback](https://comp.nus.edu.sg/~bleong/slides/gaied23-coverage-poster.pdf) | Validating repairs against test cases | Search excerpt |
| [CodeHelp (arXiv)](https://arxiv.org/pdf/2308.06921) | One-shot requests and guardrails | Search excerpt |
| [Debugging without error messages (arXiv)](https://arxiv.org/abs/2501.05706) | Source code as context for explanations | Search excerpt |
| [Code-DKT (arXiv)](https://arxiv.org/pdf/2206.03545) | Code-aware knowledge tracing result | Search excerpt |
| [KCGen-KT (arXiv)](https://arxiv.org/pdf/2502.18632) | TIKTOC, CodeWorkout and FalconCode | Search excerpt |
| [SQKT (arXiv)](https://www.arxiv.org/pdf/2502.10408) | Student questions as a mastery signal | Search excerpt |
| [Judge0 CE docs](https://ce.judge0.com/) and [Judge0 API docs](https://api.judge0.com) | Limits, network flag, GPL v3 licence | Search excerpt |
| [JSA](https://www.jsalaw.com/?p=55573) and [AZB](https://www.azbpartners.com/bank/update-indias-digital-personal-data-protection-framework-comes-into-effect/) | India data-protection timeline | Search excerpt |
