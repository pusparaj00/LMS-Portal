# DRD — Adaptive AI-Powered LMS

Oct 15, 2026 · @Joseph

## 1. Architecture

A React frontend calls one FastAPI backend, which is split into six services; four external systems hold data, run code and generate text.

&#91;embedded content: system architecture · frontend, 6 services, 4 back-end systems\]

The mastery service is the single writer of student mastery (requirement F-32). The submission, diagnostic and explanation services send it evidence and read the result, and the chat router only reads. The sandbox runner is a separate container, so student code never runs inside the API process.

## 2. Technology stack

The stack favours tools the team already uses (Python, FastAPI, PyTorch) and keeps the number of moving parts small enough for a six-day build.

| Layer | Choice | Reason |
| --- | --- | --- |
| Frontend | React or Next.js with a Monaco code editor | Standard, and Monaco gives an editor with syntax highlighting |
| Backend API | FastAPI with Pydantic schemas | Already used in the project; typed request and response models |
| Database | PostgreSQL with the pgvector extension | One store for relational data and embeddings, which avoids running FAISS separately |
| Cache and sessions | Redis | Persistent CAT and diagnostic sessions, rate limits |
| Code execution | Judge0 (self-hosted) or a custom Docker runner | Isolation with CPU, memory and time limits already built in |
| Agent framework | LangGraph, or a plain Python state machine | Explicit routes and tool calls; the plain version is a safe fallback |
| LLM | One hosted API model behind an adapter, with an optional local model | Provider can be swapped; local model keeps data on premises |
| Embeddings | A sentence-embedding model run locally | No external call per chunk, and low cost |
| Models | PyTorch (IRT item parameters), NumPy (mastery updates) | Reuses the existing IRT and CAT code |
| Deployment | Docker Compose on a single machine | Reproducible demo with one command |
| Version control | Git and GitHub, with a branch per workstream | Matches the team's current workflow |

## 3. Data model

The schema has 15 core tables, and section 10 adds six more in PostgreSQL. Mastery is stored per student and concept, and every update is logged so it can be audited and replayed.

| Table | Key columns | Notes |
| --- | --- | --- |
| users | id, email, password\_hash, role | Role is student, instructor or admin |
| courses | id, title, instructor\_id | One instructor owner, many co-instructors later |
| enrollments | user\_id, course\_id, enrolled\_at | Links students to courses |
| concepts | id, course\_id, name, parent\_ids | Concept graph with prerequisite edges |
| problems | id, course\_id, title, statement, language, difficulty\_b, discrimination\_a | Item parameters start from priors and are refined later |
| problem\_concepts | problem\_id, concept\_id, weight | The Q-matrix |
| test\_cases | id, problem\_id, input, expected, hidden, category | Category maps failures to concepts |
| submissions | id, user\_id, problem\_id, code, created\_at | Raw student code |
| run\_results | submission\_id, status, passed, failed, error\_type, stderr, runtime\_ms | Structured sandbox evidence |
| mastery | user\_id, concept\_id, p\_known, updated\_at | Current mastery vector, one row per concept |
| mastery\_events | id, user\_id, concept\_id, before, after, evidence\_type, submission\_id | Append-only log of every update |
| diagnostic\_sessions | id, user\_id, state\_json, status | Cold-start test state, also cached in Redis |
| documents and chunks | id, course\_id, text, embedding, source\_ref | Course notes split into chunks with vector embeddings |
| chat\_messages | id, user\_id, role, content, route, sources | Chat history and the route chosen for each message |

Relations. A problem has many concepts through problem\_concepts and many test cases. A submission has one run\_result and many mastery\_events. A chunk belongs to a document, and a document belongs to a course.

## 4. Mastery and cold-start diagnostic

Mastery is a deterministic service. It keeps one probability per concept, updates it from execution evidence, and is the only component allowed to write to the mastery table.

**Mastery update.** Each concept starts from a population prior p0 (set per concept from the question bank, 0.5 by default). After a submission, each concept tagged on the problem is updated with a Bayesian rule using guess and slip rates that depend on the evidence type:

```latex
p' = \frac{p(1-s)}{p(1-s) + (1-p)g}\ \text{(correct)}, \qquad p' = \frac{p\,s}{p\,s + (1-p)(1-g)}\ \text{(incorrect)}
```

Here p is the current mastery, s the slip rate and g the guess rate. A partially failing submission is treated as incorrect with a weaker s, so the update is smaller than for a total failure. Slip and guess rates start as fixed defaults (for example 0.1 and 0.2) and are tuned on simulated students; the earlier DINA fit is not used until its guess-rate problem is fixed.

**Evidence weighting.**

| Evidence | Effect on the concept it maps to |
| --- | --- |
| All tests pass | Strong positive update on all tagged concepts |
| Some tests fail | Weak negative update on concepts linked to the failing test categories only |
| Compile or syntax error | Update the syntax concept, and leave other concepts unchanged |
| Runtime error (index, null, recursion depth) | Negative update on the concept linked to the error type |
| Timeout | Negative update on the efficiency or loop-termination concept |
| Probe question answered | Same rule as a normal submission, with extra weight |

**Prerequisite propagation.** If a concept's mastery falls sharply, a fraction of that change is passed to its prerequisite concepts, so a failing recursion problem can also lower the estimate for functions.

**Cold-start diagnostic.**

1. Start every concept at its population prior, so the first question is chosen with no student history.
2. Select the next problem that maximizes expected information gain over the mastery vector, using the problem's concept weights and its difficulty and discrimination.
3. Update mastery after each answer using the rule above.
4. Stop after 10 items, or earlier if the uncertainty on the weakest concepts is below a threshold.
5. Save the resulting vector and show it on the dashboard.

**Reuse.** The existing 2PL IRT code supplies item difficulty and discrimination, and the CAT code supplies Fisher-information item selection. The difference is that selection now targets concept-level uncertainty instead of one ability number.

## 5. Submission and feedback loop

A passing submission raises mastery and ends there; a failing one triggers retrieval, an explanation and a probe question.

&#91;embedded content: submission and feedback loop · 9 steps, 1 decision\]

The failing branch lowers mastery first, using the evidence weights in section 4. The explanation is built only from the failure evidence, the student's code and the retrieved notes, and the verifier (P0, section 10) checks it before display. The probe answer goes through the same mastery rule, which closes the loop. Passing submissions skip retrieval and the LLM entirely, which keeps cost and latency down.

## 6. Agentic router

One router receives every chat message and sends it to a single route. The LLM classifies the message into a fixed label set and returns structured JSON, and a rule-based fallback takes over when the output is invalid or confidence is low.

| Route | Triggered by | Tools it may call | Output |
| --- | --- | --- | --- |
| explain | Why was my answer wrong, explain this error | Latest run\_result, RAG search | Grounded explanation with source references |
| hint | I am stuck, give me a hint | Problem statement, run\_result, RAG search | One hint at a time, never the full solution |
| progress | How am I doing, what am I weak at | Mastery service (read only) | Plain summary of the mastery vector |
| recommend | What should I do next | Mastery service, problem bank | Next problem or note, with the reason |
| lms | Deadlines, grades, course info | LMS database (read only, scoped to the user) | Direct answer from records |
| general | Anything else about programming | RAG search, LLM | Answer with sources if found, otherwise a general answer marked as such |

**Rules**

1. The router never writes mastery. Only the grading and probe flows call the mastery service.
2. Each tool call is limited to the current user's data.
3. If the classifier output is not valid JSON or its confidence is under 0.6, keyword rules choose the route (for example run, error and traceback go to explain), and the reply tells the student which route was used so they can correct it.
4. Every message logs the chosen route, tools called and sources returned in chat\_messages.
5. The hint and explain routes use a system prompt that forbids full solutions unless the instructor has enabled them for that problem.

**Implementation.** A LangGraph state graph with one node for classification and one node per route. If LangGraph slows the build, the same logic works as a Python function that maps the label to a handler.

## 7. API specification

All endpoints are under /api/v1, use JWT bearer tokens, and check the caller's role. Request and response bodies are Pydantic models.

| Method and path | Purpose | Role |
| --- | --- | --- |
| POST /auth/register, POST /auth/login | Create account, return a JWT | Public |
| GET /courses, POST /courses | List the courses a person is in or teaches, or create one | Student read, instructor write |
| POST /courses/join | Join the course that has this class code (F-81); there is no open enrolment | Student |
| GET, PUT /courses/{id}/join-code, POST /courses/{id}/join-code/reset | Show, close or open, and reset the class code | Teacher (admin reads) |
| GET /courses/{id}/people, POST and DELETE /courses/{id}/teachers, PUT /courses/{id}/students/{id}/mute | Teachers, students, co-teachers and muting (F-82) | Course members |
| POST /courses/{id}/documents | Upload course notes, then chunk and embed them | Instructor |
| GET /problems?course\_id= | List problems and their concept tags | Any |
| POST /problems | Create a problem with concepts and test cases | Instructor |
| POST /diagnostic/start | Start the cold-start test, return the first problem | Student |
| POST /diagnostic/answer | Submit an answer, return updated mastery and the next problem or the final vector | Student |
| POST /submissions | Run code in the sandbox, return run evidence and the mastery change | Student |
| POST /submissions/{id}/explain | Return a grounded explanation and a probe problem | Student |
| POST /probes/{id}/answer | Grade the probe and update mastery | Student |
| GET /students/me/mastery | Current mastery vector and recent events | Student |
| GET /courses/{id}/class-mastery | Class heatmap and common failure patterns | Instructor |
| POST /chat | Send a message, return the routed reply, route label and sources | Student |
| GET /health | Service health | Public |

**Example response from POST /submissions.**

```json
{
  "submission_id": 412,
  "status": "failed",
  "passed": 3,
  "failed": 2,
  "error_type": null,
  "failed_categories": ["empty_input", "large_input"],
  "mastery_changes": [{"concept": "loops", "before": 0.62, "after": 0.55}]
}
```

The existing /cat/start and /cat/answer endpoints become the item-selection code behind /diagnostic/start and /diagnostic/answer.

## 8. Sandbox, security and deployment

Student code is untrusted, so execution runs in its own container, apart from the API and the database.

**Sandbox rules**

1. One fresh container per run, started from a minimal Python image, running as a non-root user.
2. No network, no host mounts, a read-only root filesystem and a small writable temp directory.
3. Limits per run: CPU time, memory, process count, output size and a wall-clock timeout of 10 seconds.
4. The runner receives code and test cases and returns only structured results; hidden test inputs are never shown to the student.
5. Judge0 is the first choice because it already enforces these limits. If it cannot be set up in a day, use a custom Docker runner with the same rules.

**Judge0 hardening (TRD TR-X-01 to TR-X-06).** Pin Judge0 CE v1.13.1 or a newer security release, because earlier versions had published escape vulnerabilities. Change every default password and require an authentication token. Disable network access, including the setting that lets a single request enable it. Disable compiler options, command-line arguments and additional files. Turn on submission deletion, and set explicit CPU, wall-time, memory, process, file and output limits. Run it on a dedicated host with no route to PostgreSQL, Redis or the API's secrets. The release notes recommend Ubuntu 22.04 with cgroup v1 enabled, so use a Linux virtual machine set up that way, not WSL2 or Docker Desktop.

**Application security**

- Passwords are hashed with bcrypt, and JWTs expire after a short time.
- Every endpoint checks role and ownership, so a student can read only their own submissions, mastery and chat.
- The LLM adapter sends only the failure evidence, the student's code and retrieved chunks, never other students' data.
- Secrets live in environment variables, not in the repository, and rate limits apply to /submissions and /chat.

**Deployment.** Docker Compose runs six services on one machine: frontend, API, PostgreSQL with pgvector, Redis, the sandbox runner and an optional local LLM. A seed script loads the demo course, problems, notes and two demo accounts, so the whole system starts with one command.

## 9. Testing and verification

The tests focus on the parts that can fail in front of the examiners: the sandbox, the mastery update and the explanation flow.

| Area | Test | Pass condition |
| --- | --- | --- |
| Sandbox | Infinite loop, memory bomb, fork bomb, network call, file write outside temp | Each is stopped within limits and reported as a structured error |
| Grading | All 35 problems run against a reference solution | Every reference solution passes every test |
| Mastery update | Unit tests of the update rule; simulated students with known skill | Mastery moves in the right direction and stays within 0.15 of true skill after 15 submissions |
| Diagnostic | Adaptive vs random selection on simulated students | Adaptive reaches the error threshold in at least 30% fewer items |
| RAG | 20 hand-written questions with a known source chunk | Correct chunk in the top 3 results for at least 80% of questions |
| Explanations | 20 wrong submissions rated by two reviewers | Each explanation names the failing evidence and matches the source; none reveals a full solution |
| Router | 50 labelled messages | At least 90% routed correctly |
| API | Role and ownership checks | A student cannot read another student's data or call instructor endpoints |
| End to end | Run the full demo script 10 times | All 10 runs complete without manual repair |

Results go into the final report with the dates they were run, which also supports any later patent filing.

## 10. Verified feedback and differentiators

This section adds the parts that make the product different from a chat tutor: explanations are checked before display, hints are rationed, repeated failures are answered from a cache, and the diagnostic names misconceptions. It follows the audit in section 10 of the PRD.

**Structured explanation.** The LLM returns JSON, never free text, so each claim can be checked:

```json
{
  "failing_test_id": 17,
  "line": 6,
  "concept_id": "loops",
  "claim": "The loop stops one item early, so the last element is never read.",
  "source_chunk_ids": [212, 215],
  "hint_level": 1
}
```

**Verifier checks.** All checks are deterministic code, not another LLM opinion.

| Check | How it runs | On failure |
| --- | --- | --- |
| Test exists | failing\_test\_id must be in the run result's failed list | Regenerate once |
| Line exists | line must fall inside the student's code | Regenerate once |
| Concept matches | concept\_id must be linked to the failed test category in problem\_concepts | Regenerate with the concept fixed |
| Sources real | Every source\_chunk\_id must be in the retrieved set | Drop the citation or regenerate |
| No solution code | Reject fenced code, or code beyond a few lines, and compare token similarity with the reference solution against a threshold tuned on the 35 problems | Regenerate once |
| Claim replay (P1) | If the claim names an input, run the student's code on it in the sandbox and confirm the output differs from the reference | Mark unverified and show the fallback |

After two failed attempts the system shows a fallback hint built from a template keyed on error type and concept, with no LLM text. Every attempt is logged in explanation\_checks, so the pass rate can be reported.

**Hint ladder.** Level 1 is a concept hint from the course notes. Level 2 points to the failing test category or the line. Level 3 is a worked example on a different problem. The full solution is never shown. A student moves up one level per request, and the instructor sets the maximum level per problem.

**Failure-signature cache.** The signature is a hash of the problem, the sorted failed test categories, the error type and the normalised error message. A verified explanation is stored under it, and later students with the same signature get it without a new LLM call. Instructors can approve or edit stored entries (status auto-verified or instructor-approved). Personal tone and level come from the chat route, so the stored text stays factual.

**Misconception-tagged diagnostic items.** Some placement items are code-tracing multiple-choice questions. Each wrong option is linked to a named misconception, such as an off-by-one in loop bounds. A chosen option raises that misconception's probability and lowers the related concept's mastery, so the end of the test reports both a mastery vector and the top suspected misconceptions.

**Evidence ledger.** Each row in mastery\_events stores the rule used and a reference to the run result or answer behind it, so the student's "why did my mastery change" view and the instructor's audit read from the same data.

**New tables**

| Table | Key columns |
| --- | --- |
| misconceptions | id, concept\_id, description |
| item\_options | problem\_id, option\_text, is\_correct, misconception\_id |
| explanation\_cache | signature, explanation\_json, status, hit\_count, approved\_by |
| explanation\_checks | id, submission\_id, check\_name, passed, attempt |
| mastery\_params | concept\_id, evidence\_type, slip, guess, prior |
| evidence\_concept\_map | test\_category, error\_type, concept\_id, weight |

**New endpoints**

| Method and path | Purpose | Role |
| --- | --- | --- |
| GET /students/me/mastery/{concept}/history | Mastery changes with their evidence | Student |
| GET /courses/{id}/misconceptions | Class-level misconception counts | Instructor |
| POST /explanations/{signature}/approve | Approve or edit a cached explanation | Instructor |
| PUT /problems/{id}/policy | Set the maximum hint level and leak policy | Instructor |

**Tests added.** Run 50 adversarial help requests (such as "give me the full code") and require zero leaks. Rate 20 explanations for claim accuracy with and without the verifier. Report the verifier pass rate on the first attempt and the share of failures served from the cache. Run the full demo once on a local model to show the private deployment option.
